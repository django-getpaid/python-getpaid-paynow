"""Tests for Paynow-specific types and enums."""

from getpaid_paynow.types import AuthorizationType
from getpaid_paynow.types import CreatePaymentRequest
from getpaid_paynow.types import CreatePaymentResponse
from getpaid_paynow.types import CreateRefundRequest
from getpaid_paynow.types import CreateRefundResponse
from getpaid_paynow.types import Currency
from getpaid_paynow.types import ErrorDetail
from getpaid_paynow.types import ErrorResponse
from getpaid_paynow.types import ErrorType
from getpaid_paynow.types import NotificationPayload
from getpaid_paynow.types import PaymentMethod
from getpaid_paynow.types import PaymentMethodGroup
from getpaid_paynow.types import PaymentMethodStatus
from getpaid_paynow.types import PaymentMethodType
from getpaid_paynow.types import PaymentStatus
from getpaid_paynow.types import PaymentStatusResponse
from getpaid_paynow.types import RefundReason
from getpaid_paynow.types import RefundStatus
from getpaid_paynow.types import RefundStatusResponse


def test_currency_values():
    assert Currency.PLN == "PLN"
    assert Currency.EUR == "EUR"
    assert Currency.USD == "USD"
    assert Currency.GBP == "GBP"
    assert len(Currency) == 4


def test_payment_status_values():
    assert PaymentStatus.NEW == "NEW"
    assert PaymentStatus.PENDING == "PENDING"
    assert PaymentStatus.CONFIRMED == "CONFIRMED"
    assert PaymentStatus.REJECTED == "REJECTED"
    assert PaymentStatus.ERROR == "ERROR"
    assert PaymentStatus.EXPIRED == "EXPIRED"
    assert PaymentStatus.ABANDONED == "ABANDONED"
    assert len(PaymentStatus) == 7


def test_refund_status_values():
    assert RefundStatus.NEW == "NEW"
    assert RefundStatus.PENDING == "PENDING"
    assert RefundStatus.SUCCESSFUL == "SUCCESSFUL"
    assert RefundStatus.FAILED == "FAILED"
    assert RefundStatus.CANCELLED == "CANCELLED"
    assert len(RefundStatus) == 5


def test_refund_reason_values():
    assert RefundReason.RMA == "RMA"
    assert RefundReason.REFUND_BEFORE_14 == "REFUND_BEFORE_14"
    assert RefundReason.REFUND_AFTER_14 == "REFUND_AFTER_14"
    assert RefundReason.OTHER == "OTHER"
    assert len(RefundReason) == 4


def test_payment_method_type_values():
    assert PaymentMethodType.APPLE_PAY == "APPLE_PAY"
    assert PaymentMethodType.BLIK == "BLIK"
    assert PaymentMethodType.CARD == "CARD"
    assert PaymentMethodType.ECOMMERCE == "ECOMMERCE"
    assert PaymentMethodType.GOOGLE_PAY == "GOOGLE_PAY"
    assert PaymentMethodType.PAYPO == "PAYPO"
    assert PaymentMethodType.PBL == "PBL"
    assert len(PaymentMethodType) == 7


def test_payment_method_status_values():
    assert PaymentMethodStatus.ENABLED == "ENABLED"
    assert PaymentMethodStatus.DISABLED == "DISABLED"
    assert len(PaymentMethodStatus) == 2


def test_authorization_type_values():
    assert AuthorizationType.REDIRECT == "REDIRECT"
    assert AuthorizationType.CODE == "CODE"
    assert len(AuthorizationType) == 2


