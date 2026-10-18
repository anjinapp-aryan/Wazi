"""Signature verifier tests. Pure functions: no HTTP, no FastAPI."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from wazi.security import compute_signature, verify_signature

SECRET = "test-secret"
BODY = b'{"object":"whatsapp_business_account","entry":[]}'


def good_header(body: bytes = BODY, secret: str = SECRET) -> str:
    return compute_signature(body, secret)


def test_independent_published_hmac_vector():
    # Well-known public HMAC_SHA256 test vector (key="key", message="The quick brown fox ...").
    # It proves our construction is standard HMAC-SHA256, not just self-consistent.
    message = b"The quick brown fox jumps over the lazy dog"
    expected = "f7bc83f430538424b13298e6aa6fb143ef4d59a14946175997479dbc2d1a3cd8"
    assert compute_signature(message, "key") == "sha256=" + expected
    assert verify_signature(message, "sha256=" + expected, "key") is True


def test_valid_signature_accepted():
    assert verify_signature(BODY, good_header(), SECRET) is True


def test_uppercase_hex_accepted():
    header = "sha256=" + good_header().removeprefix("sha256=").upper()
    assert verify_signature(BODY, header, SECRET) is True


def test_matches_stdlib_hmac_directly():
    digest = hmac.new(SECRET.encode(), BODY, hashlib.sha256).hexdigest()
    assert verify_signature(BODY, f"sha256={digest}", SECRET) is True


def test_invalid_signature_rejected():
    assert verify_signature(BODY, "sha256=" + "0" * 64, SECRET) is False


def test_wrong_secret_rejected():
    assert verify_signature(BODY, good_header(secret="another-secret"), SECRET) is False


def test_modified_body_rejected():
    assert verify_signature(BODY + b" ", good_header(), SECRET) is False
    assert verify_signature(BODY.replace(b"entry", b"entrx"), good_header(), SECRET) is False


def test_reserialised_json_rejected():
    # Same JSON meaning, different bytes (extra whitespace): the signature must NOT match.
    pretty = b'{ "object": "whatsapp_business_account", "entry": [] }'
    assert verify_signature(pretty, good_header(), SECRET) is False


def test_empty_body_with_correct_signature_verifies_but_is_a_valid_hmac():
    # The verifier only answers "is this the right signature for these bytes". Rejecting an
    # empty body is the job of the JSON layer (see webhook tests).
    assert verify_signature(b"", good_header(b""), SECRET) is True


def test_empty_body_with_signature_of_other_body_rejected():
    assert verify_signature(b"", good_header(BODY), SECRET) is False


@pytest.mark.parametrize("header", [None, ""])
def test_missing_signature_rejected(header):
    assert verify_signature(BODY, header, SECRET) is False


@pytest.mark.parametrize(
    "header",
    [
        "0" * 64,  # no prefix
        "sha1=" + "0" * 40,  # wrong algorithm
        "SHA256=" + "0" * 64,  # prefix is case-sensitive per Meta's documented format
        "sha256=",  # prefix only
        "sha256=abc",  # too short
        "sha256=" + "0" * 63,  # one short
        "sha256=" + "0" * 65,  # one long
        "sha256=" + "g" * 64,  # not hex
        "sha256=" + "é" * 64,  # non-ASCII: must be rejected, not raise
        "sha256=" + "0" * 64 + " ",  # trailing whitespace
        " sha256=" + "0" * 64,  # leading whitespace
    ],
)
def test_malformed_signature_rejected_without_raising(header):
    assert verify_signature(BODY, header, SECRET) is False


@pytest.mark.parametrize("secret", [None, ""])
def test_missing_secret_fails_closed(secret):
    # Even a signature computed with an empty key must not be accepted.
    forged = compute_signature(BODY, "")
    assert verify_signature(BODY, forged, secret) is False
    assert verify_signature(BODY, good_header(), secret) is False


def test_non_bytes_body_rejected():
    assert verify_signature("not bytes", good_header(), SECRET) is False  # type: ignore[arg-type]


def test_bytearray_body_supported():
    assert verify_signature(bytearray(BODY), good_header(), SECRET) is True


def test_comparison_is_constant_time_function():
    # We cannot measure timing reliably in a unit test; assert the primitive is the one used.
    import inspect

    from wazi.security import signature

    assert "hmac.compare_digest" in inspect.getsource(signature.verify_signature)
