"""Tests for PaynowProcessor prepare, status polling, and refunds."""

import json
from decimal import Decimal

import pytest

from getpaid_core.enums import BackendMethod
from getpaid_core.enums import PaymentEvent
from getpaid_core.exceptions import CommunicationError
from getpaid_core.exceptions import CredentialsError

from getpaid_paynow.processor import PaynowProcessor

from .conftest import PAYNOW_CONFIG
from .conftest import make_mock_payment


SANDBOX_URL = "https://api.sandbox.paynow.pl"
CREATE_PAYMENT_URL = f"{SANDBOX_URL}/v3/payments"


def _make_processor(payment=None, config=None):
    if payment is None:
        payment = make_mock_payment()
    if config is None:
        config = PAYNOW_CONFIG.copy()
    return PaynowProcessor(payment=payment, config=config)


class TestPrepareTransaction:
    async def test_prepare_returns_redirect_and_external_id(self, respx_mock):
        respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "redirectUrl": "https://paywall.paynow.pl/pay/123",
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=201,
        )
        processor = _make_processor()

        result = await processor.prepare_transaction()

        assert result.redirect_url == "https://paywall.paynow.pl/pay/123"
        assert result.method is BackendMethod.GET
        assert result.external_id == "PAY-123"

    async def test_prepare_sends_correct_data(self, respx_mock):
        route = respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "redirectUrl": "https://paywall.paynow.pl/pay/123",
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=201,
        )
        processor = _make_processor()

        await processor.prepare_transaction()

        body = json.loads(route.calls.last.request.content)
        assert body["amount"] == 10000
        assert body["currency"] == "PLN"
        assert body["externalId"] == "test-payment-123"
        assert body["description"] == "Test order"
        assert body["buyer"]["email"] == "john@example.com"

    async def test_prepare_failure_raises(self, respx_mock):
        respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "statusCode": 401,
                "errors": [
                    {
                        "errorType": "UNAUTHORIZED",
                        "message": "Invalid API key",
                    }
                ],
            },
            status_code=401,
        )
        processor = _make_processor()

        with pytest.raises(CredentialsError):
            await processor.prepare_transaction()


class TestFetchPaymentStatus:
    async def test_status_confirmed_returns_capture_update(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={"paymentId": "PAY-123", "status": "CONFIRMED"},
            status_code=200,
        )
        processor = _make_processor(
            payment=make_mock_payment(external_id="PAY-123")
        )

        result = await processor.fetch_payment_status()

        assert result is not None
        assert result.payment_event is PaymentEvent.PAYMENT_CAPTURED
        assert result.external_id == "PAY-123"

    async def test_status_rejected_returns_failure_update(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={"paymentId": "PAY-123", "status": "REJECTED"},
            status_code=200,
        )
        processor = _make_processor(
            payment=make_mock_payment(external_id="PAY-123")
        )

        result = await processor.fetch_payment_status()

        assert result is not None
        assert result.payment_event is PaymentEvent.FAILED

    async def test_status_pending_returns_none(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={"paymentId": "PAY-123", "status": "PENDING"},
            status_code=200,
        )
        processor = _make_processor(
            payment=make_mock_payment(external_id="PAY-123")
        )

        result = await processor.fetch_payment_status()

        assert result is None


class TestUnsupportedOperations:
    async def test_charge_not_supported(self):
        with pytest.raises(NotImplementedError):
            await _make_processor().charge()

    async def test_release_lock_not_supported(self):
        with pytest.raises(NotImplementedError):
            await _make_processor().release_lock()


class TestRefunds:
    async def test_start_refund_with_amount_returns_refund_result(
        self, respx_mock
    ):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/refunds"
        respx_mock.post(url).respond(
            json={"refundId": "REF-456", "status": "NEW"},
            status_code=201,
        )
        payment = make_mock_payment(external_id="PAY-123")
        payment.amount_paid = Decimal("100.00")
        processor = _make_processor(payment=payment)

        result = await processor.start_refund(amount=Decimal("50.00"))

        assert result.amount == Decimal("50.00")
        assert result.provider_data["refund_id"] == "REF-456"

    async def test_start_refund_sends_correct_body(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/refunds"
        route = respx_mock.post(url).respond(
            json={"refundId": "REF-456", "status": "NEW"},
            status_code=201,
        )
        payment = make_mock_payment(external_id="PAY-123")
        payment.amount_paid = Decimal("100.00")
        processor = _make_processor(payment=payment)

        await processor.start_refund(amount=Decimal("50.00"))

        body = json.loads(route.calls.last.request.content)
        assert body["amount"] == 5000

    async def test_cancel_refund_reads_refund_id_from_provider_data(
        self, respx_mock
    ):
        url = f"{SANDBOX_URL}/v3/refunds/REF-456/cancel"
        respx_mock.post(url).respond(status_code=200)
        payment = make_mock_payment(provider_data={"refund_id": "REF-456"})
        processor = _make_processor(payment=payment)

        result = await processor.cancel_refund()

        assert result is True

    async def test_cancel_refund_failure_raises(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/refunds/REF-456/cancel"
        respx_mock.post(url).respond(
            status_code=409,
            json={
                "statusCode": 409,
                "errors": [
                    {
                        "errorType": "CONFLICT",
                        "message": "Refund already processed",
                    }
                ],
            },
        )
        payment = make_mock_payment(provider_data={"refund_id": "REF-456"})
        processor = _make_processor(payment=payment)

        with pytest.raises(CommunicationError):
            await processor.cancel_refund()
