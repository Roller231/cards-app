# Чеклист деплоя на prontopay.pro

## 1. Подготовка на сервере

```bash
# Клонировать репозиторий
git clone https://github.com/Roller231/cards-app.git
cd cards-app

# Скопировать prod env
cp .env.prod.example .env
```

## 2. Заполнить `.env` (корневой)

```bash
# MySQL
MYSQL_ROOT_PASSWORD=141722A!
MYSQL_DATABASE=cards_app
MYSQL_USER=cards_user
MYSQL_PASSWORD=141722A!

# Certbot
LETSENCRYPT_EMAIL=admin@prontopay.pro

# Database URL
DATABASE_URL=mysql+aiomysql://cards_user:141722A!@db:3306/cards_app

# Bitbanker SBP (DEV контур)
BITBANKER_API_KEY=Z9aXX6x8A5WwBqUsgv30w-a4IHDcRQrA
BITBANKER_API_SECRET=IKgT2tRCygeB-UUQ0NY2Zx9VCqvLg5sfAX6l0nYNba_05kloT8lh31aSyvWTBH-5eSH5mqjTadNJo9RZrxuAiaiulyw9TJQrSbn7dSjiM-xHSk8-q99_IW9l9rulQGzv
BITBANKER_BASE_URL=https://api.aws.dev.bitbanker.org/latest
```

## 3. Создать `backend/.env`

```bash
cp backend/.env.example backend/.env
```

Заполнить:

```bash
DATABASE_URL=mysql+aiomysql://cards_user:141722A!@db:3306/cards_app
SECRET_KEY=<сгенерировать случайный ключ>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# O-Plata API (твои реальные ключи)
OPLATA_BASE_URL=https://int.o-plata.com:443
OPLATA_PRODUCT_ID="TEST CLARUS 7"
OPLATA_PRIVATE_KEY=3e9368ec3c5073965c78be10b5849452f6565098a6b7bfe019deec55144ab5a9
OPLATA_PUBLIC_KEY=50756cfb163856e408a9015f07236a62e5a45f94e59e58b7d94377aa607def54
OPLATA_CALLBACK_PUBLIC_KEY=F542D2BCFDE318EB6487AF72D7FE88D53CD55BEB20F3EBD6E1C9C019184974E9
OPLATA_TEST_CLIENT_ID=Developer
OPLATA_PARENT_CLIENT_ID=Developer

# Telegram
TELEGRAM_BOT_TOKEN=8671315272:AAFOeW_h2w3tUQT9Fi07741IwR28aqLzSPE

# Admin
ADMIN_EMAIL=exprontopay@gmail.com
ADMIN_PASSWORD=exprontoPay2026.

# Bitbanker SBP
BITBANKER_API_KEY=Z9aXX6x8A5WwBqUsgv30w-a4IHDcRQrA
BITBANKER_API_SECRET=IKgT2tRCygeB-UUQ0NY2Zx9VCqvLg5sfAX6l0nYNba_05kloT8lh31aSyvWTBH-5eSH5mqjTadNJo9RZrxuAiaiulyw9TJQrSbn7dSjiM-xHSk8-q99_IW9l9rulQGzv
BITBANKER_BASE_URL=https://api.aws.dev.bitbanker.org/latest

# Dev logs
DETAILED_DEV_LOGS=false
```

## 4. Получить SSL-сертификат (первый раз)

```bash
# Временно запустить только nginx для certbot
docker compose -f docker-compose.prod.yml up -d nginx

# Получить сертификат
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email admin@prontopay.pro \
  --agree-tos \
  --no-eff-email \
  -d prontopay.pro \
  -d www.prontopay.pro

# Остановить nginx
docker compose -f docker-compose.prod.yml down
```

## 5. Запустить всё

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## 6. Проверить логи

```bash
# Backend
docker logs prontopay-backend -f

# Frontend
docker logs prontopay-frontend -f

# Nginx
docker logs prontopay-nginx -f

# DB
docker logs prontopay-db -f
```

## 7. Проверить работу

### API Health
```bash
curl https://prontopay.pro/api/auth/config
```

### Swagger
```
https://prontopay.pro/api/docs
```

### Frontend
```
https://prontopay.pro
```

## 8. Тест SBP флоу

1. Залогиниться в приложение
2. Попытаться выпустить карту → откроется SbpPaymentModal
3. Ввести сумму (например, 1000 ₽)
4. Получить QR-код
5. **В Bitbanker DEV-панели** — найти инвойс и вручную изменить статус на `captured`
6. Через 5 секунд поллинг подхватит статус → баланс пополнится → карта выпустится

## 9. Webhook Bitbanker

URL для регистрации в Bitbanker DEV-панели:
```
https://prontopay.pro/api/sbp/webhook
```

Проверить вебхук можно через логи:
```bash
docker logs prontopay-backend | grep "\[SBP\] Webhook"
```

## 10. Обновление после изменений

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## Troubleshooting

### Если база не поднялась
```bash
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d
```

### Если SSL не работает
```bash
# Проверить сертификаты
docker compose -f docker-compose.prod.yml exec nginx ls -la /etc/letsencrypt/live/prontopay.pro/

# Перезапустить nginx
docker compose -f docker-compose.prod.yml restart nginx
```

### Если вебхук не приходит
- Проверить, что URL в Bitbanker: `https://prontopay.pro/api/sbp/webhook`
- Проверить логи: `docker logs prontopay-backend | grep SBP`
- Проверить, что `BITBANKER_API_SECRET` совпадает с тем, что в Bitbanker-панели
