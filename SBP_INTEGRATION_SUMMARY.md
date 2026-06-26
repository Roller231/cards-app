# SBP Payment Integration Summary

## Что сделано

### Backend

1. **Bitbanker Client** (`backend/app/integrations/bitbanker_client.py`)
   - HMAC-SHA256 подпись запросов
   - Методы: `get_sbp_prediction`, `get_exchange_prediction`, `create_invoice`, `get_invoice`
   - Верификация webhook-подписи

2. **BbInvoice Model** (`backend/app/models/bb_invoice.py`)
   - Таблица `bb_invoices` для хранения инвойсов
   - Поля: `user_id`, `bb_invoice_id`, `amount_rub`, `amount_usd`, `status`, `qr_base64`, `payment_url`

3. **SBP Router** (`backend/app/api/routers/sbp.py`)
   - `GET /sbp/prediction` — лимиты и комиссии СБП
   - `GET /sbp/exchange-prediction?amount_rub=` — курс RUB→USDT
   - `POST /sbp/invoice` — создать инвойс, вернуть QR base64
   - `GET /sbp/invoice/{id}` — поллинг статуса
   - `POST /sbp/webhook` — прием вебхуков от Bitbanker (HMAC-верификация)

4. **Config** (`backend/app/core/config.py`)
   - `BITBANKER_API_KEY`
   - `BITBANKER_API_SECRET`
   - `BITBANKER_BASE_URL`

### Frontend

1. **SbpPaymentModal** (`src/components/ui/SbpPaymentModal.jsx`)
   - Ввод суммы в рублях
   - Отображение QR-кода для оплаты
   - Поллинг статуса каждые 5 секунд
   - Success screen при `captured`/`authorized`

2. **API Client** (`src/api/client.js`)
   - `api.sbp.prediction()`
   - `api.sbp.exchangePrediction(amountRub)`
   - `api.sbp.createInvoice(amountRub, purpose)`
   - `api.sbp.pollInvoice(localInvoiceId)`

3. **Интеграция**
   - `TopUpModal` — кнопка «Продолжить» открывает `SbpPaymentModal`
   - `IssueCardPage` — кнопка «Подтвердить и выпустить» открывает `SbpPaymentModal(purpose=card_issue)`

## Флоу оплаты

### 1. Пользователь нажимает «Пополнить» или «Выпустить карту»

### 2. Открывается SbpPaymentModal
- Загружаются лимиты/комиссии через `/sbp/prediction`
- Пользователь вводит сумму в рублях (1000–50000 ₽)

### 3. Создание инвойса
```
POST /api/sbp/invoice
{
  "amount_rub": 5000,
  "purpose": "balance_topup" | "card_issue"
}
```

Ответ:
```json
{
  "local_invoice_id": 123,
  "bb_invoice_id": "...",
  "status": "initiated",
  "payment_url": "https://...",
  "qr_base64": "iVBORw0KGgo...",
  "amount_rub": 5000,
  "expires_at": "2026-06-26T12:00:00Z"
}
```

### 4. Отображение QR-кода
- Пользователь сканирует QR банковским приложением
- Или нажимает «Оплатить в банке» (открывается `payment_url`)

### 5. Поллинг статуса
Каждые 5 секунд:
```
GET /api/sbp/invoice/123
```

Когда статус становится `captured` или `authorized`:
- Backend автоматически кредитует баланс пользователя (из `exchange_deal.volume_take_final`)
- Frontend показывает Success screen
- Если `purpose=card_issue` — вызывается `handleIssueCard()` для выпуска карты

### 6. Webhook от Bitbanker (опционально)
```
POST https://prontopay.pro/api/sbp/webhook
```

- Проверяется `full_sign` (HMAC-SHA256)
- Обновляется статус инвойса
- Кредитуется баланс (если ещё не было)

## Конфигурация Bitbanker

### DEV-контур
```bash
BITBANKER_API_KEY=Z9aXX6x8A5WwBqUsgv30w-a4IHDcRQrA
BITBANKER_API_SECRET=IKgT2tRCygeB-UUQ0NY2Zx9VCqvLg5sfAX6l0nYNba_05kloT8lh31aSyvWTBH-5eSH5mqjTadNJo9RZrxuAiaiulyw9TJQrSbn7dSjiM-xHSk8-q99_IW9l9rulQGzv
BITBANKER_BASE_URL=https://api.aws.dev.bitbanker.org/latest
```

### Webhook URL
```
https://prontopay.pro/api/sbp/webhook
```

Зарегистрировать в Bitbanker DEV-панели.

## Тестирование в DEV

### 1. Создать инвойс через UI
- Залогиниться
- Нажать «Пополнить баланс» или «Выпустить карту»
- Ввести сумму (например, 1000 ₽)
- Получить QR-код

### 2. Симулировать оплату
В Bitbanker DEV-панели:
- Найти созданный инвойс по `bb_invoice_id`
- Вручную изменить статус на `captured`
- Добавить `exchange_deal` с `volume_take_final` (сумма в USDT)

### 3. Проверить результат
- Через 5 секунд поллинг подхватит новый статус
- Баланс пользователя увеличится
- Если это была оплата карты — карта выпустится

### 4. Проверить webhook (если настроен)
```bash
docker logs prontopay-backend | grep "\[SBP\] Webhook"
```

## Переход на PROD

1. Получить PROD-ключи от Bitbanker
2. Обновить `.env`:
```bash
BITBANKER_BASE_URL=https://api.bitbanker.org/latest  # prod URL
BITBANKER_API_KEY=<prod_key>
BITBANKER_API_SECRET=<prod_secret>
```
3. Перезапустить:
```bash
docker compose -f docker-compose.prod.yml up -d --build backend
```

## Известные ограничения DEV-контура

- Реальные деньги не списываются
- Статус платежа нужно менять вручную в панели Bitbanker
- Webhook может приходить с задержкой или не приходить вообще
- Курс RUB→USDT может быть тестовым

## Структура файлов

```
backend/
├── app/
│   ├── integrations/
│   │   └── bitbanker_client.py      # HTTP-клиент Bitbanker
│   ├── models/
│   │   └── bb_invoice.py            # Модель инвойса
│   ├── api/routers/
│   │   └── sbp.py                   # SBP endpoints
│   └── core/
│       └── config.py                # Settings

frontend/
├── src/
│   ├── components/ui/
│   │   └── SbpPaymentModal.jsx      # UI для оплаты
│   └── api/
│       └── client.js                # API методы
```

## Логи для отладки

```bash
# Backend SBP логи
docker logs prontopay-backend | grep SBP

# Все логи backend
docker logs prontopay-backend -f

# Webhook-запросы
docker logs prontopay-nginx | grep "/api/sbp/webhook"
```

## Troubleshooting

### QR-код не отображается
- Проверить `invoice.qr_base64` в ответе `/sbp/invoice`
- Проверить логи backend на ошибки от Bitbanker

### Статус не обновляется
- Проверить, что поллинг работает (консоль браузера)
- Проверить статус в Bitbanker-панели
- Проверить логи: `docker logs prontopay-backend | grep "Poll invoice"`

### Webhook не приходит
- Проверить URL в Bitbanker: `https://prontopay.pro/api/sbp/webhook`
- Проверить, что `BITBANKER_API_SECRET` совпадает
- Проверить nginx-логи: `docker logs prontopay-nginx | grep webhook`

### Баланс не пополняется
- Проверить `exchange_deal` в ответе Bitbanker
- Проверить логи: `docker logs prontopay-backend | grep "Credited user"`
- Проверить таблицу `bb_invoices` в БД
