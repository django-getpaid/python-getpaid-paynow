"""PayNow webhook delivery for the simulator plugin."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from getpaid_paynow.simulator.signing import sign_webhook


if TYPE_CHECKING:
    from getpaid_simulator.core.storage import SimulatorStorage
    from getpaid_simulator.core.webhooks import WebhookTransport


def build_notification_payload(
    payment_id: str,
    payment: dict[str, Any],
) -> dict[str, Any]:
    return {
        "paymentId": payment_id,
        "externalId": payment.get("externalId", ""),
        "status": payment.get("status", "NEW"),
        "modifiedAt": datetime.now(UTC).isoformat(),
    }


async def trigger_paynow_webhook(
    payment_id: str,
    storage: SimulatorStorage,
    provider_config: dict[str, Any],
    transport: WebhookTransport,
) -> bool | None:
    payment = storage.get_order(payment_id)
    if payment is None:
        return None

    notify_url = payment.get("notifyUrl") or provider_config.get("notify_url")
    if not notify_url:
        return None

    payload = build_notification_payload(payment_id, payment)
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        **sign_webhook(body, str(provider_config["signature_key"])),
    }

    result = await transport.deliver(
        url=str(notify_url), body=body, headers=headers
    )
    storage.update_order(
        payment_id,
        webhook_status="success" if result else "failed",
    )
    return result
