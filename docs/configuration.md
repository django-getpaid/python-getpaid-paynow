# Configuration

## Configuration Keys

All settings are passed as a dictionary to the processor (via
`BaseProcessor.get_setting()`) or directly to `PaynowClient.__init__()`.

| Key | Type | Default | Required | Description |
|-----|------|---------|----------|-------------|
| `api_key` | `str` | — | Yes | API key from Paynow merchant panel |
| `signature_key` | `str` | — | Yes | Signature key for HMAC-SHA256 calculation |
| `sandbox` | `bool` | `True` | No | Use sandbox environment (`True`) or production (`False`) |
| `notification_url` | `str` | `""` | No | Callback URL template for payment notifications |
| `continue_url` | `str` | `""` | No | URL template to redirect buyer after payment |

### URL Templates

The `notification_url` and `continue_url` settings support a `{payment_id}`
placeholder that is replaced with the actual payment ID at runtime:

```python
"notification_url": "https://shop.example.com/payments/{payment_id}/callback/"
# becomes: https://shop.example.com/payments/abc123/callback/
```

## Example Configuration

```python
GETPAID_BACKEND_SETTINGS = {
    "paynow": {
        "api_key": "your-api-key",
        "signature_key": "your-signature-key",
        "sandbox": False,
        "notification_url": "https://shop.example.com/payments/{payment_id}/callback/",
        "continue_url": "https://shop.example.com/payments/{payment_id}/return/",
    }
}
```

## Where to Find Credentials

Both required credentials are available in the Paynow merchant panel:

1. **api_key** — generated in the merchant panel under API settings
2. **signature_key** — generated alongside the API key for HMAC signing

:::{important}
The `api_key` and `signature_key` are secrets. Never commit them to version
control. Use environment variables or a secrets manager.
:::

## Sandbox vs Production

| Setting | Sandbox | Production |
|---------|---------|------------|
| `sandbox` | `True` | `False` |
| Base URL | `https://api.sandbox.paynow.pl` | `https://api.paynow.pl` |

:::{note}
The default value of `sandbox` is `True`. Always set it explicitly to `False`
for production deployments.
:::
