"""Tests for the PayNow simulator plugin."""

from __future__ import annotations

import json
from importlib.metadata import entry_points

import pytest
from getpaid_simulator.spi import SIMULATOR_PLUGIN_API_VERSION

from getpaid_paynow.simulator import get_plugin
from getpaid_paynow.simulator.plugin import load_provider_config
from getpaid_paynow.simulator.signing import sign_webhook
from getpaid_paynow.simulator.webhooks import trigger_paynow_webhook


def _handler_name(handler: object) -> str:
    return str(handler.fn.__name__)


class FakeStorage:
    def __init__(self, payment: dict[str, object] | None) -> None:
        self.payment = payment
        self.updated: dict[str, object] = {}

    def get_order(self, payment_id: str) -> dict[str, object] | None:
        if self.payment is None or payment_id != "payment-1":
            return None
        return dict(self.payment)

    def update_order(self, payment_id: str, **updates: object) -> None:
        assert payment_id == "payment-1"
        self.updated = dict(updates)


class FakeTransport:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def deliver(
        self,
        *,
        url: str,
        body: bytes,
        headers: dict[str, str],
    ) -> bool:
        self.calls.append({"url": url, "body": body, "headers": dict(headers)})
        return self.result


def test_paynow_simulator_entry_point_registered() -> None:
    simulator_plugins = [
        entry_point
        for entry_point in entry_points(group="getpaid.simulator.providers")
        if entry_point.name == "paynow"
    ]

    assert len(simulator_plugins) == 1
    assert simulator_plugins[0].value == "getpaid_paynow.simulator:get_plugin"


def test_get_plugin_returns_paynow_simulator_descriptor() -> None:
    plugin = get_plugin()

    assert plugin.api_version == SIMULATOR_PLUGIN_API_VERSION
    assert plugin.slug == "paynow"
    assert plugin.display_name == "PayNow"
    assert plugin.authorize_path_template == "/sim/paynow/authorize/{entity_id}"
    assert (
        plugin.build_authorize_path("payment-123")
        == "/sim/paynow/authorize/payment-123"
    )
    assert {_handler_name(handler) for handler in plugin.api_handlers} == {
        "create_payment",
        "get_payment_status",
        "get_payment_methods",
        "create_refund",
        "get_refund_status",
        "cancel_refund",
    }
    assert {_handler_name(handler) for handler in plugin.ui_handlers} == {
        "paynow_authorize_get",
        "paynow_authorize_post",
    }


def test_load_provider_config_reads_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIMULATOR_PAYNOW_API_KEY", "override-api-key")
    monkeypatch.setenv("SIMULATOR_PAYNOW_SIGNATURE_KEY", "override-signature")
    monkeypatch.setenv(
        "SIMULATOR_PAYNOW_NOTIFY_URL",
        "https://merchant.example/paynow/callback",
    )

    assert load_provider_config() == {
        "amount_minor_unit_places": 2,
        "api_key": "override-api-key",
        "signature_key": "override-signature",
        "notify_url": "https://merchant.example/paynow/callback",
    }


def test_load_provider_config_includes_amount_minor_unit_places() -> None:
    assert load_provider_config()["amount_minor_unit_places"] == 2


@pytest.mark.asyncio
async def test_trigger_paynow_webhook_uses_provider_notify_url_fallback() -> (
    None
):
    storage = FakeStorage(
        {
            "externalId": "PAYNOW-42",
            "status": "CONFIRMED",
        }
    )
    transport = FakeTransport()

    result = await trigger_paynow_webhook(
        "payment-1",
        storage,
        {
            "signature_key": "secret-key",
            "notify_url": "https://merchant.example/paynow/callback",
        },
        transport,
    )

    assert result is True
    assert storage.updated == {"webhook_status": "success"}
    assert len(transport.calls) == 1

    request = transport.calls[0]
    assert request["url"] == "https://merchant.example/paynow/callback"
    body = request["body"]
    assert isinstance(body, bytes)
    payload = json.loads(body)
    assert payload["paymentId"] == "payment-1"
    assert payload["externalId"] == "PAYNOW-42"
    assert payload["status"] == "CONFIRMED"
    assert request["headers"] == {
        "Content-Type": "application/json",
        **sign_webhook(body, "secret-key"),
    }


@pytest.mark.asyncio
async def test_trigger_paynow_webhook_returns_none_without_target() -> None:
    storage = FakeStorage({"externalId": "PAYNOW-42", "status": "CONFIRMED"})
    transport = FakeTransport()

    result = await trigger_paynow_webhook(
        "payment-1",
        storage,
        {"signature_key": "secret-key", "notify_url": ""},
        transport,
    )

    assert result is None
    assert transport.calls == []
