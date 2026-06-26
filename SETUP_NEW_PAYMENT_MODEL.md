# Новая модель оплаты выпуска карт

## Что изменилось

**Старая модель:**
- Пользователь вводил сумму для пополнения карты
- Система добавляла комиссию
- Пользователь оплачивал итоговую сумму

**Новая модель:**
- Админ устанавливает фиксированную цену выпуска карты
- Пользователь оплачивает фиксированную цену
- Карта выпускается с нулевым балансом
- Пользователь может пополнить карту после выпуска

## Запуск локально с dev-пользователем

### 1. Запустить Docker Compose

```powershell
cd d:\GitPR\cards-app
docker compose -f docker-compose.dev.yml up --build
```

### 2. Открыть приложение

Откройте в браузере: `http://localhost:8080`

### 3. Войти как dev-пользователь

1. Сделайте жёсткий перезапуск страницы (Ctrl+Shift+R)
2. Нажмите кнопку **"Dev auth"** (или "Войти без Telegram")
3. Вы автоматически войдёте как `dev_user` с балансом $1000

### 4. Настроить цены в админ-панели

#### Войти в админку:

1. Откройте `http://localhost:8080/admin`
2. Логин: `admin`
3. Пароль: `admin123`

#### Установить цену:

1. Перейдите в раздел **"Settings"**
2. Найдите настройку:
   - **CARD_ISSUANCE_PRICE_USD** - цена выпуска карты (по умолчанию: 10.0)
3. Установите нужное значение и сохраните

**Пример:**
- CARD_ISSUANCE_PRICE_USD = 15.0

Это означает:
- Пользователь платит $15
- Карта выпускается с нулевым балансом
- Вся сумма $15 - ваша прибыль

### 5. Протестировать выпуск карты

1. Вернитесь на главную страницу (`http://localhost:8080`)
2. Нажмите **"Выпустить карту"**
3. Выберите тип карты
4. Вы увидите фиксированную цену выпуска и начальный баланс
5. Выберите способ оплаты (СБП)
6. Подтвердите и выпустите карту

## Как это работает внутри

### Backend

1. **Получение цены** (`GET /cards/issuance-price`):
   - Читает настройки `CARD_ISSUANCE_PRICE_USD` и `CARD_INITIAL_BALANCE_USD` из БД
   - Возвращает их фронтенду

2. **Выпуск карты** (`POST /cards/issue`):
   - Проверяет баланс пользователя (должен быть >= CARD_ISSUANCE_PRICE_USD)
   - Списывает с пользователя CARD_ISSUANCE_PRICE_USD
   - Переводит CARD_INITIAL_BALANCE_USD с родительского O-Plata аккаунта на дочерний аккаунт пользователя
   - Выпускает карту через O-Plata API
   - Карта автоматически пополняется на CARD_INITIAL_BALANCE_USD

### Frontend

- **IssueCardPage**: Показывает фиксированную цену вместо поля ввода суммы
- **API client**: Убран параметр `amount` из запроса выпуска карты

### Database

Настройки хранятся в таблице `admin_settings`:
```sql
INSERT INTO admin_settings (key, value, description) VALUES
('CARD_ISSUANCE_PRICE_USD', '10.0', 'Card issuance price (USD) - user pays this fixed amount'),
('CARD_INITIAL_BALANCE_USD', '5.0', 'Card initial balance (USD) - transferred from parent to user O-Plata account');
```

## Важные моменты

1. **Родительский аккаунт O-Plata** должен иметь достаточный баланс USDT для пополнения дочерних аккаунтов
2. **CARD_INITIAL_BALANCE_USD** не должен превышать баланс родительского аккаунта
3. **Разница** между CARD_ISSUANCE_PRICE_USD и CARD_INITIAL_BALANCE_USD - ваша прибыль
4. Пользователь видит только фиксированную цену, внутренняя логика переводов скрыта

## Troubleshooting

### Ошибка "Insufficient balance"
- Убедитесь, что у dev_user есть баланс >= CARD_ISSUANCE_PRICE_USD
- По умолчанию dev_user создаётся с балансом $1000

### Ошибка при переводе с родительского аккаунта
- Проверьте, что родительский O-Plata аккаунт (`OPLATA_PARENT_CLIENT_ID` в `.env`) имеет достаточный баланс USDT
- Проверьте логи: `docker compose -f docker-compose.dev.yml logs backend`

### Настройки не применяются
- Убедитесь, что вы сохранили изменения в админ-панели
- Перезагрузите страницу выпуска карты (Ctrl+Shift+R)
- Проверьте БД: `docker compose -f docker-compose.dev.yml exec db mysql -u cards_user -p141722A! cards_app -e "SELECT * FROM admin_settings WHERE key LIKE 'CARD_%'"`

## API Endpoints

### GET /cards/issuance-price
Получить текущую цену выпуска карты

**Response:**
```json
{
  "price": 10.0,
  "initial_balance": 5.0,
  "description": "Card issuance costs $10.00 USD. Card will be issued with $5.00 USD initial balance."
}
```

### POST /cards/issue
Выпустить карту (без параметра amount)

**Request:**
```json
{
  "offer_id": "RAVANA:RT-TEST-1-int:uuid",
  "holder_first_name": "John",
  "holder_last_name": "Doe",
  "email": "user@example.com",
  "payment_method": "sbp"
}
```

### Admin Settings API

**GET /admin/settings** - получить все настройки
**PUT /admin/settings** - обновить настройки

```json
{
  "CARD_ISSUANCE_PRICE_USD": "15.0",
  "CARD_INITIAL_BALANCE_USD": "10.0"
}
```
