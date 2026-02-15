# getpaid-paynow

[![PyPI](https://img.shields.io/pypi/v/python-getpaid-paynow.svg)](https://pypi.org/project/python-getpaid-paynow/)
[![Python Version](https://img.shields.io/pypi/pyversions/python-getpaid-paynow)](https://pypi.org/project/python-getpaid-paynow/)
[![License](https://img.shields.io/pypi/l/python-getpaid-paynow)](https://github.com/django-getpaid/python-getpaid-paynow/blob/main/LICENSE)

[Paynow](https://www.paynow.pl/) payment gateway plugin for the
[python-getpaid](https://github.com/django-getpaid) ecosystem. Provides an
async HTTP client (`PaynowClient`) and a payment processor (`PaynowProcessor`)
that integrates with getpaid-core's `BaseProcessor` interface. Authentication
uses API Key + HMAC-SHA256 signature against the Paynow V3 REST API.

## Architecture

The plugin is split into two layers:

- **`PaynowClient`** -- low-level async HTTP client wrapping the Paynow V3
  REST API. Uses `httpx.AsyncClient` with API Key authentication and
  HMAC-SHA256 request signing. Can be used standalone or as an async context
  manager for connection reuse.
- **`PaynowProcessor`** -- high-level payment processor implementing
  `BaseProcessor`. Orchestrates payment creation, callback/notification
  handling, status polling, and refunds. Integrates with the getpaid-core FSM
  for state transitions.

## Key Features

- **Create payment** -- register a payment and get a redirect URL
- **Notification handling** -- verify HMAC signature and process status changes
- **Status polling** -- fetch current payment status via API
- **Refund** -- create, check, and cancel refunds
- **Payment methods** -- retrieve available payment methods
- **HMAC-SHA256 signatures** -- automatic request and notification signing
- **PUSH and PULL** -- notification-based flow with optional status polling

## Quick Usage

### Standalone Client

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
        redirect_url = response["redirectUrl"]
        print(f"Redirect buyer to: {redirect_url}")

anyio.run(main)
```

### With django-getpaid

Register the plugin via entry point in `pyproject.toml`:

```toml
[project.entry-points."getpaid.backends"]
paynow = "getpaid_paynow.processor:PaynowProcessor"
```

Then configure in your Django settings (or config dict):

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

## Configuration Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `api_key` | `str` | *required* | API key from Paynow merchant panel |
| `signature_key` | `str` | *required* | Signature key for HMAC calculation |
| `sandbox` | `bool` | `True` | Use sandbox or production API |
| `notification_url` | `str` | `""` | Notification URL template; use `{payment_id}` placeholder |
| `continue_url` | `str` | `""` | Return URL template; use `{payment_id}` placeholder |

## Supported Currencies

PLN, EUR, USD, GBP (4 total).

## Limitations

Paynow does not support pre-authorization. The `charge()` and
`release_lock()` methods raise `NotImplementedError`.

## Requirements

- Python 3.12+
- `python-getpaid-core >= 0.1.0`
- `httpx >= 0.27.0`

## Related Projects

- [python-getpaid-core](https://github.com/django-getpaid/python-getpaid-core) -- core abstractions (protocols, FSM, processor base class)
- [django-getpaid](https://github.com/django-getpaid/django-getpaid) -- Django adapter (models, views, admin)

## License

MIT

## Disclaimer

This project has nothing in common with the
[getpaid](http://code.google.com/p/getpaid/) plone project.
It is part of the `django-getpaid` / `python-getpaid` ecosystem.

## Credits

Created by [Dominik Kozaczko](https://github.com/dekoza).
