"""Background processing: the real ``MessageDispatcher`` of the walking skeleton.

Flow (the webhook has already verified, normalised and claimed the message):

    webhook -> dispatcher.dispatch(message)   returns immediately (queued)        -> 200 ACK
                      |
                      v   worker thread
          responder.respond(message) -> reply -> sender.send(reply)  (bounded retries)
                      |
                      v
          completion.mark_done / mark_failed

Delivery semantics (ADR-004): after the ACK, Meta will not resend, so processing is
"at most once, best effort": a reply that still fails after the retries is recorded as ``failed``
and is not sent again; a crash between the ACK and the end of processing leaves the key in
``claimed`` state (visible through ``SqliteIdempotencyStore.unfinished_keys``) but does not
re-run it, because the message content is deliberately not persisted yet.

Back-pressure: at most ``max_pending`` messages may be queued or running. Beyond that
``dispatch`` raises ``DispatchRejected``; the webhook then releases the claim and answers 5xx,
so Meta retries later instead of this process growing without bound.

Nothing here logs message text, recipients or credentials.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass

from wazi.idempotency import CompletionRecorder
from wazi.messaging import NormalizedMessage
from wazi.ports import ReplySender, Responder, SendError
from wazi.safe_logging import fingerprint

logger = logging.getLogger("wazi.worker")


class DispatchRejected(RuntimeError):
    """The worker cannot accept more work right now (queue full or shutting down)."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0

    def delay_for(self, attempt: int, retry_after: float | None) -> float:
        """Delay before the next attempt; ``attempt`` is the 1-based attempt that just failed."""
        backoff = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        if retry_after is not None:
            backoff = max(backoff, min(retry_after, self.max_delay))
        return backoff


class BackgroundDispatcher:
    def __init__(
        self,
        responder: Responder,
        sender: ReplySender,
        *,
        completion: CompletionRecorder | None = None,
        executor: Executor | None = None,
        max_workers: int = 4,
        max_pending: int = 1000,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_pending < 1:
            raise ValueError("max_pending must be >= 1")
        self._responder = responder
        self._sender = sender
        self._completion = completion
        self._owns_executor = executor is None
        self._executor = executor or ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="wazi-worker"
        )
        self._max_pending = max_pending
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        self._pending = 0
        self._closed = False
        self._cond = threading.Condition()

    # ---- MessageDispatcher ---------------------------------------------------------------

    def dispatch(self, message: NormalizedMessage) -> None:
        with self._cond:
            if self._closed:
                raise DispatchRejected("worker is shut down")
            if self._pending >= self._max_pending:
                raise DispatchRejected("worker queue is full")
            self._pending += 1
        try:
            self._executor.submit(self._run, message)
        except BaseException:
            self._finish_one()
            raise

    # ---- lifecycle -----------------------------------------------------------------------

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until no message is queued or running. Mainly for tests and shutdown."""
        with self._cond:
            return self._cond.wait_for(lambda: self._pending == 0, timeout=timeout)

    def close(self, wait: bool = True) -> None:
        with self._cond:
            self._closed = True
        if self._owns_executor:
            self._executor.shutdown(wait=wait)
        closer = getattr(self._sender, "close", None)
        if callable(closer):
            closer()

    # ---- internals -----------------------------------------------------------------------

    def _finish_one(self) -> None:
        with self._cond:
            self._pending -= 1
            self._cond.notify_all()

    def _run(self, message: NormalizedMessage) -> None:
        tag = fingerprint(message.message_id)
        try:
            self._process(message, tag)
            self._record(message.message_id, ok=True)
        except Exception as exc:  # a worker thread must never die with an unlogged error
            logger.error("processing failed (%s) id=%s", type(exc).__name__, tag)
            self._record(message.message_id, ok=False)
        finally:
            self._finish_one()

    def _process(self, message: NormalizedMessage, tag: str) -> None:
        reply = self._responder.respond(message)
        if reply is None:
            logger.debug("no reply for id=%s", tag)
            return
        for attempt in range(1, self._retry.max_attempts + 1):
            try:
                result = self._sender.send(reply)
                # Trace: webhook "message queued id=<tag>" -> here -> Meta's id for OUR reply.
                sent_tag = fingerprint(result.message_id) if result.message_id else "unknown"
                logger.info("reply sent id=%s sent_id=%s attempt=%d", tag, sent_tag, attempt)
                return
            except SendError as err:
                last_attempt = attempt >= self._retry.max_attempts
                if not err.retryable or last_attempt:
                    logger.error(
                        "reply not sent id=%s attempt=%d retryable=%s http=%s code=%s",
                        tag,
                        attempt,
                        err.retryable,
                        err.status_code,
                        err.error_code,
                    )
                    raise
                delay = self._retry.delay_for(attempt, err.retry_after)
                logger.warning(
                    "send failed, retrying id=%s attempt=%d in %.1fs", tag, attempt, delay
                )
                self._sleep(delay)

    def _record(self, key: str, *, ok: bool) -> None:
        if self._completion is None:
            return
        try:
            (self._completion.mark_done if ok else self._completion.mark_failed)(key)
        except Exception as exc:
            logger.error("could not record completion (%s)", type(exc).__name__)
