"""Comprehensive tests for PaynowClient."""

import json
from decimal import Decimal

import pytest
from getpaid_core.exceptions import CommunicationError
from getpaid_core.exceptions import CredentialsError
from getpaid_core.exceptions import RefundFailure

from getpaid_paynow.client import PaynowClient


SANDBOX_URL = "https://api.sandbox.paynow.pl"
CREATE_PAYMENT_URL = f"{SANDBOX_URL}/v3/payments"
PAYMENT_METHODS_URL = f"{SANDBOX_URL}/v3/payments/paymentmethods"

# Paynow documented test credentials
TEST_API_KEY = "97a55694-5478-43b5-b406-fb49ebfdd2b5"
TEST_SIGNATURE_KEY = "b305b996-bca5-4404-a0b7-2ccea3d2b64b"


def _make_client(
    *,
    api_key: str = TEST_API_KEY,
    signature_key: str = TEST_SIGNATURE_KEY,
    api_url: str = SANDBOX_URL,
) -> PaynowClient:
    return PaynowClient(
        api_key=api_key,
        signature_key=signature_key,
        api_url=api_url,
    )


class TestRequestSignature:
    """Tests for _calculate_request_signature using Paynow docs
    test vectors."""

    def test_empty_body_empty_params(self):
        """Known test vector from Paynow docs:
        Api-Key + Idempotency-Key, empty body, empty params."""
        client = _make_client()
        sig = client._calculate_request_signature(
            api_key=TEST_API_KEY,
            idempotency_key=("d243fdb3-c287-484a-bb9c-58536f2794c1"),
            body="",
            parameters={},
        )
        assert sig == "fXwLZRwo0WiGll90PPl5oULX9VKA0gpFA/3+E+NRp5E="

    def test_with_body(self):
        """Signature should change when body is provided."""
        client = _make_client()
        sig_empty = client._calculate_request_signature(
            api_key=TEST_API_KEY,
            idempotency_key="test-key",
            body="",
            parameters={},
        )
        sig_body = client._calculate_request_signature(
            api_key=TEST_API_KEY,
            idempotency_key="test-key",
            body='{"amount":10000}',
            parameters={},
        )
        assert sig_empty != sig_body

    def test_with_parameters(self):
        """Signature should include query parameters."""
        client = _make_client()
        sig_no_params = client._calculate_request_signature(
            api_key=TEST_API_KEY,
            idempotency_key="test-key",
            body="",
            parameters={},
        )
        sig_params = client._calculate_request_signature(
            api_key=TEST_API_KEY,
            idempotency_key="test-key",
            body="",
            parameters={"amount": "10000", "currency": "PLN"},
        )
        assert sig_no_params != sig_params

    def test_parameters_sorted_alphabetically(self):
        """Parameters should be sorted for deterministic
        signatures."""
        client = _make_client()
        sig1 = client._calculate_request_signature(
            api_key=TEST_API_KEY,
            idempotency_key="test-key",
            body="",
            parameters={"currency": "PLN", "amount": "10000"},
        )
        sig2 = client._calculate_request_signature(
            api_key=TEST_API_KEY,
            idempotency_key="test-key",
            body="",
            parameters={"amount": "10000", "currency": "PLN"},
        )
        assert sig1 == sig2


class TestNotificationSignature:
    """Tests for _calculate_notification_signature using Paynow
    docs test vector."""

    def test_known_vector(self):
        """Known test vector from Paynow docs (integration page,
        notification curl example with pretty-printed JSON body,
        4-space indent, no indent on closing brace)."""
        client = _make_client(signature_key=TEST_SIGNATURE_KEY)
        body = (
            "{\n"
            '    "paymentId": "NOLV-8F9-08K-WGD",\n'
            '    "externalId": '
            '"9fea23c7-cd5c-4884-9842-6f8592be65df",\n'
            '    "status": "CONFIRMED",\n'
            '    "modifiedAt": "2018-12-12T13:24:52"\n'
            "}"
        )
        sig = client._calculate_notification_signature(body)
        assert sig == ("F69sbjUxBX4eFjfUal/Y9XGREbfaRjh/zdq9j4MWeHM=")

    def test_different_body_different_signature(self):
        """Different body content should produce different
        signature."""
        client = _make_client()
        sig1 = client._calculate_notification_signature(
            '{"status":"CONFIRMED"}'
        )
        sig2 = client._calculate_notification_signature('{"status":"REJECTED"}')
        assert sig1 != sig2


