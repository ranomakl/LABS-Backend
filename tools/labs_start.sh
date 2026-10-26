#!/bin/bash
# LABS auf dem Pi starten - fuer das Desktop-Symbol "LABS starten" (26.10.2026).
# Holt den neuesten Stand (git pull), startet Backend und Frontend im Hintergrund (Logs in
# LABS-Backend/logs/), wartet bis beide antworten und oeffnet Chromium mit dem Frontend.
# Laeuft in einem Terminalfenster, damit man sieht, was passiert; das Fenster bleibt offen.
set -u
BACKEND=/home/pohlma/LABS/LABS-Backend
FRONTEND=/home/pohlma/LABS/LABS-User-Interface
URL=http://localhost:5000

echo "=== LABS starten  $(date '+%d.%m.%Y %H:%M') ==="
echo
if ss -ltn | grep -q ":11123 "; then
  echo "Backend laeuft schon (Port 11123) - nichts gestartet."
  BACKEND_RUNNING=1
else
  BACKEND_RUNNING=0
fi

echo "--- Neuesten Stand holen (git pull) ---"
for repo in "$BACKEND" "$FRONTEND"; do
  (cd "$repo" && git pull --ff-only 2>&1 | tail -1)
done
echo

if [ "$BACKEND_RUNNING" = 0 ]; then
  echo "--- Backend starten (Log: logs/backend_stdout.log) ---"
  cd "$BACKEND" || exit 1
  mkdir -p logs
  nohup .venv/bin/python main.py >> logs/backend_stdout.log 2>&1 &
  for i in $(seq 1 60); do
    sleep 1
    curl -s -m 1 http://127.0.0.1:11123/api/station_overview >/dev/null 2>&1 && break
    [ "$i" = 60 ] && echo "FEHLER: Backend antwortet nach 60 s nicht - Log pruefen: logs/backend_stdout.log"
  done
  echo "Backend-Status: $(curl -s -m 2 http://127.0.0.1:11123/api/station_overview)"
  echo
  echo "--- Warnungen beim Geraetestart (sollte leer sein) ---"
  tail -400 logs/backend_stdout.log | grep -iE "nicht verfuegbar|uebersprungen|nicht verbunden|Gasstrom-Ventil|Could not|CONNECTION LOST|Error" | tail -12
  echo
fi

if ss -ltn | grep -q ":5000 "; then
  echo "Frontend laeuft schon (Port 5000)."
else
  echo "--- Frontend starten (Log: logs/frontend_stdout.log) ---"
  cd "$FRONTEND" || exit 1
  nohup .venv/bin/flask run --host=0.0.0.0 >> "$BACKEND/logs/frontend_stdout.log" 2>&1 &
  for i in $(seq 1 30); do
    sleep 1
    curl -s -m 1 -o /dev/null $URL && break
  done
fi

echo "--- Browser oeffnen: $URL ---"
nohup chromium "$URL" >/dev/null 2>&1 &
echo
echo "Fertig. Dieses Fenster kann offen bleiben (oder geschlossen werden, Backend und Frontend laufen weiter)."
echo "Beenden: Desktop-Symbol 'LABS beenden' oder tools/labs_stop.sh."
echo
read -r -p "Enter zum Schliessen ..." _
