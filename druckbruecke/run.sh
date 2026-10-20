#!/bin/sh
# Optionen aus der Add-on-Seite in die Umgebung der Druckbrücke übernehmen (Schlüssel bleibt im Gerät).
O=/data/options.json
export DRUCK_SERVER="$(python3 -c "import json;print(json.load(open('$O'))['server'])")"
export DRUCK_STANDORT="$(python3 -c "import json;print(json.load(open('$O'))['standort'])")"
export DRUCK_TOKEN="$(python3 -c "import json;print(json.load(open('$O'))['schluessel'])")"
export DRUCK_NETZE="$(python3 -c "import json;print(json.load(open('$O'))['netze'])")"
export PYTHONUNBUFFERED=1
if [ -z "$DRUCK_TOKEN" ]; then
  echo "Kein Schlüssel eingetragen: im Portal /druck bei '$DRUCK_STANDORT' Schlüssel erzeugen und hier unter Konfiguration eintragen."
  sleep 3600; exit 1
fi
python3 /app/druckbruecke.py --pruefen || echo "Prüfung fehlgeschlagen – läuft trotzdem weiter und versucht es erneut."
exec python3 /app/druckbruecke.py
