"""Background worker: queueing, retries, failure handling, back-pressure, shutdown."""

from __future__ import annotations

import logging
from concurrent.futures import Executor

import pytest

from tests.fakes import FakeSender, permanent_error, transient_error
from tests.helpers import fixture_json
from wazi.idempotency import InMemoryIdempotencyStore
from wazi.messaging import NormalizedMessage, OutboundReply, normalize_payload
from wazi.responder import EchoResponder
from wazi.worker import BackgroundDispatcher, DispatchRejected, RetryPolicy


def make_message(name: str = "text_message") -> NormalizedMessage:
    return normalize_payload(fixture_json(name)).messages[0]


class NoReply:
    def respond(self, message):
        return None


class Exploding:
    def respond(self, message):
        raise RuntimeError("responder crashed: private-detail")


class Sleeps:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


def build(sender, store, responder=None, **kwargs) -> BackgroundDispatcher:
    kwargs.setdefault("sleep", Sleeps())
    return BackgroundDispatcher(responder or EchoResponder(), sender, completion=store, **kwargs)


def claim_and_dispatch(dispatcher, store, message) -> None:
    assert store.claim(message.message_id)
    dispatcher.dispatch(message)


# ---- happy path and queueing ----------------------------------------------------------------


def test_dispatch_returns_before_the_work_finishes(store):
    sender = FakeSender(block=True)
    dispatcher = build(sender, store)
    message = make_message()
    claim_and_dispatch(dispatcher, store, message)  # returns even though sending is blocked
    assert sender.started.wait(timeout=5)
    assert dispatcher.wait_idle(timeout=0.05) is False  # still running
    assert store.state_of(message.message_id) == "claimed"
    sender.release_event.set()
    assert dispatcher.wait_idle(timeout=5) is True
    assert store.state_of(message.message_id) == "done"
    dispatcher.close()


def test_reply_is_built_by_the_responder_and_sent_once(store):
    sender = FakeSender()
    dispatcher = build(sender, store)
    message = make_message()
    claim_and_dispatch(dispatcher, store, message)
    assert dispatcher.wait_idle(5)
    (sent,) = sender.replies
    assert sent == OutboundReply(
        recipient_id=message.sender_id,
        text="Wazi skeleton echo: Hello Wazi, this is a test.",
        in_reply_to=message.message_id,
    )
    dispatcher.close()


def test_no_reply_means_done_without_sending(store):
    sender = FakeSender()
    dispatcher = build(sender, store, responder=NoReply())
    message = make_message()
    claim_and_dispatch(dispatcher, store, message)
    assert dispatcher.wait_idle(5)
    assert sender.attempts == 0
    assert store.state_of(message.message_id) == "done"
    dispatcher.close()


# ---- retries --------------------------------------------------------------------------------


def test_transient_failure_is_retried_with_backoff_then_succeeds(store):
    sender = FakeSender(script=[transient_error(), transient_error(), None])
    sleeps = Sleeps()
    dispatcher = build(sender, store, sleep=sleeps, retry=RetryPolicy(max_attempts=3))
    message = make_message()
    claim_and_dispatch(dispatcher, store, message)
    assert dispatcher.wait_idle(5)
    assert sender.attempts == 3 and len(sender.replies) == 1
    assert sleeps.calls == [0.5, 1.0]
    assert store.state_of(message.message_id) == "done"
    dispatcher.close()


def test_retries_are_bounded_then_the_message_is_marked_failed(store):
    sender = FakeSender(script=[transient_error()] * 10)
    sleeps = Sleeps()
    dispatcher = build(sender, store, sleep=sleeps, retry=RetryPolicy(max_attempts=3))
    message = make_message()
    claim_and_dispatch(dispatcher, store, message)
    assert dispatcher.wait_idle(5)
    assert sender.attempts == 3 and sender.replies == []
    assert len(sleeps.calls) == 2
    assert store.state_of(message.message_id) == "failed"
    dispatcher.close()


def test_permanent_failure_is_not_retried(store):
    sender = FakeSender(script=[permanent_error(status_code=400, error_code=131047)])
    sleeps = Sleeps()
    dispatcher = build(sender, store, sleep=sleeps)
    message = make_message()
    claim_and_dispatch(dispatcher, store, message)
    assert dispatcher.wait_idle(5)
    assert sender.attempts == 1 and sleeps.calls == []
    assert store.state_of(message.message_id) == "failed"
    dispatcher.close()


