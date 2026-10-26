#!/bin/bash
# LABS auf dem Pi beenden (Desktop-Symbol "LABS beenden"): Backend sauber herunterfahren
# (/api/shutdown schaltet die Geraete ab: Netzteile aus, MFC-Ventile in Ruhelage), dann Frontend beenden.
set -u
echo "=== LABS beenden  $(date '+%d.%m.%Y %H:%M') ==="
STATUS=$(curl -s -m 2 http://127.0.0.1:11123/api/station_overview)
if echo "$STATUS" | grep -q '"status": "Busy"'; then
  echo "ACHTUNG: Es laeuft gerade ein Experiment: $STATUS"
  read -r -p "Trotzdem beenden? (j/N) " answer
  [ "$answer" = "j" ] || { echo "Abgebrochen."; read -r -p "Enter zum Schliessen ..." _; exit 0; }
fi
# Prozesse ueber ihre Ports finden (kein pkill -f: das traefe auch dieses Skript)
for port in 11123 5000; do
  for pid in $(ss -ltnp 2>/dev/null | grep ":$port " | grep -o "pid=[0-9]*" | cut -d= -f2 | sort -u); do
    if [ "$port" = 11123 ]; then
      echo "Backend (PID $pid): Geraete abschalten (/api/shutdown) ..."
      curl -s -m 5 http://127.0.0.1:11123/api/shutdown >/dev/null
      sleep 3
    fi
    echo "Beende PID $pid (Port $port)"
    kill "$pid" 2>/dev/null
  done
done
sleep 2
ss -ltn | grep -qE ":(11123|5000) " && echo "Noch nicht alles beendet - ggf. nochmal versuchen." || echo "Backend und Frontend beendet."
read -r -p "Enter zum Schliessen ..." _
