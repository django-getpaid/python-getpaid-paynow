"""Paynow payment processor."""

import contextlib
import hmac as hmac_mod
import logging
from decimal import Decimal
from typing import ClassVar

from getpaid_core.exceptions import InvalidCallbackError
from getpaid_core.processor import BaseProcessor
from getpaid_core.types import ChargeResponse
from getpaid_core.types import PaymentStatusResponse
from getpaid_core.types import TransactionResult
from transitions.core import MachineError

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
            api_key=self.get_setting("api_key"),
            signature_key=self.get_setting("signature_key"),
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

        if payment_id:
            self.payment.external_id = payment_id

        return TransactionResult(
            redirect_url=redirect_url,
            form_data=None,
            method="GET",
            headers={},
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
        raw_body: str = kwargs.get("raw_body", "")
        received_sig = headers.get("Signature", "")

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
    ) -> None:
        """Handle Paynow notification and update FSM.

        Paynow sends notification on every status change.
        No separate verify step is needed. The flow:
        1. Extract paymentId and status from notification
        2. Store paymentId as external_id
        3. Map Paynow status to FSM transition

        Notifications may arrive multiple times and out of order.
        Uses ``contextlib.suppress(MachineError)`` for idempotent
        transitions.
        """
        payment_id: str = data.get("paymentId", "")
        paynow_status: str = data.get("status", "")

        if payment_id:
            self.payment.external_id = payment_id

        if paynow_status == PaynowPaymentStatus.CONFIRMED:
            if self.payment.may_trigger("confirm_payment"):
                self.payment.confirm_payment()
                with contextlib.suppress(MachineError):
                    self.payment.mark_as_paid()
            else:
                logger.debug(
                    "Cannot confirm payment %s (status: %s)",
                    self.payment.id,
                    self.payment.status,
                )
        elif paynow_status in (
            PaynowPaymentStatus.REJECTED,
            PaynowPaymentStatus.ERROR,
            PaynowPaymentStatus.EXPIRED,
            PaynowPaymentStatus.ABANDONED,
        ):
            if hasattr(self.payment, "fail"):
                with contextlib.suppress(MachineError):
                    self.payment.fail()
        else:
            logger.debug(
                "Paynow status %s for payment %s — no FSM action",
                paynow_status,
                self.payment.id,
            )

    async def fetch_payment_status(self, **kwargs) -> PaymentStatusResponse:
        """PULL flow: fetch payment status from Paynow API."""
        client = self._get_client()
        response = await client.get_payment_status(
            self.payment.external_id,
        )
        paynow_status = response.get("status", "")

        status_map: dict[str, str | None] = {
            PaynowPaymentStatus.NEW: None,
            PaynowPaymentStatus.PENDING: "confirm_prepared",
            PaynowPaymentStatus.CONFIRMED: "confirm_payment",
            PaynowPaymentStatus.REJECTED: "fail",
            PaynowPaymentStatus.ERROR: "fail",
            PaynowPaymentStatus.EXPIRED: "fail",
            PaynowPaymentStatus.ABANDONED: "fail",
        }

        return PaymentStatusResponse(
            status=status_map.get(paynow_status),
        )

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
    ) -> Decimal:
        """Start a refund via Paynow API."""
        client = self._get_client()
        refund_amount = amount or self.payment.amount_paid
        await client.create_refund(
            payment_id=self.payment.external_id,
            amount=refund_amount,
        )
        return refund_amount

    async def cancel_refund(self, **kwargs) -> bool:
        """Cancel an awaiting refund via Paynow API."""
        client = self._get_client()
        refund_id = getattr(self.payment, "external_refund_id", "")
        await client.cancel_refund(refund_id)
        return True
