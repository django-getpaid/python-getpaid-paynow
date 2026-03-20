"""Paynow payment processor."""

import hmac as hmac_mod
import logging
from decimal import Decimal
from typing import ClassVar

from getpaid_core.enums import PaymentEvent
from getpaid_core.exceptions import InvalidCallbackError
from getpaid_core.processor import BaseProcessor
from getpaid_core.types import ChargeResponse
from getpaid_core.types import PaymentUpdate
from getpaid_core.types import RefundResult
from getpaid_core.types import TransactionResult

from .client import PaynowClient
from .types import Currency
from .types import PaymentStatus as PaynowPaymentStatus


logger = logging.getLogger(__name__)


class PaynowProcessor(BaseProcessor):
    """Paynow V3 payment gateway processor.

    Paynow uses a notification-based (PUSH) flow:
    create payment -> redirect -> notification -> done.
    No separate verification step is needed (unlike P24).

    Paynow has no pre-authorization flow — only direct payment.
    Therefore ``charge()`` and ``release_lock()`` raise
    ``NotImplementedError``.
    """

    slug: ClassVar[str] = "paynow"
    display_name: ClassVar[str] = "Paynow"
    accepted_currencies: ClassVar[list[str]] = [c.value for c in Currency]
    sandbox_url: ClassVar[str] = "https://api.sandbox.paynow.pl"
    production_url: ClassVar[str] = "https://api.paynow.pl"

    def _get_client(self) -> PaynowClient:
        """Create a PaynowClient from processor config."""
        return PaynowClient(
            api_key=str(self.get_setting("api_key", "")),
            signature_key=str(self.get_setting("signature_key", "")),
            api_url=self.get_paywall_baseurl(),
        )

    def _resolve_url(self, url_template: str) -> str:
        """Replace {payment_id} placeholder."""
        return url_template.format(payment_id=self.payment.id)

    def _build_paywall_context(self, **kwargs) -> dict:
        """Build Paynow payment creation data from payment."""
        buyer = self.payment.order.get_buyer_info()

        context: dict = {
            "amount": self.payment.amount_required,
            "currency": self.payment.currency,
            "external_id": self.payment.id,
            "description": self.payment.description,
            "buyer_email": buyer.get("email", ""),
        }

        first_name = buyer.get("first_name")
        if first_name:
            context["buyer_first_name"] = first_name

        last_name = buyer.get("last_name")
        if last_name:
            context["buyer_last_name"] = last_name

        continue_url_template = self.get_setting("continue_url", "")
        if continue_url_template:
            context["continue_url"] = self._resolve_url(
                continue_url_template,
            )

        return context

    async def prepare_transaction(self, **kwargs) -> TransactionResult:
        """Prepare a Paynow payment — create and get redirect."""
        client = self._get_client()
        context = self._build_paywall_context(**kwargs)
        response = await client.create_payment(**context)

        redirect_url = response.get("redirectUrl", "")
        payment_id = response.get("paymentId", "")
        provider_data = {"paynow_status": response.get("status", "")}

        return TransactionResult(
            method="GET",
            redirect_url=redirect_url or None,
            external_id=payment_id or None,
            provider_data=provider_data,
        )

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        """Verify Paynow notification HMAC signature.

        Compares the Signature header against HMAC-SHA256 of the
        raw body with the Signature-Key.

        :param data: Parsed notification payload.
        :param headers: HTTP headers (must include 'Signature').
        :raises InvalidCallbackError: On missing/invalid signature.
        """
        raw_body = kwargs.get("raw_body")
        if raw_body is None:
            raise InvalidCallbackError(
                "Missing raw_body in callback kwargs. "
                "The framework adapter must pass the raw HTTP body."
            )
        if isinstance(raw_body, (bytes, bytearray)):
            raw_body = raw_body.decode("utf-8")
        if not isinstance(raw_body, str):
            raise InvalidCallbackError("raw_body must be a str or bytes value.")

        received_sig = ""
        for key, value in headers.items():
            if key.lower() == "signature":
                received_sig = value
                break

        if not received_sig:
            raise InvalidCallbackError(
                "Missing Signature header in notification",
            )

        client = self._get_client()
        expected_sig = client._calculate_notification_signature(raw_body)

        if not hmac_mod.compare_digest(expected_sig, received_sig):
            logger.error(
                "Paynow notification bad signature for "
                "payment %s! Got '%s', expected '%s'",
                self.payment.id,
                received_sig,
                expected_sig,
            )
            raise InvalidCallbackError(
                f"BAD SIGNATURE: got '{received_sig}', "
                f"expected '{expected_sig}'"
            )

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> PaymentUpdate | None:
        """Handle Paynow notification and return a semantic update."""
        payment_id: str = data.get("paymentId", "")
        paynow_status: str = data.get("status", "")
        modified_at: str = data.get("modifiedAt", "")
        provider_event_id = (
            ":".join(
                part
                for part in (payment_id, paynow_status, modified_at)
                if part
            )
            or None
        )
        provider_data = {"paynow_status": paynow_status}
        external_id = payment_id or self.payment.external_id

        if paynow_status == PaynowPaymentStatus.CONFIRMED:
            return PaymentUpdate(
                payment_event=PaymentEvent.PAYMENT_CAPTURED,
                paid_amount=self.payment.amount_required,
                external_id=external_id,
                provider_event_id=provider_event_id,
                provider_data=provider_data,
            )
        elif paynow_status in (
            PaynowPaymentStatus.REJECTED,
            PaynowPaymentStatus.ERROR,
            PaynowPaymentStatus.EXPIRED,
            PaynowPaymentStatus.ABANDONED,
        ):
            return PaymentUpdate(
                payment_event=PaymentEvent.FAILED,
                external_id=external_id,
                provider_event_id=provider_event_id,
                provider_data=provider_data,
            )
        return PaymentUpdate(
            external_id=external_id,
            provider_event_id=provider_event_id,
            provider_data=provider_data,
        )

    async def fetch_payment_status(self, **kwargs) -> PaymentUpdate | None:
        """PULL flow: fetch payment status from Paynow API."""
        client = self._get_client()
        response = await client.get_payment_status(
            self.payment.external_id,
        )
        payment_id = response.get("paymentId") or self.payment.external_id
        paynow_status = response.get("status", "")

        provider_data = {"paynow_status": paynow_status}
        if paynow_status == PaynowPaymentStatus.CONFIRMED:
            return PaymentUpdate(
                payment_event=PaymentEvent.PAYMENT_CAPTURED,
                paid_amount=self.payment.amount_required,
                external_id=payment_id,
                provider_event_id=f"poll:{payment_id}:{paynow_status}",
                provider_data=provider_data,
            )
        if paynow_status in {
            PaynowPaymentStatus.REJECTED,
            PaynowPaymentStatus.ERROR,
            PaynowPaymentStatus.EXPIRED,
            PaynowPaymentStatus.ABANDONED,
        }:
            return PaymentUpdate(
                payment_event=PaymentEvent.FAILED,
                external_id=payment_id,
                provider_event_id=f"poll:{payment_id}:{paynow_status}",
                provider_data=provider_data,
            )
        return None

    async def charge(
        self, amount: Decimal | None = None, **kwargs
    ) -> ChargeResponse:
        """Not supported by Paynow (no pre-auth flow)."""
        raise NotImplementedError(
            "Paynow does not support pre-authorization/charge flow"
        )

    async def release_lock(self, **kwargs) -> Decimal:
        """Not supported by Paynow (no pre-auth flow)."""
        raise NotImplementedError(
            "Paynow does not support pre-authorization/release flow"
        )

    async def start_refund(
        self, amount: Decimal | None = None, **kwargs
    ) -> RefundResult:
        """Start a refund via Paynow API."""
        client = self._get_client()
        refund_amount = amount or self.payment.amount_paid
        response = await client.create_refund(
            payment_id=self.payment.external_id,
            amount=refund_amount,
        )
        refund_id = response.get("refundId", "")
        provider_data = {}
        if refund_id:
            provider_data["refund_id"] = refund_id
        return RefundResult(amount=refund_amount, provider_data=provider_data)

    async def cancel_refund(self, **kwargs) -> bool:
        """Cancel an awaiting refund via Paynow API."""
        client = self._get_client()
        refund_id = self.payment.provider_data.get("refund_id")
        if not refund_id:
            refund_id = getattr(self.payment, "external_refund_id", "")
        if not refund_id:
            raise InvalidCallbackError("Missing refund identifier")
        await client.cancel_refund(refund_id)
        return True
