"""Paynow V3 API types and enums."""

from enum import StrEnum
from enum import auto
from enum import unique
from typing import TypedDict


class AutoName(StrEnum):
    @staticmethod
    def _generate_next_value_(name, start, count, last_values):
        return name.strip("_")


@unique
class Currency(AutoName):
    """Currencies supported by Paynow."""

    PLN = auto()
    EUR = auto()
    USD = auto()
    GBP = auto()


@unique
class PaymentStatus(AutoName):
    """Payment statuses returned by Paynow V3 API."""

    NEW = auto()
    PENDING = auto()
    CONFIRMED = auto()
    REJECTED = auto()
    ERROR = auto()
    EXPIRED = auto()
    ABANDONED = auto()


@unique
class RefundStatus(AutoName):
    """Refund statuses returned by Paynow V3 API."""

    NEW = auto()
    PENDING = auto()
    SUCCESSFUL = auto()
    FAILED = auto()
    CANCELLED = auto()


@unique
class RefundReason(AutoName):
    """Refund reason codes accepted by Paynow V3 API."""

    RMA = auto()
    REFUND_BEFORE_14 = auto()
    REFUND_AFTER_14 = auto()
    OTHER = auto()


@unique
class PaymentMethodType(AutoName):
    """Payment method group types from Paynow V3 API."""

    APPLE_PAY = auto()
    BLIK = auto()
    CARD = auto()
    ECOMMERCE = auto()
    GOOGLE_PAY = auto()
    PAYPO = auto()
    PBL = auto()


@unique
class PaymentMethodStatus(AutoName):
    """Payment method availability status."""

    ENABLED = auto()
    DISABLED = auto()


@unique
class AuthorizationType(AutoName):
    """Payment method authorization type."""

    REDIRECT = auto()
    CODE = auto()


@unique
class ErrorType(AutoName):
    """Error types returned by Paynow V3 API."""

    CONFLICT = auto()
    FORBIDDEN = auto()
    NOT_FOUND = auto()
    RATE_LIMIT_REACHED = auto()
    SYSTEM_TEMPORARILY_UNAVAILABLE = auto()
    UNAUTHORIZED = auto()
    VALIDATION_ERROR = auto()
    VERIFICATION_FAILED = auto()
    PAYMENT_METHOD_NOT_AVAILABLE = auto()
    PAYMENT_AMOUNT_TOO_SMALL = auto()
    PAYMENT_AMOUNT_TOO_LARGE = auto()
    IDEMPOTENCY_KEY_MISSING = auto()
    SIGNATURE_MISSING = auto()


# --- TypedDicts for API requests and responses ---


class BuyerData(TypedDict, total=False):
    """Buyer information for payment creation."""

    email: str
    firstName: str
    lastName: str
    phone: str


class OrderItem(TypedDict, total=False):
    """Single item in an order."""

    name: str
    category: str
    quantity: int
    price: int


class CreatePaymentRequest(TypedDict, total=False):
    """Data for POST /v3/payments."""

    amount: int
    currency: str
    externalId: str
    description: str
    buyer: BuyerData
    continueUrl: str
    orderItems: list[OrderItem]
    validityTime: int
    payoutAccount: str
    locale: str
    deviceFingerprint: str


class CreatePaymentResponse(TypedDict):
    """Response from POST /v3/payments (201)."""

    redirectUrl: str
    paymentId: str
    status: str


class PaymentStatusResponse(TypedDict):
    """Response from GET /v3/payments/{paymentId}/status."""

    paymentId: str
    status: str


class NotificationPayload(TypedDict):
    """Notification POST data sent by Paynow on status change."""

    paymentId: str
    externalId: str
    status: str
    modifiedAt: str


class CreateRefundRequest(TypedDict, total=False):
    """Data for POST /v3/payments/{paymentId}/refunds."""

    amount: int
    reason: str


class CreateRefundResponse(TypedDict):
    """Response from POST /v3/payments/{paymentId}/refunds (201)."""

    refundId: str
    status: str


class RefundStatusResponse(TypedDict):
    """Response from GET /v3/refunds/{refundId}/status."""

    refundId: str
    status: str


class PaymentMethod(TypedDict):
    """Single payment method within a group."""

    id: int
    name: str
    description: str
    image: str
    status: str
    authorizationType: str


class PaymentMethodGroup(TypedDict):
    """Payment method group from GET /v3/payments/paymentmethods."""

    type: str
    paymentMethods: list[PaymentMethod]


class ErrorDetail(TypedDict):
    """Single error entry in an error response."""

    errorType: str
    message: str


class ErrorResponse(TypedDict):
    """Error response from Paynow V3 API."""

    statusCode: int
    errors: list[ErrorDetail]
