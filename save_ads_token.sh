#!/usr/bin/env bash
# Guarda el token de Ads (act_2472515443131861) directo en .env, oculto,
# sin que pase por el chat ni quede en el historial de bash.
set -euo pipefail

ENV_FILE="$(dirname "$0")/.env"
ACCOUNT_ID="act_2472515443131861"

echo "Pega el token de Ads (ads_management + ads_read) y presiona Enter (no se mostrará en pantalla):"
read -rs TOKEN
echo
echo

if [[ -z "$TOKEN" ]]; then
  echo "No se recibió ningún token. Abortando, no se tocó .env."
  exit 1
fi

# Quita líneas previas de estas claves si existían, y agrega las nuevas
grep -v "^META_ADS_ACCESS_TOKEN=\|^META_AD_ACCOUNT_ID=" "$ENV_FILE" > "$ENV_FILE.tmp" || true
{
  cat "$ENV_FILE.tmp"
  echo "META_ADS_ACCESS_TOKEN=$TOKEN"
  echo "META_AD_ACCOUNT_ID=$ACCOUNT_ID"
} > "$ENV_FILE"
rm -f "$ENV_FILE.tmp"

unset TOKEN

echo "Guardado en .env — el token no se mostró ni quedó en el historial de la terminal."
echo "Verificando validez del token (sin exponerlo)..."
cd "$(dirname "$0")"
venv/bin/python3 -c "
import requests, os
from dotenv import load_dotenv
load_dotenv('.env')
T = os.getenv('META_ADS_ACCESS_TOKEN')
r = requests.get('https://graph.facebook.com/v20.0/debug_token', params={'input_token': T, 'access_token': T}).json()
d = r.get('data', {})
print('is_valid:', d.get('is_valid'))
print('scopes:', d.get('scopes'))
print('expires_at:', d.get('expires_at'))
"
