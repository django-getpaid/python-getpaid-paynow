"""Tests for PaynowProcessor: prepare, fetch, callback, refund."""

import json
from decimal import Decimal

import pytest
from getpaid_core.exceptions import CommunicationError
from getpaid_core.exceptions import CredentialsError

from getpaid_paynow.processor import PaynowProcessor

from .conftest import PAYNOW_CONFIG
from .conftest import make_mock_payment


SANDBOX_URL = "https://api.sandbox.paynow.pl"
CREATE_PAYMENT_URL = f"{SANDBOX_URL}/v3/payments"
PAYMENT_METHODS_URL = f"{SANDBOX_URL}/v3/payments/paymentmethods"


def _make_processor(payment=None, config=None):
    """Create a PaynowProcessor with defaults."""
    if payment is None:
        payment = make_mock_payment()
    if config is None:
        config = PAYNOW_CONFIG.copy()
    return PaynowProcessor(payment=payment, config=config)


class TestClassAttributes:
    """Tests for PaynowProcessor class-level attributes."""

    def test_slug(self):
        assert PaynowProcessor.slug == "paynow"

    def test_display_name(self):
        assert PaynowProcessor.display_name == "Paynow"

    def test_accepted_currencies(self):
        currencies = PaynowProcessor.accepted_currencies
        assert "PLN" in currencies
        assert "EUR" in currencies
        assert "USD" in currencies
        assert "GBP" in currencies

    def test_sandbox_url(self):
        assert PaynowProcessor.sandbox_url == ("https://api.sandbox.paynow.pl")

    def test_production_url(self):
        assert PaynowProcessor.production_url == ("https://api.paynow.pl")


class TestInitialization:
    """Tests for processor initialization and settings."""

    def test_payment_stored(self):
        payment = make_mock_payment()
        processor = _make_processor(payment=payment)
        assert processor.payment is payment

    def test_config_stored(self):
        config = PAYNOW_CONFIG.copy()
        processor = _make_processor(config=config)
        assert processor.config == config

    def test_get_setting(self):
        processor = _make_processor()
        assert processor.get_setting("api_key") == (
            "97a55694-5478-43b5-b406-fb49ebfdd2b5"
        )

    def test_get_setting_default(self):
        processor = _make_processor()
        assert processor.get_setting("nonexistent", "default") == ("default")


class TestGetClient:
    """Tests for _get_client helper."""

    def test_creates_client_with_sandbox(self):
        processor = _make_processor()
        client = processor._get_client()
        assert client.api_url == SANDBOX_URL
        assert client.api_key == PAYNOW_CONFIG["api_key"]
        assert client.signature_key == (PAYNOW_CONFIG["signature_key"])

    def test_creates_client_with_production(self):
        config = PAYNOW_CONFIG.copy()
        config["sandbox"] = False
        processor = _make_processor(config=config)
        client = processor._get_client()
        assert client.api_url == "https://api.paynow.pl"


class TestBuildPaywallContext:
    """Tests for _build_paywall_context."""

    def test_builds_correct_structure(self):
        processor = _make_processor()
        context = processor._build_paywall_context()

        assert context["amount"] == Decimal("100.00")
        assert context["currency"] == "PLN"
        assert context["external_id"] == "test-payment-123"
        assert context["description"] == "Test order"
        assert context["buyer_email"] == "john@example.com"
        assert context["continue_url"] == (
            "https://shop.example.com/payments/success/test-payment-123"
        )

    def test_no_continue_url_if_not_configured(self):
        config = PAYNOW_CONFIG.copy()
        del config["continue_url"]
        processor = _make_processor(config=config)
        context = processor._build_paywall_context()
        assert "continue_url" not in context


