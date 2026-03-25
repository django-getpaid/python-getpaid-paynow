"""PayNow simulator plugin factory."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from typing import Any

from getpaid_simulator.spi import SIMULATOR_PLUGIN_API_VERSION
from getpaid_simulator.spi import SimulatorProviderPlugin

from getpaid_paynow.simulator.routes import cancel_refund
from getpaid_paynow.simulator.routes import create_payment
from getpaid_paynow.simulator.routes import create_refund
from getpaid_paynow.simulator.routes import get_payment_methods
from getpaid_paynow.simulator.routes import get_payment_status
from getpaid_paynow.simulator.routes import get_refund_status
from getpaid_paynow.simulator.routes import paynow_authorize_get
from getpaid_paynow.simulator.routes import paynow_authorize_post
from getpaid_paynow.simulator.transitions import PAYNOW_TRANSITIONS


if TYPE_CHECKING:
    from collections.abc import Mapping


def load_provider_config(
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    environment = env or os.environ
    return {
        "amount_minor_unit_places": 2,
        "api_key": environment.get(
            "SIMULATOR_PAYNOW_API_KEY",
            "sim-paynow-api-key",
        ),
        "signature_key": environment.get(
            "SIMULATOR_PAYNOW_SIGNATURE_KEY",
            "sim-paynow-key-default",
        ),
        "notify_url": environment.get("SIMULATOR_PAYNOW_NOTIFY_URL", ""),
    }


def get_plugin() -> SimulatorProviderPlugin:
    return SimulatorProviderPlugin(
        api_version=SIMULATOR_PLUGIN_API_VERSION,
        slug="paynow",
        display_name="PayNow",
        api_handlers=(
            create_payment,
            get_payment_status,
            get_payment_methods,
            create_refund,
            get_refund_status,
            cancel_refund,
        ),
        ui_handlers=(paynow_authorize_get, paynow_authorize_post),
        transitions=PAYNOW_TRANSITIONS,
        load_config=load_provider_config,
        authorize_path_template="/sim/paynow/authorize/{entity_id}",
    )
