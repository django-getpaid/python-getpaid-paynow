# python-getpaid-paynow

[![PyPI version](https://img.shields.io/pypi/v/python-getpaid-paynow.svg)](https://pypi.org/project/python-getpaid-paynow/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python versions](https://img.shields.io/pypi/pyversions/python-getpaid-paynow.svg)](https://pypi.org/project/python-getpaid-paynow/)

Paynow payment processor for [python-getpaid](https://github.com/django-getpaid/python-getpaid-core) ecosystem.
Paynow is a modern Polish payment provider and a subsidiary of mBank.

## Architecture

The plugin is split into two layers:

- **`PaynowClient`** -- low-level async HTTP client wrapping the Paynow V3 REST API. Uses `httpx.AsyncClient` with API Key authentication and HMAC-SHA256 request signing. Can be used standalone or as an async context manager for connection reuse.
- **`PaynowProcessor`** -- high-level payment processor implementing `BaseProcessor`. Orchestrates payment creation, callback/notification handling, status polling, and refunds. Integrates with the getpaid-core FSM for state transitions.

## Key Features

- **Create payment** -- register a payment and get a redirect URL
- **Notification handling** -- verify HMAC-SHA256 signature and process status changes
- **Status polling** -- fetch current payment status via API (PULL flow)
- **Refund** -- create, check, and cancel refunds
- **Payment methods** -- retrieve available payment methods
- **Sandbox mode** -- full support for testing environment

**Note:** Paynow does not support pre-authorization flows. Immediate capture is used for all transactions. The `charge()` and `release_lock()` methods raise `NotImplementedError`.

## Supported Currencies

The processor supports the following 4 currencies:
- **PLN** (Polish Złoty)
- **EUR** (Euro)
- **GBP** (British Pound)
- **USD** (US Dollar)

## Installation

Install the package using pip:

```bash
pip install python-getpaid-paynow
```

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

### With python-getpaid

Register the plugin via entry point in `pyproject.toml` (if not using the pre-packaged version):

```toml
[project.entry-points."getpaid.backends"]
paynow = "getpaid_paynow.processor:PaynowProcessor"
```

Then configure in your project settings:

```python
GETPAID_BACKEND_SETTINGS = {
    "paynow": {
        "api_key": "your-api-key",
        "signature_key": "your-signature-key",
        "sandbox": True,
        "notification_url": "https://your-site.com/payments/{payment_id}/callback/",
        "continue_url": "https://your-site.com/payments/{payment_id}/return/",
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

## Requirements

- Python 3.12+
- `python-getpaid-core >= 3.0.0a2`
- `httpx >= 0.27.0`

## Links

- **Core Library:** [python-getpaid-core](https://github.com/django-getpaid/python-getpaid-core)
- **Official Paynow Documentation:** [docs.paynow.pl](https://docs.paynow.pl/)
- **GitHub Repository:** [django-getpaid/python-getpaid-paynow](https://github.com/django-getpaid/python-getpaid-paynow)

## License

This project is licensed under the MIT License.

## Credits

Created by [Dominik Kozaczko](https://github.com/dekoza).
