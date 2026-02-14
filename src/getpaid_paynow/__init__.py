"""Paynow V3 payment gateway integration for python-getpaid ecosystem."""

__all__ = [
    "PaynowClient",
    "PaynowProcessor",
]


def __getattr__(name: str):
    if name == "PaynowClient":
        from getpaid_paynow.client import PaynowClient

        return PaynowClient
    if name == "PaynowProcessor":
        from getpaid_paynow.processor import PaynowProcessor

        return PaynowProcessor
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
