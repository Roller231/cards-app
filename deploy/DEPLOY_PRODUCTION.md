# Production deploy: prontopay.pro (Docker + Nginx + Certbot)

## 1) Server prep (Ubuntu 22.04/24.04)

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release

# Docker repo
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# optional: run docker without sudo (re-login needed)
sudo usermod -aG docker $USER
```

## 2) DNS

Point both records to your server IP:
- `A prontopay.pro`
- `A www.prontopay.pro`

## 3) Upload project

```bash
# example
sudo mkdir -p /opt/prontopay
sudo chown -R $USER:$USER /opt/prontopay
git clone <your_repo_url> /opt/prontopay
cd /opt/prontopay
```

## 4) Configure env files

### 4.1 Root compose env

```bash
cp .env.prod.example .env.prod
nano .env.prod
```

Set strong DB passwords and certbot email.

### 4.2 Backend app env

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

Important values:
- `DATABASE_URL=mysql+aiomysql://cards_user:<MYSQL_PASSWORD>@db:3306/cards_app`
- `SECRET_KEY=<strong random>`
- `AIFORY_*`
- `ABCEX_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `ADMIN_EMAIL`, `ADMIN_PASSWORD`

## 5) First start (HTTP only)

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build db backend frontend nginx
```

Check:
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f nginx
```

At this step `http://prontopay.pro` must open.

## 6) Get SSL cert (Certbot webroot)

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d prontopay.pro -d www.prontopay.pro \
  --email "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email
```

If successful, cert files are in the shared `certbot_conf` volume.

## 7) Enable HTTPS nginx config

```bash
cp deploy/nginx/conf.d/ssl.conf deploy/nginx/conf.d/active.conf
docker compose --env-file .env.prod -f docker-compose.prod.yml restart nginx
```

Now verify:
- `https://prontopay.pro`
- `https://www.prontopay.pro`

## 8) Renewal (cron)

Open crontab:
```bash
crontab -e
```

Add:
```cron
0 3 * * * cd /opt/prontopay && docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm certbot renew --webroot -w /var/www/certbot && docker compose --env-file .env.prod -f docker-compose.prod.yml restart nginx >/dev/null 2>&1
```

## 9) Useful commands

```bash
# restart stack
docker compose --env-file .env.prod -f docker-compose.prod.yml restart

# pull logs
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f backend

# rebuild after code changes
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```
