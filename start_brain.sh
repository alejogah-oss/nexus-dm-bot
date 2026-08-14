#!/bin/bash
# NEXUS Brain Server — arranca el WebSocket y abre brain.html

NEXUS_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$NEXUS_DIR/venv/bin/python3"
BRAIN="$NEXUS_DIR/brain.html"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  NEXUS BRAIN — modo LIVE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Mata instancia anterior si existe
pkill -f "brain_server.py" 2>/dev/null
sleep 0.3

# Abre brain.html
open "$BRAIN"
echo "  brain.html abierto"
echo ""
echo "  Esperando conexión en ws://localhost:8765"
echo "  En el browser: click  ⚡ RUN REAL  para correr todo"
echo ""
echo "  Ctrl+C para detener el servidor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$NEXUS_DIR"
exec "$PYTHON" brain_server.py
