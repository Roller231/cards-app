# Virtual Cards Backend API

FastAPI backend для Telegram Mini App с интеграцией Aifory Virtual Cards API.

## Архитектура

```
backend/
├── app/
│   ├── api/
│   │   ├── deps.py              # Зависимости (auth, db)
│   │   └── routers/             # API роутеры
│   │       ├── auth.py          # Авторизация Telegram
│   │       ├── cards.py         # Управление картами
│   │       ├── offers.py        # Офферы и выпуск карт
│   │       ├── topup.py         # Пополнение карт
│   │       ├── orders.py        # Статусы ордеров
│   │       └── transactions.py  # Транзакции
│   ├── core/
│   │   ├── config.py            # Настройки приложения
│   │   ├── database.py          # SQLAlchemy + MySQL
│   │   └── redis.py             # Redis клиент
│   ├── integrations/
│   │   └── aifory_client.py     # HTTP клиент Aifory API
│   ├── models/
│   │   ├── user.py              # Модель пользователя
│   │   ├── card.py              # Модель карты
│   │   └── order.py             # Модель ордера
│   ├── schemas/                 # Pydantic схемы
│   ├── services/
│   │   ├── auth_service.py      # Логика авторизации
│   │   ├── card_service.py      # Логика карт
│   │   ├── deposit_service.py   # Логика пополнения
│   │   ├── order_service.py     # Логика ордеров
│   │   └── transaction_service.py
│   └── main.py                  # FastAPI приложение
├── requirements.txt
├── .env.example
└── run.py
```

## Установка

### 1. Создать виртуальное окружение

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Настроить переменные окружения

```bash
cp .env.example .env
# Отредактировать .env
```

**Обязательные переменные:**

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | MySQL connection string |
| `REDIS_URL` | Redis connection string |
| `AIFORY_TOKEN` | Bearer токен Aifory API |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота |
| `JWT_SECRET_KEY` | Секретный ключ для JWT |

### 4. Создать базу данных MySQL

```sql
CREATE DATABASE cards_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. Запустить сервер

```bash
python run.py
```

Сервер запустится на `http://localhost:8000`

## API Документация

После запуска доступна по адресам:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Основные эндпоинты

### Авторизация

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/telegram` | Авторизация через Telegram initData |
| GET | `/api/auth/me` | Текущий пользователь |
| POST | `/api/auth/onboarding/complete` | Завершить онбординг |

### Карты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/cards` | Список карт пользователя |
| GET | `/api/cards/{id}` | Получить карту |
| POST | `/api/cards/{id}/requisites` | Реквизиты карты (не хранятся!) |
| GET | `/api/cards/sync` | Синхронизация с Aifory |

### Выпуск карт

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/offers` | Доступные офферы |
| POST | `/api/offers/calculate` | Расчёт комиссии |
| POST | `/api/offers/issue` | Выпустить карту |

### Пополнение

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/cards/{id}/topup/offer` | Оффер пополнения |
| POST | `/api/cards/{id}/topup/calculate` | Расчёт комиссии |
| POST | `/api/cards/{id}/topup` | Пополнить карту |

### Ордера

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/orders/{id}` | Получить ордер |
| GET | `/api/orders/{id}/status` | Polling статуса |

### Транзакции

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/cards/{id}/transactions` | Список транзакций |
| GET | `/api/cards/{id}/transactions/{tx_id}` | Детали транзакции |

## Финансовая модель

```
┌─────────────────┐
│   Пользователь  │
│   (users.balance)│
└────────┬────────┘
         │ Пополняет через СБП/крипту
         ▼
┌─────────────────┐
│  Твой Backend   │
│  (списывает     │
│   users.balance)│
└────────┬────────┘
         │ Вызывает Aifory API
         ▼
┌─────────────────┐
│   Aifory API    │
│  (твой баланс   │
│   в Aifory)     │
└─────────────────┘
```

**Важно:**
- `users.balance` — баланс пользователя в твоей системе
- При выпуске/пополнении карты списывается `users.balance`
- Aifory списывает с твоего операционного баланса в Aifory
- Если ордер failed/canceled — деньги возвращаются в `users.balance`

## Polling ордеров

После создания ордера (выпуск/пополнение) нужно polling:

```
GET /api/orders/{order_id}/status
```

Интервал: 2-3 секунды, таймаут: 60-90 секунд.

**Статусы:**
- `1` — Pending
- `2` — Success
- `3` — Failed
- `5` — Canceled

## Безопасность

- ✅ Telegram initData валидируется на backend
- ✅ JWT токены для авторизации
- ✅ Реквизиты карт НЕ хранятся в БД
- ✅ Frontend никогда не вызывает Aifory напрямую
- ⚠️ Настроить CORS для production
- ⚠️ Добавить rate limiting

## TODO для production

- [ ] Rate limiting
- [ ] Логирование в файл/ELK
- [ ] Мониторинг (Prometheus/Grafana)
- [ ] Background worker для polling (BullMQ/Celery)
- [ ] Антифрод система
- [ ] Backup базы данных
