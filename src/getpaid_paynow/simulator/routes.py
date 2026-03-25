"""PayNow simulator routes."""

from __future__ import annotations

import logging
from decimal import Decimal
from decimal import InvalidOperation
from typing import Any
from typing import TypedDict
from typing import cast

from litestar import Request
from litestar import get
from litestar import post
from litestar.enums import MediaType
from litestar.enums import RequestEncodingType
from litestar.exceptions import HTTPException
from litestar.exceptions import NotFoundException
from litestar.params import Body
from litestar.response import Redirect
from litestar.response import Response
from litestar.response import Template

from getpaid_paynow.simulator.webhooks import trigger_paynow_webhook


logger = logging.getLogger(__name__)
URL_ENCODED_BODY = Body(media_type=RequestEncodingType.URL_ENCODED)

PAYNOW_STATUSES = {
    "NEW",
    "PENDING",
    "CONFIRMED",
    "REJECTED",
    "ERROR",
    "EXPIRED",
    "ABANDONED",
}


class PaynowError(TypedDict):
    errorType: str
    message: str


class BuyerData(TypedDict, total=False):
    email: str


class PaymentMethod(TypedDict):
    id: int
    name: str
    description: str
    image: str
    status: str
    authorizationType: str


class PaymentMethodGroup(TypedDict):
    type: str
    paymentMethods: list[PaymentMethod]


class CreatePaymentPayload(TypedDict, total=False):
    amount: int
    currency: str
    externalId: str
    description: str
    buyer: BuyerData
    status: str


PAYMENT_METHODS: list[PaymentMethodGroup] = [
    {
        "type": "PBL",
        "paymentMethods": [
            {
                "id": 2001,
                "name": "mTransfer",
                "description": "mBank",
                "image": "https://static.paynow.pl/payment-method-icons/2001.png",
                "status": "ENABLED",
                "authorizationType": "REDIRECT",
            }
        ],
    },
    {
        "type": "CARD",
        "paymentMethods": [
            {
                "id": 3001,
                "name": "Visa",
                "description": "Visa",
                "image": "https://static.paynow.pl/payment-method-icons/3001.png",
                "status": "ENABLED",
                "authorizationType": "REDIRECT",
            }
        ],
    },
    {
        "type": "BLIK",
        "paymentMethods": [
            {
                "id": 5001,
                "name": "BLIK",
                "description": "BLIK",
                "image": "https://static.paynow.pl/payment-method-icons/5001.png",
                "status": "ENABLED",
                "authorizationType": "CODE",
            }
        ],
    },
]


def _provider_config(request: Request[Any, Any, Any]) -> dict[str, Any]:
    return dict(request.app.state.provider_configs["paynow"])


def _format_amount_for_display(
    payment: dict[str, Any],
    provider_config: dict[str, Any],
) -> str:
    amount_raw = payment.get("amount", payment.get("totalAmount", 0))
    try:
        amount_value = Decimal(str(amount_raw))
    except (InvalidOperation, TypeError, ValueError):
        return str(amount_raw)

    minor_unit_places = int(provider_config.get("amount_minor_unit_places", 2))
    if minor_unit_places >= 0:
        amount_value /= Decimal(10) ** minor_unit_places

    currency = payment.get("currency", payment.get("currencyCode", "PLN"))
    return f"{amount_value:.2f} {currency}"


def _error_response(
    status_code: int,
    error_type: str,
    message: str,
) -> Response[object]:
    return Response(
        content={
            "statusCode": status_code,
            "errors": [{"errorType": error_type, "message": message}],
        },
        status_code=status_code,
        media_type=MediaType.JSON,
    )


def _warn_if_signature_missing(request: Request[Any, Any, Any]) -> None:
    if request.headers.get("signature"):
        return
    logger.warning("Signature header missing for PayNow request")


