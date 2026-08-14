#!/usr/bin/env bash
# Guarda el NUEVO Page Access Token (con instagram_manage_messages agregado)
# directo en .env, oculto, sin que pase por el chat ni quede en el historial.
set -euo pipefail

ENV_FILE="$(dirname "$0")/.env"

echo "Pega el NUEVO Page Access Token (debe incluir TODOS los permisos anteriores + instagram_manage_messages) y presiona Enter (no se mostrará en pantalla):"
read -rs TOKEN
echo
echo

if [[ -z "$TOKEN" ]]; then
  echo "No se recibió ningún token. Abortando, no se tocó .env."
  exit 1
fi

# Backup del token viejo antes de sobrescribir
cp "$ENV_FILE" "$ENV_FILE.bak-$(date +%Y%m%d-%H%M%S)"

grep -v "^META_PAGE_ACCESS_TOKEN=" "$ENV_FILE" > "$ENV_FILE.tmp" || true
{
  cat "$ENV_FILE.tmp"
  echo "META_PAGE_ACCESS_TOKEN=$TOKEN"
} > "$ENV_FILE"
rm -f "$ENV_FILE.tmp"

unset TOKEN

echo "Guardado — verificando permisos del nuevo token (sin exponerlo)..."
cd "$(dirname "$0")"
venv/bin/python3 -c "
import requests, os
from dotenv import load_dotenv
load_dotenv('.env')
T = os.getenv('META_PAGE_ACCESS_TOKEN')
r = requests.get('https://graph.facebook.com/v19.0/debug_token', params={'input_token': T, 'access_token': T}).json()
d = r.get('data', {})
scopes = d.get('scopes', [])
print('is_valid:', d.get('is_valid'))
print('expires_at:', d.get('expires_at'))
print('tiene instagram_manage_messages:', 'instagram_manage_messages' in scopes)
required = ['pages_messaging','instagram_basic','instagram_manage_comments','instagram_content_publish','pages_manage_metadata','pages_manage_posts','catalog_management','business_management','whatsapp_business_management','whatsapp_business_messaging']
faltantes = [s for s in required if s not in scopes]
if faltantes:
    print('⚠️  FALTAN permisos que sí tenía antes:', faltantes)
else:
    print('✅ todos los permisos anteriores siguen presentes')
"