class TestAmountConversion:
    """Tests for _to_lowest_unit and _from_lowest_unit."""

    def test_to_lowest_unit_decimal(self):
        assert PaynowClient._to_lowest_unit(Decimal("1.23")) == 123

    def test_to_lowest_unit_integer(self):
        assert PaynowClient._to_lowest_unit(Decimal("100")) == 10000

    def test_to_lowest_unit_small(self):
        assert PaynowClient._to_lowest_unit(Decimal("0.01")) == 1

    def test_from_lowest_unit(self):
        assert PaynowClient._from_lowest_unit(123) == Decimal("1.23")

    def test_from_lowest_unit_large(self):
        result = PaynowClient._from_lowest_unit(10000)
        assert result == Decimal("100.00")


class TestCreatePayment:
    """Tests for create_payment."""

    async def test_create_payment_success(self, respx_mock):
        respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "redirectUrl": "https://paywall.paynow.pl/pay/123",
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=201,
        )
        client = _make_client()
        result = await client.create_payment(
            amount=Decimal("49.99"),
            currency="PLN",
            external_id="order-001",
            description="Order #001",
            buyer_email="buyer@example.com",
        )
        assert result["redirectUrl"] == ("https://paywall.paynow.pl/pay/123")
        assert result["paymentId"] == "PAY-123"
        assert result["status"] == "NEW"

    async def test_create_payment_sends_correct_body(self, respx_mock):
        route = respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "redirectUrl": "https://paywall.paynow.pl/pay/123",
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=201,
        )
        client = _make_client()
        await client.create_payment(
            amount=Decimal("49.99"),
            currency="PLN",
            external_id="order-001",
            description="Order #001",
            buyer_email="buyer@example.com",
            continue_url="https://shop.example.com/return",
        )
        body = json.loads(route.calls.last.request.content)
        assert body["amount"] == 4999
        assert body["currency"] == "PLN"
        assert body["externalId"] == "order-001"
        assert body["description"] == "Order #001"
        assert body["buyer"]["email"] == "buyer@example.com"
        assert body["continueUrl"] == ("https://shop.example.com/return")

    async def test_create_payment_sends_correct_headers(self, respx_mock):
        route = respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "redirectUrl": "https://paywall.paynow.pl/pay/123",
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=201,
        )
        client = _make_client()
        await client.create_payment(
            amount=Decimal("10.00"),
            currency="PLN",
            external_id="order-001",
            description="Test",
            buyer_email="test@example.com",
        )
        request = route.calls.last.request
        assert request.headers["Api-Key"] == TEST_API_KEY
        assert "Signature" in request.headers
        assert "Idempotency-Key" in request.headers
        assert request.headers["Content-Type"] == "application/json"
        assert request.headers["Accept"] == "application/json"

    async def test_create_payment_with_optional_params(self, respx_mock):
        route = respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "redirectUrl": "https://paywall.paynow.pl/pay/123",
                "paymentId": "PAY-123",
                "status": "NEW",
            },
            status_code=201,
        )
        client = _make_client()
        await client.create_payment(
            amount=Decimal("10.00"),
            currency="PLN",
            external_id="order-001",
            description="Test",
            buyer_email="test@example.com",
            buyer_first_name="John",
            buyer_last_name="Doe",
            validity_time=900,
        )
        body = json.loads(route.calls.last.request.content)
        assert body["buyer"]["firstName"] == "John"
        assert body["buyer"]["lastName"] == "Doe"
        assert body["validityTime"] == 900

    async def test_create_payment_auth_failure(self, respx_mock):
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
        client = _make_client()
        with pytest.raises(CredentialsError):
            await client.create_payment(
                amount=Decimal("10.00"),
                currency="PLN",
                external_id="order-001",
                description="Test",
                buyer_email="test@example.com",
            )

    async def test_create_payment_validation_error(self, respx_mock):
        respx_mock.post(CREATE_PAYMENT_URL).respond(
            json={
                "statusCode": 400,
                "errors": [
                    {
                        "errorType": "VALIDATION_ERROR",
                        "message": "Amount too small",
                    }
                ],
            },
            status_code=400,
        )
        client = _make_client()
        with pytest.raises(CommunicationError):
            await client.create_payment(
                amount=Decimal("0.10"),
                currency="PLN",
                external_id="order-001",
                description="Test",
                buyer_email="test@example.com",
            )

    async def test_create_payment_server_error(self, respx_mock):
        respx_mock.post(CREATE_PAYMENT_URL).respond(
            status_code=500,
            json={
                "statusCode": 500,
                "errors": [
                    {
                        "errorType": ("SYSTEM_TEMPORARILY_UNAVAILABLE"),
                        "message": "Try again later",
                    }
                ],
            },
        )
        client = _make_client()
        with pytest.raises(CommunicationError):
            await client.create_payment(
                amount=Decimal("10.00"),
                currency="PLN",
                external_id="order-001",
                description="Test",
                buyer_email="test@example.com",
            )


