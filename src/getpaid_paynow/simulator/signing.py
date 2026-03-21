"""PayNow signing helpers for the simulator plugin."""

import base64
import hashlib
import hmac
import json


def calculate_notification_signature(body: str, signature_key: str) -> str:
    digest = hmac.new(
        signature_key.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def calculate_request_signature(
    api_key: str,
    idempotency_key: str,
    body: str,
    signature_key: str,
    parameters: dict[str, str] | None = None,
) -> str:
    params = parameters or {}
    headers_dict = {
        "Api-Key": api_key,
        "Idempotency-Key": idempotency_key,
    }
    payload = {
        "headers": dict(sorted(headers_dict.items())),
        "parameters": dict(sorted(params.items())),
        "body": body,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    digest = hmac.new(
        signature_key.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def sign_webhook(body: bytes, signature_key: str) -> dict[str, str]:
    signature = calculate_notification_signature(
        body.decode("utf-8"),
        signature_key,
    )
    return {"Signature": signature}
