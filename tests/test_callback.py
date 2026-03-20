"""Tests for PaynowProcessor callback handling."""

import base64
import hashlib
import hmac as hmac_mod
import json

import pytest

from getpaid_core.enums import PaymentEvent
from getpaid_core.exceptions import InvalidCallbackError

from getpaid_paynow.processor import PaynowProcessor

from .conftest import PAYNOW_CONFIG
from .conftest import make_mock_payment


SIGNATURE_KEY: str = str(PAYNOW_CONFIG["signature_key"])


def _make_processor(payment=None, config=None):
    if payment is None:
        payment = make_mock_payment()
    if config is None:
        config = PAYNOW_CONFIG.copy()
    return PaynowProcessor(payment=payment, config=config)


def _sign_body(body: str, key: str = SIGNATURE_KEY) -> str:
    digest = hmac_mod.new(
        key.encode(),
        body.encode(),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode()


def _notification(
    *,
    payment_id: str = "PAY-123",
    external_id: str = "test-payment-123",
    status: str = "CONFIRMED",
    modified_at: str = "2025-01-15T10:30:00",
) -> tuple[dict, str]:
    payload = {
        "paymentId": payment_id,
        "externalId": external_id,
        "status": status,
        "modifiedAt": modified_at,
    }
    raw_body = json.dumps(payload, separators=(",", ":"))
    return payload, raw_body


class TestVerifyCallback:
    async def test_valid_signature(self):
        data, raw_body = _notification()
        signature = _sign_body(raw_body)
        processor = _make_processor()

        await processor.verify_callback(
            data=data,
            headers={"Signature": signature},
            raw_body=raw_body,
        )

    async def test_missing_signature_raises(self):
        data, raw_body = _notification()
        processor = _make_processor()

        with pytest.raises(InvalidCallbackError, match="Missing Signature"):
            await processor.verify_callback(
                data=data,
                headers={},
                raw_body=raw_body,
            )

    async def test_bad_signature_raises(self):
        data, raw_body = _notification()
        processor = _make_processor()

        with pytest.raises(InvalidCallbackError, match="BAD SIGNATURE"):
            await processor.verify_callback(
                data=data,
                headers={"Signature": "bad_signature"},
                raw_body=raw_body,
            )

    async def test_missing_raw_body_raises(self):
        data, _ = _notification()
        processor = _make_processor()

        with pytest.raises(InvalidCallbackError, match="Missing raw_body"):
            await processor.verify_callback(
                data=data, headers={"Signature": "x"}
            )


class TestHandleCallback:
    async def test_confirmed_returns_capture_update(self):
        processor = _make_processor()
        data, _ = _notification(status="CONFIRMED")

        update = await processor.handle_callback(data=data, headers={})

        assert update is not None
        assert update.payment_event is PaymentEvent.PAYMENT_CAPTURED
        assert update.external_id == "PAY-123"
        assert (
            update.provider_event_id == "PAY-123:CONFIRMED:2025-01-15T10:30:00"
        )

    async def test_rejected_returns_failure_update(self):
        processor = _make_processor()
        data, _ = _notification(status="REJECTED")

        update = await processor.handle_callback(data=data, headers={})

        assert update is not None
        assert update.payment_event is PaymentEvent.FAILED
        assert update.external_id == "PAY-123"

    async def test_pending_returns_metadata_only_update(self):
        processor = _make_processor()
        data, _ = _notification(status="PENDING")

        update = await processor.handle_callback(data=data, headers={})

        assert update is not None
        assert update.payment_event is None
        assert update.external_id == "PAY-123"
        assert update.provider_data["paynow_status"] == "PENDING"

    async def test_same_payload_generates_same_event_id(self):
        processor = _make_processor()
        data, _ = _notification(status="CONFIRMED")

        first = await processor.handle_callback(data=data, headers={})
        second = await processor.handle_callback(data=data, headers={})

        assert first is not None
        assert second is not None
        assert first.provider_event_id == second.provider_event_id