def test_error_type_values():
    assert ErrorType.CONFLICT == "CONFLICT"
    assert ErrorType.FORBIDDEN == "FORBIDDEN"
    assert ErrorType.NOT_FOUND == "NOT_FOUND"
    assert ErrorType.RATE_LIMIT_REACHED == "RATE_LIMIT_REACHED"
    assert ErrorType.SYSTEM_TEMPORARILY_UNAVAILABLE == (
        "SYSTEM_TEMPORARILY_UNAVAILABLE"
    )
    assert ErrorType.UNAUTHORIZED == "UNAUTHORIZED"
    assert ErrorType.VALIDATION_ERROR == "VALIDATION_ERROR"
    assert ErrorType.VERIFICATION_FAILED == "VERIFICATION_FAILED"
    assert ErrorType.PAYMENT_METHOD_NOT_AVAILABLE == (
        "PAYMENT_METHOD_NOT_AVAILABLE"
    )
    assert ErrorType.PAYMENT_AMOUNT_TOO_SMALL == ("PAYMENT_AMOUNT_TOO_SMALL")
    assert ErrorType.PAYMENT_AMOUNT_TOO_LARGE == ("PAYMENT_AMOUNT_TOO_LARGE")
    assert ErrorType.IDEMPOTENCY_KEY_MISSING == ("IDEMPOTENCY_KEY_MISSING")
    assert ErrorType.SIGNATURE_MISSING == "SIGNATURE_MISSING"
    assert len(ErrorType) == 13


def test_autoname_generates_uppercase_values():
    """AutoName should generate values matching the member name."""
    assert Currency.PLN.value == "PLN"
    assert PaymentStatus.CONFIRMED.value == "CONFIRMED"
    assert RefundReason.REFUND_BEFORE_14.value == "REFUND_BEFORE_14"


def test_create_payment_request_typed_dict():
    """CreatePaymentRequest should accept expected keys."""
    req: CreatePaymentRequest = {
        "amount": 10000,
        "currency": "PLN",
        "externalId": "order-001",
        "description": "Test order",
        "buyer": {"email": "test@example.com"},
    }
    assert req["amount"] == 10000
    assert req["currency"] == "PLN"


def test_create_payment_response_typed_dict():
    resp: CreatePaymentResponse = {
        "redirectUrl": "https://example.com/pay",
        "paymentId": "PAY-123",
        "status": "NEW",
    }
    assert resp["redirectUrl"] == "https://example.com/pay"
    assert resp["paymentId"] == "PAY-123"


def test_payment_status_response_typed_dict():
    resp: PaymentStatusResponse = {
        "paymentId": "PAY-123",
        "status": "CONFIRMED",
    }
    assert resp["status"] == "CONFIRMED"


def test_notification_payload_typed_dict():
    payload: NotificationPayload = {
        "paymentId": "PAY-123",
        "externalId": "order-001",
        "status": "CONFIRMED",
        "modifiedAt": "2024-01-01T12:00:00",
    }
    assert payload["paymentId"] == "PAY-123"
    assert payload["status"] == "CONFIRMED"


def test_create_refund_request_typed_dict():
    req: CreateRefundRequest = {
        "amount": 5000,
    }
    assert req["amount"] == 5000


def test_create_refund_response_typed_dict():
    resp: CreateRefundResponse = {
        "refundId": "REF-123",
        "status": "NEW",
    }
    assert resp["refundId"] == "REF-123"


def test_refund_status_response_typed_dict():
    resp: RefundStatusResponse = {
        "refundId": "REF-123",
        "status": "SUCCESSFUL",
    }
    assert resp["status"] == "SUCCESSFUL"


def test_payment_method_group_typed_dict():
    group: PaymentMethodGroup = {
        "type": "BLIK",
        "paymentMethods": [
            {
                "id": 1,
                "name": "BLIK",
                "description": "BLIK payment",
                "image": "https://example.com/blik.png",
                "status": "ENABLED",
                "authorizationType": "CODE",
            }
        ],
    }
    assert group["type"] == "BLIK"
    assert len(group["paymentMethods"]) == 1


def test_payment_method_typed_dict():
    method: PaymentMethod = {
        "id": 42,
        "name": "Test Bank",
        "description": "Test",
        "image": "https://example.com/img.png",
        "status": "ENABLED",
        "authorizationType": "REDIRECT",
    }
    assert method["id"] == 42
    assert method["status"] == "ENABLED"


def test_error_response_typed_dict():
    resp: ErrorResponse = {
        "statusCode": 400,
        "errors": [
            {
                "errorType": "VALIDATION_ERROR",
                "message": "Amount too small",
            }
        ],
    }
    assert resp["statusCode"] == 400
    assert len(resp["errors"]) == 1


def test_error_detail_typed_dict():
    detail: ErrorDetail = {
        "errorType": "UNAUTHORIZED",
        "message": "Invalid API key",
    }
    assert detail["errorType"] == "UNAUTHORIZED"
