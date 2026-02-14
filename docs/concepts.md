# Concepts

## Payment Flow

The Paynow payment flow follows a create-redirect-notify pattern:

```
┌──────────┐     create_payment           ┌──────────┐
│  Your    │ ──────────────────────────►  │  Paynow  │
│  Server  │  ◄── redirectUrl ─────────  │   API    │
└────┬─────┘                              └──────────┘
     │
     │  redirect buyer to
     │  Paynow payment page
     ▼
┌──────────┐     buyer pays               ┌──────────┐
│  Buyer   │ ──────────────────────────►  │  Paynow  │
│ Browser  │                              │ Payment  │
└──────────┘                              │  Page    │
                                          └────┬─────┘
                                               │
                          notification (POST)  │
┌──────────┐  ◄────────────────────────────────┘
│  Your    │
│  Server  │  1. verify_callback (check HMAC signature)
│          │  2. handle_callback (update FSM state)
└──────────┘
```

### Step by Step

1. **Create payment** — `PaynowProcessor.prepare_transaction()` calls
   `PaynowClient.create_payment()` with payment details. Paynow returns a
   `redirectUrl` and `paymentId`.

2. **Redirect** — the buyer is redirected to `redirectUrl` where they
   complete the payment.

3. **Notification** — Paynow sends a POST request to `notification_url` with
   the notification payload (including `paymentId`, `status`, `Signature`
   header).

4. **Verify callback** — `PaynowProcessor.verify_callback()` recalculates the
   HMAC-SHA256 signature from the raw body with the Signature-Key and compares
   it with the received `Signature` header. Raises `InvalidCallbackError` on
   mismatch.

5. **Handle callback** — `PaynowProcessor.handle_callback()` maps the Paynow
   status to FSM transitions: `CONFIRMED` triggers `confirm_payment` +
   `mark_as_paid`; `REJECTED`, `ERROR`, `EXPIRED`, `ABANDONED` trigger `fail`.

:::{note}
Unlike Przelewy24, Paynow does **not** require a separate verification step
after the notification. The HMAC signature verification is sufficient.
:::

## Notification Handling

Paynow sends HTTP POST notifications to the configured `notification_url`
on every status change. Important characteristics:

- **Same notification may arrive multiple times** — handle idempotently
- **Notifications may arrive out of order** — check status before transitioning
- **Respond with 200 OK or 202 Accepted** with an empty body
- **Signature header** contains the HMAC-SHA256 of the raw body

## No Pre-Authorization Flow

Paynow only supports direct payments. There is no lock/charge/release cycle.
The `charge()` and `release_lock()` methods on `PaynowProcessor` raise
`NotImplementedError`.

## Refund Flow

```
┌──────────┐     start_refund             ┌──────────┐
│  Your    │ ──────────────────────────►  │  Paynow  │
│  Server  │                              │   API    │
└──────────┘                              └────┬─────┘
                                               │
                    refund notification (POST)  │
┌──────────┐  ◄─────────────────────────────────┘
│  Your    │
│  Server  │  Process refund notification
└──────────┘
```

1. `PaynowProcessor.start_refund(amount)` calls `PaynowClient.create_refund()`
   with the refund amount.

2. Paynow processes the refund asynchronously. The refund status can be
   checked via `PaynowClient.get_refund_status()`.

3. A pending refund can be cancelled via
   `PaynowProcessor.cancel_refund()` /
   `PaynowClient.cancel_refund()`.

### Refund Statuses

| Status | Description |
|--------|-------------|
| `NEW` | Refund just created |
| `PENDING` | Refund is being processed |
| `SUCCESSFUL` | Refund completed |
| `FAILED` | Refund failed |
| `CANCELLED` | Refund was cancelled |

### Refund Reasons

| Reason | Description |
|--------|-------------|
| `RMA` | Return merchandise authorization |
| `REFUND_BEFORE_14` | Refund within 14 days |
| `REFUND_AFTER_14` | Refund after 14 days |
| `OTHER` | Other reason |

## HMAC-SHA256 Signature Calculation

### Request Signatures

All API requests are signed with HMAC-SHA256. The payload for signing is a
JSON object with three keys:

1. **`headers`** — `Api-Key` and `Idempotency-Key` values, sorted
   alphabetically by key name
2. **`parameters`** — query parameters sorted alphabetically (empty `{}` for
   POST requests)
3. **`body`** — JSON string of the request body (empty `""` for GET requests)

The payload is serialized as compact JSON (`separators=(",", ":")`),
then HMAC-SHA256 is calculated using the Signature-Key, and the result is
base64-encoded.

### Notification Signatures

Notification signatures are simpler: HMAC-SHA256 of the raw body string
with the Signature-Key, base64-encoded.

## Amount Handling

Paynow expects amounts as **integers in the lowest currency unit** (e.g.,
grosze for PLN, cents for EUR). The client handles conversion automatically:

- `PaynowClient._to_lowest_unit(Decimal("49.99"))` → `4999`
- `PaynowClient._from_lowest_unit(4999)` → `Decimal("49.99")`

## PUSH vs PULL Status Checking

The plugin supports both notification models:

- **PUSH** — Paynow sends a POST to `notification_url` after each status
  change. The processor handles it via `verify_callback()` +
  `handle_callback()`. This is the primary flow.

- **PULL** — `PaynowProcessor.fetch_payment_status()` calls
  `PaynowClient.get_payment_status()` to poll the payment status. Returns a
  `PaymentStatusResponse` with the mapped FSM trigger.

| Paynow Status | Mapped FSM Trigger |
|---------------|-------------------|
| `NEW` | `None` |
| `PENDING` | `confirm_prepared` |
| `CONFIRMED` | `confirm_payment` |
| `REJECTED` | `fail` |
| `ERROR` | `fail` |
| `EXPIRED` | `fail` |
| `ABANDONED` | `fail` |

## Supported Operations

| Operation | Client Method | Processor Method | HTTP |
|-----------|--------------|------------------|------|
| Create payment | `create_payment()` | `prepare_transaction()` | `POST /v3/payments` |
| Payment status | `get_payment_status()` | `fetch_payment_status()` | `GET /v3/payments/{id}/status` |
| Payment methods | `get_payment_methods()` | — | `GET /v3/payments/paymentmethods` |
| Create refund | `create_refund()` | `start_refund()` | `POST /v3/payments/{id}/refunds` |
| Refund status | `get_refund_status()` | — | `GET /v3/refunds/{id}/status` |
| Cancel refund | `cancel_refund()` | `cancel_refund()` | `POST /v3/refunds/{id}/cancel` |

## Supported Currencies

Paynow supports 4 currencies: PLN, EUR, USD, GBP.

## Payment Statuses

| Status | Description |
|--------|-------------|
| `NEW` | Payment just created |
| `PENDING` | Payment is being processed |
| `CONFIRMED` | Payment confirmed (success) |
| `REJECTED` | Payment rejected by buyer or bank |
| `ERROR` | Technical error during payment |
| `EXPIRED` | Payment expired (time limit reached) |
| `ABANDONED` | Buyer abandoned the payment page |