class TestGetPaymentStatus:
    """Tests for get_payment_status."""

    async def test_get_status_success(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "CONFIRMED",
            },
            status_code=200,
        )
        client = _make_client()
        result = await client.get_payment_status("PAY-123")
        assert result["paymentId"] == "PAY-123"
        assert result["status"] == "CONFIRMED"

    async def test_get_status_sends_headers(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        route = respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "CONFIRMED",
            },
            status_code=200,
        )
        client = _make_client()
        await client.get_payment_status("PAY-123")
        request = route.calls.last.request
        assert request.headers["Api-Key"] == TEST_API_KEY
        assert "Signature" in request.headers
        assert "Idempotency-Key" in request.headers

    async def test_get_status_failure(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            status_code=404,
            json={
                "statusCode": 404,
                "errors": [
                    {
                        "errorType": "NOT_FOUND",
                        "message": "Payment not found",
                    }
                ],
            },
        )
        client = _make_client()
        with pytest.raises(CommunicationError):
            await client.get_payment_status("PAY-123")


class TestCreateRefund:
    """Tests for create_refund."""

    async def test_create_refund_success(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/refunds"
        respx_mock.post(url).respond(
            json={"refundId": "REF-456", "status": "NEW"},
            status_code=201,
        )
        client = _make_client()
        result = await client.create_refund(
            payment_id="PAY-123",
            amount=Decimal("10.00"),
            reason="OTHER",
        )
        assert result["refundId"] == "REF-456"
        assert result["status"] == "NEW"

    async def test_create_refund_sends_correct_body(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/refunds"
        route = respx_mock.post(url).respond(
            json={"refundId": "REF-456", "status": "NEW"},
            status_code=201,
        )
        client = _make_client()
        await client.create_refund(
            payment_id="PAY-123",
            amount=Decimal("5.50"),
            reason="RMA",
        )
        body = json.loads(route.calls.last.request.content)
        assert body["amount"] == 550
        assert body["reason"] == "RMA"

    async def test_create_refund_failure(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/refunds"
        respx_mock.post(url).respond(
            status_code=400,
            json={
                "statusCode": 400,
                "errors": [
                    {
                        "errorType": "VALIDATION_ERROR",
                        "message": "Refund amount exceeds payment",
                    }
                ],
            },
        )
        client = _make_client()
        with pytest.raises(RefundFailure):
            await client.create_refund(
                payment_id="PAY-123",
                amount=Decimal("10.00"),
            )


class TestGetRefundStatus:
    """Tests for get_refund_status."""

    async def test_get_refund_status_success(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/refunds/REF-456/status"
        respx_mock.get(url).respond(
            json={"refundId": "REF-456", "status": "SUCCESSFUL"},
            status_code=200,
        )
        client = _make_client()
        result = await client.get_refund_status("REF-456")
        assert result["refundId"] == "REF-456"
        assert result["status"] == "SUCCESSFUL"

    async def test_get_refund_status_failure(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/refunds/REF-456/status"
        respx_mock.get(url).respond(
            status_code=404,
            json={
                "statusCode": 404,
                "errors": [
                    {
                        "errorType": "NOT_FOUND",
                        "message": "Refund not found",
                    }
                ],
            },
        )
        client = _make_client()
        with pytest.raises(CommunicationError):
            await client.get_refund_status("REF-456")


class TestCancelRefund:
    """Tests for cancel_refund."""

    async def test_cancel_refund_success(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/refunds/REF-456/cancel"
        respx_mock.post(url).respond(status_code=200)
        client = _make_client()
        await client.cancel_refund("REF-456")

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
        client = _make_client()
        with pytest.raises(CommunicationError):
            await client.cancel_refund("REF-456")


class TestGetPaymentMethods:
    """Tests for get_payment_methods."""

    async def test_get_methods_success(self, respx_mock):
        respx_mock.get(PAYMENT_METHODS_URL).respond(
            json=[
                {
                    "type": "BLIK",
                    "paymentMethods": [
                        {
                            "id": 1,
                            "name": "BLIK",
                            "description": "BLIK payment",
                            "image": "https://img.paynow.pl/blik",
                            "status": "ENABLED",
                            "authorizationType": "CODE",
                        }
                    ],
                }
            ],
            status_code=200,
        )
        client = _make_client()
        result = await client.get_payment_methods()
        assert len(result) == 1
        assert result[0]["type"] == "BLIK"

    async def test_get_methods_with_filters(self, respx_mock):
        route = respx_mock.get(PAYMENT_METHODS_URL).respond(
            json=[],
            status_code=200,
        )
        client = _make_client()
        await client.get_payment_methods(amount=10000, currency="PLN")
        request_url = str(route.calls.last.request.url)
        assert "amount=10000" in request_url
        assert "currency=PLN" in request_url

    async def test_get_methods_failure(self, respx_mock):
        respx_mock.get(PAYMENT_METHODS_URL).respond(
            status_code=401,
            json={
                "statusCode": 401,
                "errors": [
                    {
                        "errorType": "UNAUTHORIZED",
                        "message": "Invalid API key",
                    }
                ],
            },
        )
        client = _make_client()
        with pytest.raises(CredentialsError):
            await client.get_payment_methods()


class TestAsyncContextManager:
    """Tests for async context manager protocol."""

    async def test_context_manager(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "CONFIRMED",
            },
            status_code=200,
        )
        async with _make_client() as client:
            result = await client.get_payment_status("PAY-123")
            assert result["status"] == "CONFIRMED"

    async def test_context_manager_creates_and_closes_client(self):
        client = _make_client()
        assert client._client is None
        async with client:
            assert client._client is not None
            assert client._owns_client is True
        assert client._client is None
        assert client._owns_client is False

    async def test_last_response_tracked(self, respx_mock):
        url = f"{SANDBOX_URL}/v3/payments/PAY-123/status"
        respx_mock.get(url).respond(
            json={
                "paymentId": "PAY-123",
                "status": "CONFIRMED",
            },
            status_code=200,
        )
        client = _make_client()
        assert client.last_response is None
        await client.get_payment_status("PAY-123")
        assert client.last_response is not None
        assert client.last_response.status_code == 200
