#!/bin/bash
# Corre el Marketplace Inbox Bot en modo LOCAL (usa perfil completo del browser)
# Uso: ./run_marketplace_local.sh
# Para correr en background: nohup ./run_marketplace_local.sh &

cd /Users/macbookpro/nexus-automation

LOG=marketplace_local.log
echo "[$(date)] Iniciando Marketplace Inbox Bot LOCAL" >> "$LOG"

LOCAL_MODE=1 venv/bin/python3 marketplace_inbox_bot.py >> "$LOG" 2>&1