def test_retry_delay_math():
    policy = RetryPolicy(max_attempts=5, base_delay=0.5, max_delay=8.0)
    assert [policy.delay_for(n, None) for n in (1, 2, 3, 4, 5, 6)] == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]
    assert policy.delay_for(1, retry_after=3.0) == 3.0  # provider asked for longer
    assert policy.delay_for(1, retry_after=0.1) == 0.5  # never shorter than our backoff
    assert policy.delay_for(1, retry_after=999) == 8.0  # capped


def test_retry_after_from_the_provider_is_honoured(store):
    sender = FakeSender(script=[transient_error(retry_after=4.0), None])
    sleeps = Sleeps()
    dispatcher = build(sender, store, sleep=sleeps)
    claim_and_dispatch(dispatcher, store, make_message())
    assert dispatcher.wait_idle(5)
    assert sleeps.calls == [4.0]
    dispatcher.close()


# ---- failure isolation ----------------------------------------------------------------------


def test_responder_crash_marks_failed_and_the_worker_keeps_working(store):
    sender = FakeSender()
    crashing = build(sender, store, responder=Exploding())
    first = make_message()
    claim_and_dispatch(crashing, store, first)
    assert crashing.wait_idle(5)
    assert store.state_of(first.message_id) == "failed"
    crashing.close()

    healthy = build(sender, store)
    second = make_message("multi_message")
    claim_and_dispatch(healthy, store, second)
    assert healthy.wait_idle(5)
    assert store.state_of(second.message_id) == "done"
    healthy.close()


def test_completion_recording_errors_do_not_kill_the_worker():
    class BrokenRecorder:
        def mark_done(self, key):
            raise OSError("disk full")

        def mark_failed(self, key):
            raise OSError("disk full")

    sender = FakeSender()
    dispatcher = BackgroundDispatcher(EchoResponder(), sender, completion=BrokenRecorder())
    dispatcher.dispatch(make_message())
    assert dispatcher.wait_idle(5)
    assert len(sender.replies) == 1
    dispatcher.close()


# ---- back-pressure and shutdown -------------------------------------------------------------


def test_full_queue_rejects_new_work_until_space_frees_up(store):
    sender = FakeSender(block=True)
    dispatcher = build(sender, store, max_pending=1, max_workers=1)
    first, second = make_message(), make_message("multi_message")
    claim_and_dispatch(dispatcher, store, first)
    assert sender.started.wait(5)
    with pytest.raises(DispatchRejected):
        dispatcher.dispatch(second)
    sender.release_event.set()
    assert dispatcher.wait_idle(5)
    dispatcher.dispatch(second)  # accepted now
    assert dispatcher.wait_idle(5)
    dispatcher.close()


def test_submit_failure_does_not_leak_a_pending_slot(store):
    class BrokenExecutor(Executor):
        def submit(self, fn, /, *args, **kwargs):
            raise RuntimeError("pool is gone")

    dispatcher = BackgroundDispatcher(
        EchoResponder(), FakeSender(), executor=BrokenExecutor(), max_pending=1
    )
    for _ in range(3):  # would raise DispatchRejected on the 2nd try if a slot leaked
        with pytest.raises(RuntimeError):
            dispatcher.dispatch(make_message())
    assert dispatcher.wait_idle(0.1) is True


def test_close_finishes_queued_work_closes_the_sender_and_rejects_new_work(store):
    sender = FakeSender()
    dispatcher = build(sender, store)
    message = make_message()
    claim_and_dispatch(dispatcher, store, message)
    dispatcher.close(wait=True)
    assert store.state_of(message.message_id) == "done"
    assert sender.closed is True
    with pytest.raises(DispatchRejected):
        dispatcher.dispatch(make_message())


def test_invalid_construction():
    with pytest.raises(ValueError):
        BackgroundDispatcher(EchoResponder(), FakeSender(), max_pending=0)


# ---- privacy --------------------------------------------------------------------------------


def test_worker_logs_contain_no_text_recipient_or_raw_ids(store, caplog):
    sender = FakeSender(script=[transient_error(status_code=429, error_code=130429), None])
    dispatcher = build(sender, store)
    crashing = build(FakeSender(), store, responder=Exploding())
    message = make_message()
    with caplog.at_level(logging.DEBUG):
        claim_and_dispatch(dispatcher, store, message)
        dispatcher.wait_idle(5)
        crashing.dispatch(make_message("multi_message"))
        crashing.wait_idle(5)
    dispatcher.close()
    crashing.close()
    logged = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("wazi"))
    assert logged
    for forbidden in (
        "Hello Wazi",
        message.sender_id,
        message.message_id,
        "private-detail",  # exception text must not be logged, only its type
    ):
        assert forbidden not in logged
