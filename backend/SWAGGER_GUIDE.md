# Swagger Testing Guide — Cards App Backend

Open Swagger UI at: **http://localhost:8000/docs**

---

## 0. Prerequisites

1. Copy `.env.example` → `.env` and fill in your actual values:
   - `DATABASE_URL` — point to your MySQL instance
   - `AIFORY_TOTP_SECRET` — the secret from your Aifory 2FA QR code
2. Create the database: `CREATE DATABASE cards_app CHARACTER SET utf8mb4;`
3. Install dependencies and start the server:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Tables are created automatically on startup.

---

## Step 1 — Authenticate (passwordless)

Preferred for Mini App flow (no password/email needed):

**`POST /auth/telegram-login`**

```json
{
  "telegram_user_id": "123456789",
  "username": "optional_display_name"
}
```

If a user with this `telegram_user_id` doesn't exist, it will be created automatically.  
Copy the returned `access_token`.

Optional alternative for Swagger-only tests (no password required):

**`POST /auth/register`**

```json
{
  "username": "testuser",
  "telegram_user_id": null
}
```

Copy the returned `access_token`.

---

## Step 2 — Authorize in Swagger

Click the **🔒 Authorize** button (top-right of Swagger UI).  
Paste the token into the `bearerAuth` field → **Authorize**.

All subsequent calls will be authenticated.

---

## Step 3 — Check your profile and balance

**`GET /auth/me`**

Confirms your user info. Balance starts at `0`.

---

## Step 4 — Create a balance top-up request

**`POST /balance/topup-requests`**

```json
{
  "amount": 50,
  "comment": "Initial test top-up"
}
```

Note the returned `id`.

---

## Step 5 — Confirm the top-up (manual / dev)

**`POST /balance/topup-requests/{id}/confirm`**

```json
{
  "payment_reference": "manual-test-001"
}
```

Your balance is now credited. Verify with `GET /auth/me` → `balance` should be `50`.

---

## Step 6 — Browse card offers

**`GET /cards/offers`**

Returns a list of available virtual card products from Aifory.  
Note an `id` from the list (this is your `offer_id`).

---

## Step 7 — Issue a virtual card

**`POST /cards/issue`**

```json
{
  "offer_id": "<offer_id from step 6>",
  "holder_first_name": "Ivan",
  "holder_last_name": "Petrov"
}
```

Returns `local_order_id` and `partner_order_id`.  
Aifory processes issuance asynchronously — the card appears once the order completes.

---

## Step 8 — Check order status

**`POST /orders/{local_order_id}/sync`**

Polls Aifory and updates the local order status.  
Repeat until `status` is no longer `pending`.

---

## Step 9 — Sync and list cards

**`GET /cards`**

Syncs all cards from Aifory, links completed issue orders to local card records, and returns your card list.

Note the `id` (local card ID) for subsequent calls.

---

## Step 10 — View card requisites (PAN / CVV)

**`GET /cards/{card_id}/requisites`**

Returns the full card number, expiry date, CVV, and holder name.  
Only works once the card is linked (i.e., issuance order completed in Step 8).

---

## Step 11 — Top up card balance (via Aifory deposit)

### 11a. See available deposit methods

**`GET /cards/{card_id}/deposit-offers`**

### 11b. Create a deposit order

**`POST /cards/{card_id}/deposit`**

```json
{
  "amount": 20
}
```

Deducts from your user balance and creates an Aifory deposit order.  
Use `POST /orders/{local_order_id}/sync` to track its status.

---

## Step 12 — View transaction history

**`GET /transactions/cards/{card_id}`**

Fetches the card's transaction history directly from Aifory.

---

## Step 13 — List all orders

**`GET /orders`**

Shows all local orders (issue + topup) for the current user.

---

## Dev / Debug endpoints

| Endpoint | Purpose |
|---|---|
| `POST /aifory-dev/login` | Trigger Aifory re-login manually |
| `GET /aifory-dev/accounts` | Inspect parent account IDs |
| `GET /aifory-dev/offers?account_id=…` | Raw card offers from Aifory |
| `GET /aifory-dev/cards?account_id=…` | All raw cards on parent account |
| `GET /aifory-dev/orders/{partner_order_id}` | Raw Aifory order details |

---

## Complete Swagger flow summary

```
register → authorize → top-up request → confirm top-up
→ get offers → issue card → sync order → list cards
→ get requisites → deposit card → view transactions
```
