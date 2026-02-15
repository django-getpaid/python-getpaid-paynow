# Getting Started

## Installation

Install getpaid-paynow from PyPI (distributed as `python-getpaid-paynow`):

```bash
pip install python-getpaid-paynow
```

Or add it as a dependency with uv:

```bash
uv add python-getpaid-paynow
```

This will also install `python-getpaid-core` and `httpx` as dependencies.

## About This Plugin

getpaid-paynow is a **payment gateway plugin** for the python-getpaid
ecosystem. It can be used in two ways:

1. **Standalone** — use `PaynowClient` directly to interact with the Paynow
   V3 REST API from any Python application.
2. **With django-getpaid** — register `PaynowProcessor` as a payment backend
   and let the framework handle the payment lifecycle.

## Standalone Usage

The `PaynowClient` is an async HTTP client that wraps the Paynow V3 REST API.
Use it as an async context manager for connection reuse:

```python
import anyio
from decimal import Decimal
from getpaid_paynow import PaynowClient

async def main():
    async with PaynowClient(
        api_key="your-api-key",
        signature_key="your-signature-key",
        api_url="https://api.sandbox.paynow.pl",
    ) as client:
        # Create a payment
        response = await client.create_payment(
            amount=Decimal("49.99"),
            currency="PLN",
            external_id="order-001",
            description="Order #001",
            buyer_email="buyer@example.com",
            continue_url="https://shop.example.com/return/order-001",
        )

        # Get redirect URL
        redirect_url = response["redirectUrl"]
        print(f"Redirect buyer to: {redirect_url}")

anyio.run(main)
```

## Using with django-getpaid

### 1. Register the entry point

Add the processor to your plugin's or application's `pyproject.toml`:

```toml
[project.entry-points."getpaid.backends"]
paynow = "getpaid_paynow.processor:PaynowProcessor"
```

### 2. Configure backend settings

In your Django settings (or config dict passed to the processor):

```python
GETPAID_BACKEND_SETTINGS = {
    "paynow": {
        "api_key": "your-api-key",
        "signature_key": "your-signature-key",
        "sandbox": True,
        "notification_url": "https://shop.example.com/payments/{payment_id}/callback/",
        "continue_url": "https://shop.example.com/payments/{payment_id}/return/",
    }
}
```

The `{payment_id}` placeholder in URL templates is replaced with the actual
payment ID at runtime.

### 3. Process payments

The framework adapter handles the rest — creating payments, redirecting
buyers, receiving notifications, and updating payment status via the FSM.

## Sandbox vs Production

By default, `sandbox=True`, which uses `https://api.sandbox.paynow.pl`.
Set `sandbox=False` for production, which uses `https://api.paynow.pl`.

You can obtain sandbox credentials from the
[Paynow merchant panel](https://panel.paynow.pl/).