def _validate_create_payload(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["Request body must be an object"]

    typed_payload = cast("CreatePaymentPayload", cast("object", payload))
    required_fields = [
        "amount",
        "currency",
        "externalId",
        "description",
        "buyer",
    ]
    errors = [
        f"Field '{field_name}' is required"
        for field_name in required_fields
        if field_name not in typed_payload
    ]

    buyer = typed_payload.get("buyer")
    if "buyer" in typed_payload and (
        not isinstance(buyer, dict) or not buyer.get("email")
    ):
        errors.append("Field 'buyer.email' is required")

    amount = typed_payload.get("amount")
    if "amount" in typed_payload and not isinstance(amount, int):
        errors.append("Field 'amount' must be an integer")

    status = typed_payload.get("status", "NEW")
    if status not in PAYNOW_STATUSES:
        errors.append("Field 'status' has invalid value")
    return errors


@post("/paynow/v3/payments")
async def create_payment(
    request: Request[Any, Any, Any],
) -> Response[object]:
    _warn_if_signature_missing(request)

    payload_object: object = await request.json()
    validation_errors = _validate_create_payload(payload_object)
    if validation_errors:
        return _error_response(400, "VALIDATION_ERROR", validation_errors[0])

    payload = cast("CreatePaymentPayload", payload_object)
    payment_data = dict(payload)
    payment_data["status"] = str(payload.get("status", "NEW"))

    provider_config = _provider_config(request)
    notify_url = provider_config.get("notify_url")
    if notify_url:
        payment_data["notifyUrl"] = notify_url

    payment_id = request.app.state.storage.create_order(
        payment_data,
        provider="paynow",
    )

    host = request.headers.get("host", "localhost")
    redirect_url = f"http://{host}/sim/paynow/authorize/{payment_id}"
    response_body = {
        "redirectUrl": redirect_url,
        "paymentId": payment_id,
        "status": payment_data["status"],
    }
    return Response(
        content=response_body,
        status_code=201,
        media_type=MediaType.JSON,
    )


@get("/paynow/v3/payments/{payment_id:str}/status")
async def get_payment_status(
    request: Request[Any, Any, Any],
    payment_id: str,
) -> Response[object]:
    _warn_if_signature_missing(request)

    payment = request.app.state.storage.get_order(payment_id)
    if payment is None or payment.get("provider") != "paynow":
        return _error_response(
            404, "NOT_FOUND", f"Payment {payment_id} not found"
        )

    return Response(
        content={
            "paymentId": payment_id,
            "status": str(payment.get("status", "NEW")),
        },
        status_code=200,
        media_type=MediaType.JSON,
    )


@get("/paynow/v3/payments/paymentmethods")
async def get_payment_methods(
    request: Request[Any, Any, Any],
) -> Response[object]:
    _warn_if_signature_missing(request)
    return Response(
        content=PAYMENT_METHODS, status_code=200, media_type=MediaType.JSON
    )


@post("/paynow/v3/payments/{payment_id:str}/refunds")
async def create_refund(
    request: Request[Any, Any, Any],
    payment_id: str,
) -> Response[object]:
    _warn_if_signature_missing(request)

    payment = request.app.state.storage.get_order(payment_id)
    if payment is None or payment.get("provider") != "paynow":
        return _error_response(
            404, "NOT_FOUND", f"Payment {payment_id} not found"
        )

    payment_status = payment.get("status", "NEW")
    if payment_status != "CONFIRMED":
        return _error_response(
            400,
            "VALIDATION_ERROR",
            f"Payment not in CONFIRMED status (current: {payment_status})",
        )

    payload = await request.json()
    if not isinstance(payload, dict):
        payload = {}

    amount = payload.get("amount")
    reason = payload.get("reason")
    if amount is None:
        return _error_response(
            400, "VALIDATION_ERROR", "Field 'amount' is required"
        )

    refund_data = {"amount": amount, "status": "SUCCESSFUL"}
    if reason is not None:
        refund_data["reason"] = reason

    refund_id = request.app.state.storage.create_refund(payment_id, refund_data)
    return Response(
        content={"refundId": refund_id, "status": "SUCCESSFUL"},
        status_code=201,
        media_type=MediaType.JSON,
    )


@get("/paynow/v3/refunds/{refund_id:str}/status")
async def get_refund_status(
    request: Request[Any, Any, Any],
    refund_id: str,
) -> Response[object]:
    _warn_if_signature_missing(request)

    refund = request.app.state.storage.get_refund(refund_id)
    if refund is None:
        return _error_response(
            404, "NOT_FOUND", f"Refund {refund_id} not found"
        )

    amount = refund.get("amount")
    if isinstance(amount, str):
        amount = int(amount)
    return Response(
        content={
            "refundId": refund_id,
            "status": str(refund.get("status", "SUCCESSFUL")),
            "amount": amount,
        },
        status_code=200,
        media_type=MediaType.JSON,
    )


@post("/paynow/v3/refunds/{refund_id:str}/cancel")
async def cancel_refund(
    request: Request[Any, Any, Any],
    refund_id: str,
) -> Response[object]:
    _warn_if_signature_missing(request)

    refund = request.app.state.storage.get_refund(refund_id)
    if refund is None:
        return _error_response(
            404, "NOT_FOUND", f"Refund {refund_id} not found"
        )

    request.app.state.storage.update_refund(refund_id, status="CANCELLED")
    return Response(
        content={"refundId": refund_id, "status": "CANCELLED"},
        status_code=200,
        media_type=MediaType.JSON,
    )


@get("/sim/paynow/authorize/{payment_id:str}")
async def paynow_authorize_get(
    payment_id: str,
    request: Request[Any, Any, Any],
) -> Template:
    payment = request.app.state.storage.get_order(payment_id)
    if not payment:
        raise NotFoundException("Payment not found")

    if payment.get("status") in ("CONFIRMED", "REJECTED"):
        raise HTTPException(status_code=400, detail="Payment already processed")

    formatted_amount = _format_amount_for_display(
        payment,
        _provider_config(request),
    )

    return Template(
        template_name="authorize.html",
        context={
            "provider": "PayNow",
            "payment": payment,
            "payment_id": payment_id,
            "order_id": payment_id,
            "amount": formatted_amount,
            "status": payment.get("status", "NEW"),
        },
    )


@post("/sim/paynow/authorize/{payment_id:str}")
async def paynow_authorize_post(
    payment_id: str,
    request: Request[Any, Any, Any],
    data: dict[str, str] = URL_ENCODED_BODY,
) -> Redirect:
    payment = request.app.state.storage.get_order(payment_id)
    if not payment:
        raise NotFoundException("Payment not found")

    current_status = payment.get("status", "NEW")
    if current_status in ("CONFIRMED", "REJECTED"):
        raise HTTPException(status_code=400, detail="Payment already processed")

    action = data.get("action")
    if action == "approve":
        if current_status == "NEW":
            request.app.state.state_machine.transition(payment_id, "PENDING")
        request.app.state.state_machine.transition(payment_id, "CONFIRMED")
    elif action == "reject":
        if current_status == "NEW":
            request.app.state.state_machine.transition(payment_id, "PENDING")
        request.app.state.state_machine.transition(payment_id, "REJECTED")
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    await trigger_paynow_webhook(
        payment_id,
        request.app.state.storage,
        _provider_config(request),
        request.app.state.webhook_transport,
    )

    continue_url = payment.get("continueUrl", "/sim/dashboard")
    return Redirect(path=str(continue_url))