class TestPrepareTransaction:
    """Tests for prepare_transaction."""

    async def test_prepare_returns_redirect(self, respx_mock):
        respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "redirectUrl": ("https://paywall.paynow.pl/pay/123"),
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=201,
        )
        processor = _make_processor()
        result = await processor.prepare_transaction()

        assert result["redirect_url"] == ("https://paywall.paynow.pl/pay/123")
        assert result["method"] == "GET"
        assert result["form_data"] is None

    async def test_prepare_sends_correct_data(self, respx_mock):
        route = respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "redirectUrl": ("https://paywall.paynow.pl/pay/123"),
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=201,
        )
        processor = _make_processor()
        await processor.prepare_transaction()

        body = json.loads(route.calls.last.request.content)
        assert body["amount"] == 10000  # 100.00 * 100
        assert body["currency"] == "PLN"
        assert body["externalId"] == "test-payment-123"
        assert body["description"] == "Test order"
        assert body["buyer"]["email"] == "john@example.com"
        assert body["continueUrl"] == (
            "https://shop.example.com/payments/success/test-payment-123"
        )

    async def test_prepare_stores_external_id(self, respx_mock):
        respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "redirectUrl": ("https://paywall.paynow.pl/pay/123"),
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=201,
        )
        payment = make_mock_payment()
        processor = _make_processor(payment=payment)
        await processor.prepare_transaction()

        assert payment.external_id == "PAY-123"

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
    """Tests for fetch_payment_status (PULL flow)."""

    async def test_status_confirmed(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "CONFIRMED",
            },
            status_code=200,
        )
        payment = make_mock_payment(external_id="PAY-123")
        processor = _make_processor(payment=payment)
        result = await processor.fetch_payment_status()
        assert result["status"] == "confirm_payment"

    async def test_status_rejected(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "REJECTED",
            },
            status_code=200,
        )
        payment = make_mock_payment(external_id="PAY-123")
        processor = _make_processor(payment=payment)
        result = await processor.fetch_payment_status()
        assert result["status"] == "fail"

    async def test_status_new(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=200,
        )
        payment = make_mock_payment(external_id="PAY-123")
        processor = _make_processor(payment=payment)
        result = await processor.fetch_payment_status()
        assert result["status"] is None

    async def test_status_pending(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "PENDING",
            },
            status_code=200,
        )
        payment = make_mock_payment(external_id="PAY-123")
        processor = _make_processor(payment=payment)
        result = await processor.fetch_payment_status()
        assert result["status"] == "confirm_prepared"

    async def test_status_error(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "ERROR",
            },
            status_code=200,
        )
        payment = make_mock_payment(external_id="PAY-123")
        processor = _make_processor(payment=payment)
        result = await processor.fetch_payment_status()
        assert result["status"] == "fail"

    async def test_status_expired(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "EXPIRED",
            },
            status_code=200,
        )
        payment = make_mock_payment(external_id="PAY-123")
        processor = _make_processor(payment=payment)
        result = await processor.fetch_payment_status()
        assert result["status"] == "fail"


class TestCharge:
    """Tests that charge() raises NotImplementedError."""

    async def test_charge_not_supported(self):
        processor = _make_processor()
        with pytest.raises(NotImplementedError):
            await processor.charge()


class TestReleaseLock:
    """Tests that release_lock() raises NotImplementedError."""

    async def test_release_lock_not_supported(self):
        processor = _make_processor()
        with pytest.raises(NotImplementedError):
            await processor.release_lock()


class TestStartRefund:
    """Tests for start_refund method."""

    async def test_start_refund_with_amount(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/refunds"
        respx_mock.post(url).respond(
            json={"refundId": "REF-456", "status": "NEW"},
            status_code=201,
        )
        payment = make_mock_payment(external_id="PAY-123")
        payment.amount_paid = Decimal("100.00")
        processor = _make_processor(payment=payment)
        result = await processor.start_refund(
            amount=Decimal("50.00"),
        )
        assert result == Decimal("50.00")
        assert payment.external_refund_id == "REF-456"

    async def test_start_refund_full_amount(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/refunds"
        respx_mock.post(url).respond(
            json={"refundId": "REF-456", "status": "NEW"},
            status_code=201,
        )
        payment = make_mock_payment(external_id="PAY-123")
        payment.amount_paid = Decimal("100.00")
        processor = _make_processor(payment=payment)
        result = await processor.start_refund()
        assert result == Decimal("100.00")
        assert payment.external_refund_id == "REF-456"

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


class TestCancelRefund:
    """Tests for cancel_refund method."""

    async def test_cancel_refund_success(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/refunds/REF-456/cancel"
        respx_mock.post(url).respond(status_code=200)
        payment = make_mock_payment()
        payment.external_refund_id = "REF-456"
        processor = _make_processor(payment=payment)
        result = await processor.cancel_refund()
        assert result is True

    async def test_cancel_refund_failure(self, respx_mock):
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
        payment = make_mock_payment()
        payment.external_refund_id = "REF-456"
        processor = _make_processor(payment=payment)
        with pytest.raises(CommunicationError):
            await processor.cancel_refund()
