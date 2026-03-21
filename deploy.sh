#!/bin/bash
# deploy.sh — wdróż aplikację na serwer Linux (Ubuntu/Debian)
# Uruchom na SERWERZE jako root lub sudo:
#   bash deploy.sh twojadomena.pl

set -e
DOMAIN=${1:-"twojadomena.pl"}
APP_DIR="/var/www/rzeczy"
SERVICE="rzeczy"

echo "================================================"
echo "  Deploy: Rzeczy z Drugiej Ręki → $DOMAIN"
echo "================================================"

# 1. Aktualizacja systemu
echo "[1/8] Aktualizacja pakietów..."
apt-get update -q && apt-get install -y -q python3 python3-pip nginx certbot python3-certbot-nginx

# 2. Skopiuj pliki
echo "[2/8] Kopiowanie plików..."
mkdir -p $APP_DIR
cp -r . $APP_DIR/
mkdir -p $APP_DIR/backend/uploads
cd $APP_DIR

# 3. Zależności Pythona
echo "[3/8] Instalacja zależności..."
pip3 install -r backend/requirements.txt

# 4. Plik .env — jeśli nie istnieje, stwórz z przykładu
if [ ! -f "$APP_DIR/backend/.env" ]; then
    cp $APP_DIR/backend/.env.example $APP_DIR/backend/.env
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/zmien-to-na-losowy-dlugi-ciag-znakow/$SECRET/" $APP_DIR/backend/.env
    sed -i "s|http://localhost:8080|https://$DOMAIN|" $APP_DIR/backend/.env
    echo ""
    echo "⚠️  UZUPEŁNIJ: $APP_DIR/backend/.env (Stripe keys!)"
    echo ""
fi

# 5. Inicjalizacja bazy
echo "[4/8] Inicjalizacja bazy danych..."
cd $APP_DIR/backend && python3 -c "from db import init_db; init_db()"
cd $APP_DIR/backend && python3 seed.py 2>/dev/null || true

# 6. Nginx
echo "[5/8] Konfiguracja Nginx..."
sed "s/twojadomena.pl/$DOMAIN/g" $APP_DIR/nginx.conf > /etc/nginx/sites-available/rzeczy
ln -sf /etc/nginx/sites-available/rzeczy /etc/nginx/sites-enabled/rzeczy
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# 7. SSL (Let's Encrypt)
echo "[6/8] Certyfikat SSL..."
certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN || \
    echo "⚠️  SSL nie powiódł się — skonfiguruj ręcznie: certbot --nginx -d $DOMAIN"

# 8. Systemd service
echo "[7/8] Tworzenie usługi systemd..."
cat > /etc/systemd/system/rzeczy.service << EOF
[Unit]
Description=Rzeczy z Drugiej Reki — Flask/Gunicorn
After=network.target

[Service]
User=www-data
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/backend/.env
ExecStart=/usr/local/bin/gunicorn -c gunicorn.conf.py app:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable rzeczy
systemctl restart rzeczy

# Uprawnienia
chown -R www-data:www-data $APP_DIR
chmod -R 755 $APP_DIR/backend/uploads

echo "[8/8] Gotowe!"
echo ""
echo "================================================"
echo "  ✅ Aplikacja dostępna pod: https://$DOMAIN"
echo "  📋 Logi: journalctl -u rzeczy -f"
echo "  🔄 Restart: systemctl restart rzeczy"
echo "  📁 Pliki: $APP_DIR"
echo "================================================"
