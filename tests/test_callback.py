"""Tests for PaynowProcessor verify_callback and handle_callback."""

import base64
import hashlib
import hmac as hmac_mod
import json

import pytest
from getpaid_core.enums import PaymentStatus
from getpaid_core.exceptions import InvalidCallbackError
from getpaid_core.fsm import create_payment_machine

from getpaid_paynow.processor import PaynowProcessor

from .conftest import PAYNOW_CONFIG
from .conftest import FakePayment
from .conftest import make_mock_payment


SIGNATURE_KEY: str = str(PAYNOW_CONFIG["signature_key"])


def _make_processor(payment=None, config=None):
    """Create a PaynowProcessor with defaults."""
    if payment is None:
        payment = make_mock_payment()
    if config is None:
        config = PAYNOW_CONFIG.copy()
    return PaynowProcessor(payment=payment, config=config)


def _sign_body(body: str, key: str = SIGNATURE_KEY) -> str:
    """Compute HMAC-SHA256 notification signature."""
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
    """Build a valid notification payload and raw body."""
    payload = {
        "paymentId": payment_id,
        "externalId": external_id,
        "status": status,
        "modifiedAt": modified_at,
    }
    raw_body = json.dumps(payload, separators=(",", ":"))
    return payload, raw_body


class TestVerifyCallback:
    """Tests for verify_callback signature verification."""

    async def test_valid_signature(self):
        data, raw_body = _notification()
        signature = _sign_body(raw_body)
        headers = {"Signature": signature}
        processor = _make_processor()
        # Should not raise
        await processor.verify_callback(
            data=data,
            headers=headers,
            raw_body=raw_body,
        )

    async def test_missing_signature_raises(self):
        data, raw_body = _notification()
        headers = {}  # No Signature header
        processor = _make_processor()
        with pytest.raises(
            InvalidCallbackError,
            match="Missing Signature",
        ):
            await processor.verify_callback(
                data=data,
                headers=headers,
                raw_body=raw_body,
            )

    async def test_lowercase_signature_header_is_accepted(self):
        data, raw_body = _notification()
        signature = _sign_body(raw_body)
        headers = {"signature": signature}
        processor = _make_processor()
        await processor.verify_callback(
            data=data,
            headers=headers,
            raw_body=raw_body.encode("utf-8"),
        )

    async def test_missing_raw_body_raises(self):
        data, raw_body = _notification()
        signature = _sign_body(raw_body)
        headers = {"Signature": signature}
        processor = _make_processor()
        with pytest.raises(InvalidCallbackError, match="Missing raw_body"):
            await processor.verify_callback(
                data=data,
                headers=headers,
            )

    async def test_bad_signature_raises(self):
        data, raw_body = _notification()
        headers = {"Signature": "bad_signature"}
        processor = _make_processor()
        with pytest.raises(
            InvalidCallbackError,
            match="BAD SIGNATURE",
        ):
            await processor.verify_callback(
                data=data,
                headers=headers,
                raw_body=raw_body,
            )

    async def test_tampered_body_raises(self):
        """If body is tampered after signing, verification fails."""
        _, raw_body = _notification(status="CONFIRMED")
        signature = _sign_body(raw_body)
        # Tamper the body
        tampered_body = raw_body.replace("CONFIRMED", "REJECTED")
        tampered_data = json.loads(tampered_body)
        headers = {"Signature": signature}
        processor = _make_processor()
        with pytest.raises(InvalidCallbackError):
            await processor.verify_callback(
                data=tampered_data,
                headers=headers,
                raw_body=tampered_body,
            )

    async def test_wrong_signature_key_raises(self):
        """Signature computed with wrong key is rejected."""
        data, raw_body = _notification()
        wrong_signature = _sign_body(raw_body, key="wrong-key")
        headers = {"Signature": wrong_signature}
        processor = _make_processor()
        with pytest.raises(InvalidCallbackError):
            await processor.verify_callback(
                data=data,
                headers=headers,
                raw_body=raw_body,
            )


class TestHandleCallback:
    """Tests for handle_callback with FSM transitions."""

    async def test_confirmed_marks_paid(self):
        """CONFIRMED status moves PREPARED payment to PAID."""
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "CONFIRMED",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.PAID

    async def test_rejected_marks_failed(self):
        """REJECTED status moves payment to FAILED."""
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "REJECTED",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.FAILED

    async def test_error_marks_failed(self):
        """ERROR status moves payment to FAILED."""
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "ERROR",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.FAILED

    async def test_expired_marks_failed(self):
        """EXPIRED status moves payment to FAILED."""
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "EXPIRED",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.FAILED

    async def test_abandoned_marks_failed(self):
        """ABANDONED status moves payment to FAILED."""
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "ABANDONED",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.FAILED

    async def test_stores_external_id(self):
        """handle_callback stores paymentId as external_id."""
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-XYZ-999",
            "externalId": "test-payment-123",
            "status": "CONFIRMED",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        assert payment.external_id == "PAY-XYZ-999"

    async def test_duplicate_callback_no_crash(self):
        """Duplicate callback on PAID payment does not crash."""
        payment = FakePayment(status=PaymentStatus.PAID)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "CONFIRMED",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        # may_trigger returns False, no crash
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.PAID

    async def test_callback_from_new_status(self):
        """Callback on NEW payment — confirm_payment not available
        from NEW, should not crash."""
        payment = FakePayment(status=PaymentStatus.NEW)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "CONFIRMED",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        # confirm_payment not available from NEW
        assert payment.status == PaymentStatus.NEW

    async def test_pending_no_state_change(self):
        """PENDING status does not trigger any FSM transition."""
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "PENDING",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.PREPARED

    async def test_new_status_no_state_change(self):
        """NEW status notification does not trigger any FSM
        transition."""
        payment = FakePayment(status=PaymentStatus.PREPARED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "NEW",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.PREPARED

    async def test_duplicate_failure_callback_no_crash(self):
        """Duplicate REJECTED callback on FAILED payment does
        not crash (MachineError suppressed)."""
        payment = FakePayment(status=PaymentStatus.FAILED)
        create_payment_machine(payment)

        processor = _make_processor(payment=payment)
        data = {
            "paymentId": "PAY-123",
            "externalId": "test-payment-123",
            "status": "REJECTED",
            "modifiedAt": "2025-01-15T10:30:00",
        }
        await processor.handle_callback(data=data, headers={})

        assert payment.status == PaymentStatus.FAILED
