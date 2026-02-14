"""Async HTTP client for Paynow V3 REST API."""

import base64
import hashlib
import hmac
import json
import uuid
from decimal import Decimal

import httpx
from getpaid_core.exceptions import CommunicationError
from getpaid_core.exceptions import CredentialsError
from getpaid_core.exceptions import RefundFailure

from .types import CreatePaymentResponse
from .types import CreateRefundResponse
from .types import PaymentMethodGroup
from .types import PaymentStatusResponse
from .types import RefundStatusResponse


class PaynowClient:
    """Async client for Paynow V3 REST API.

    Uses ``httpx.AsyncClient`` with API Key authentication and
    HMAC-SHA256 request signing. Can be used as an async context
    manager for connection reuse::

        async with PaynowClient(...) as client:
            await client.create_payment(...)
    """

    last_response: httpx.Response | None = None

    def __init__(
        self,
        *,
        api_key: str,
        signature_key: str,
        api_url: str,
    ) -> None:
        self.api_key = api_key
        self.signature_key = signature_key
        self.api_url = api_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self._owns_client: bool = False

    async def __aenter__(self) -> "PaynowClient":
        self._client = httpx.AsyncClient()
        self._owns_client = True
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None
            self._owns_client = False

    @staticmethod
    def _generate_idempotency_key() -> str:
        """Generate a unique idempotency key (max 45 chars)."""
        return str(uuid.uuid4())

    def _calculate_request_signature(
        self,
        *,
        api_key: str,
        idempotency_key: str,
        body: str,
        parameters: dict,
    ) -> str:
        """Calculate HMAC-SHA256 signature for API requests.

        Payload is a JSON object with keys ``headers``,
        ``parameters``, and ``body``, where headers and parameters
        are sorted alphabetically by key.

        :param api_key: The Api-Key header value.
        :param idempotency_key: The Idempotency-Key header value.
        :param body: JSON string of request body or empty string.
        :param parameters: Query parameters dict (may be empty).
        :return: Base64-encoded HMAC-SHA256 signature.
        """
        headers_dict = {
            "Api-Key": api_key,
            "Idempotency-Key": idempotency_key,
        }
        sorted_headers = dict(sorted(headers_dict.items()))
        sorted_params = dict(sorted(parameters.items()))

        payload = {
            "headers": sorted_headers,
            "parameters": sorted_params,
            "body": body,
        }
        payload_json = json.dumps(payload, separators=(",", ":"))
        digest = hmac.new(
            self.signature_key.encode(),
            payload_json.encode(),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode()

    def _calculate_notification_signature(self, body: str) -> str:
        """Calculate HMAC-SHA256 signature for notifications.

        Simpler than request signature — just HMAC of the raw body
        string with the signature key.

        :param body: Raw notification body string.
        :return: Base64-encoded HMAC-SHA256 signature.
        """
        digest = hmac.new(
            self.signature_key.encode(),
            body.encode(),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode()

    def _build_headers(
        self,
        *,
        idempotency_key: str,
        body: str = "",
        parameters: dict | None = None,
    ) -> dict[str, str]:
        """Build request headers with authentication and
        signature."""
        params = parameters or {}
        signature = self._calculate_request_signature(
            api_key=self.api_key,
            idempotency_key=idempotency_key,
            body=body,
            parameters=params,
        )
        return {
            "Api-Key": self.api_key,
            "Signature": signature,
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: str | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        """Execute an authenticated HTTP request."""
        url = f"{self.api_url}{path}"
        idempotency_key = self._generate_idempotency_key()

        # Convert params to string values for signature
        str_params: dict = {}
        if params:
            str_params = {k: str(v) for k, v in params.items()}

        headers = self._build_headers(
            idempotency_key=idempotency_key,
            body=body or "",
            parameters=str_params,
        )

        if self._client is not None:
            return await self._client.request(
                method,
                url,
                headers=headers,
                content=body,
                params=params,
            )
        async with httpx.AsyncClient() as client:
            return await client.request(
                method,
                url,
                headers=headers,
                content=body,
                params=params,
            )

    def _handle_error(self, response: httpx.Response) -> None:
        """Raise appropriate exception based on status code."""
        if response.status_code == 401:
            raise CredentialsError(
                "Paynow API authentication failed.",
                context={"raw_response": response},
            )
        raise CommunicationError(
            f"Paynow API error (HTTP {response.status_code}).",
            context={"raw_response": response},
        )

    @staticmethod
    def _to_lowest_unit(amount: Decimal) -> int:
        """Convert a Decimal amount to integer lowest currency
        unit."""
        return int(amount * 100)

    @staticmethod
    def _from_lowest_unit(amount: int) -> Decimal:
        """Convert integer lowest currency unit to Decimal."""
        return Decimal(amount) / 100

    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        external_id: str,
        description: str,
        buyer_email: str,
        continue_url: str | None = None,
        buyer_first_name: str | None = None,
        buyer_last_name: str | None = None,
        buyer_phone: str | None = None,
        validity_time: int | None = None,
        locale: str | None = None,
    ) -> CreatePaymentResponse:
        """Create a new payment.

        POST /v3/payments

        :param amount: Payment amount in main currency unit.
        :param currency: ISO 4217 currency code.
        :param external_id: Unique external ID (maps to
            payment.id).
        :param description: Payment description.
        :param buyer_email: Buyer email address.
        :return: Response with redirectUrl and paymentId.
        """
        amount_int = self._to_lowest_unit(amount)
        buyer: dict = {"email": buyer_email}
        if buyer_first_name is not None:
            buyer["firstName"] = buyer_first_name
        if buyer_last_name is not None:
            buyer["lastName"] = buyer_last_name
        if buyer_phone is not None:
            buyer["phone"] = buyer_phone

        data: dict = {
            "amount": amount_int,
            "currency": currency,
            "externalId": external_id,
            "description": description,
            "buyer": buyer,
        }
        if continue_url is not None:
            data["continueUrl"] = continue_url
        if validity_time is not None:
            data["validityTime"] = validity_time
        if locale is not None:
            data["locale"] = locale

        encoded = json.dumps(data, default=str)
        self.last_response = await self._request(
            "POST",
            "/v3/payments",
            body=encoded,
        )
        if self.last_response.status_code in (200, 201):
            return self.last_response.json()
        self._handle_error(self.last_response)
        # unreachable — _handle_error always raises
        raise AssertionError  # pragma: no cover

    async def get_payment_status(
        self,
        payment_id: str,
    ) -> PaymentStatusResponse:
        """Get payment status.

        GET /v3/payments/{paymentId}/status

        :param payment_id: Paynow payment ID.
        :return: Payment status response.
        """
        path = f"/v3/payments/{payment_id}/status"
        self.last_response = await self._request("GET", path)
        if self.last_response.status_code == 200:
            return self.last_response.json()
        self._handle_error(self.last_response)
        raise AssertionError  # pragma: no cover

    async def create_refund(
        self,
        *,
        payment_id: str,
        amount: Decimal,
        reason: str | None = None,
    ) -> CreateRefundResponse:
        """Create a refund.

        POST /v3/payments/{paymentId}/refunds

        :param payment_id: Paynow payment ID.
        :param amount: Refund amount in main currency unit.
        :param reason: Refund reason code.
        :return: Refund response.
        """
        amount_int = self._to_lowest_unit(amount)
        data: dict = {"amount": amount_int}
        if reason is not None:
            data["reason"] = reason

        encoded = json.dumps(data, default=str)
        path = f"/v3/payments/{payment_id}/refunds"
        self.last_response = await self._request(
            "POST",
            path,
            body=encoded,
        )
        if self.last_response.status_code in (200, 201):
            return self.last_response.json()
        if self.last_response.status_code == 401:
            raise CredentialsError(
                "Paynow API authentication failed.",
                context={"raw_response": self.last_response},
            )
        raise RefundFailure(
            "Error creating Paynow refund.",
            context={"raw_response": self.last_response},
        )

    async def get_refund_status(
        self,
        refund_id: str,
    ) -> RefundStatusResponse:
        """Get refund status.

        GET /v3/refunds/{refundId}/status

        :param refund_id: Paynow refund ID.
        :return: Refund status response.
        """
        path = f"/v3/refunds/{refund_id}/status"
        self.last_response = await self._request("GET", path)
        if self.last_response.status_code == 200:
            return self.last_response.json()
        self._handle_error(self.last_response)
        raise AssertionError  # pragma: no cover

    async def cancel_refund(
        self,
        refund_id: str,
    ) -> None:
        """Cancel an awaiting refund (only NEW status).

        POST /v3/refunds/{refundId}/cancel

        :param refund_id: Paynow refund ID.
        """
        path = f"/v3/refunds/{refund_id}/cancel"
        self.last_response = await self._request("POST", path)
        if self.last_response.status_code in (200, 202):
            return
        self._handle_error(self.last_response)

    async def get_payment_methods(
        self,
        *,
        amount: int | None = None,
        currency: str | None = None,
    ) -> list[PaymentMethodGroup]:
        """Get available payment methods.

        GET /v3/payments/paymentmethods

        :param amount: Optional amount filter (lowest currency
            unit).
        :param currency: Optional currency filter.
        :return: List of payment method groups.
        """
        params: dict = {}
        if amount is not None:
            params["amount"] = amount
        if currency is not None:
            params["currency"] = currency
        self.last_response = await self._request(
            "GET",
            "/v3/payments/paymentmethods",
            params=params or None,
        )
        if self.last_response.status_code == 200:
            return self.last_response.json()
        self._handle_error(self.last_response)
        raise AssertionError  # pragma: no cover
