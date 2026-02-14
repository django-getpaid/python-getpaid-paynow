# Changelog

## v0.1.0 (2026-02-14)

Initial release.

### Features

- Full Paynow V3 REST API coverage
- Async HTTP client (`PaynowClient`) with API Key + HMAC-SHA256 signing
- Payment processor (`PaynowProcessor`) implementing `BaseProcessor`
- Payment creation with redirect URL
- HMAC-SHA256 signature calculation and verification
- Notification (PUSH) callback handling
- Status polling (PULL) via API
- Refund support (create, check status, cancel)
- Payment methods retrieval
- Amount conversion (`Decimal` ↔ integer lowest currency unit)
- Support for PLN, EUR, USD, GBP currencies
