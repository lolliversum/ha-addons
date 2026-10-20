#!/bin/sh
# Lolliversum Sync: nur der Ordner <standort>/ aus dem Repo landet in /config/lolliversum/.
# Die übrige Home-Assistant-Konfiguration wird NIE angefasst. Vor jedem Neuladen prüft Home Assistant die Konfig;
# ist sie fehlerhaft, bleibt der alte Stand aktiv und es kommt eine Meldung in Home Assistant.
O=/data/options.json
STANDORT=$(jq -r .standort $O); SCHL=$(jq -r .github_schluessel $O); ZWEIG=$(jq -r .zweig $O); TAKT=$(jq -r .takt_minuten $O)
ZIEL=/homeassistant/lolliversum; ARBEIT=/data/repo
API="http://supervisor/core/api"; AUTH="Authorization: Bearer $SUPERVISOR_TOKEN"
melden() { curl -s -X POST -H "$AUTH" -H "Content-Type: application/json" "$API/services/persistent_notification/create" \
  -d "{\"title\":\"Lolliversum Sync\",\"message\":\"$1\",\"notification_id\":\"lolliversum_sync\"}" >/dev/null; }
[ -z "$SCHL" ] && { echo "Kein GitHub-Schlüssel eingetragen."; sleep 3600; exit 1; }
URL="https://x-access-token:${SCHL}@github.com/lolliversum/smarthome.git"
while true; do
  if [ -d "$ARBEIT/.git" ]; then git -C "$ARBEIT" fetch -q origin "$ZWEIG" && git -C "$ARBEIT" reset -q --hard "origin/$ZWEIG"
  else git clone -q --depth 1 -b "$ZWEIG" "$URL" "$ARBEIT"; fi || { echo "GitHub nicht erreichbar"; sleep 60; continue; }
  NEU=$(git -C "$ARBEIT" rev-parse --short HEAD); ALT=$(cat /data/stand 2>/dev/null)
  if [ "$NEU" != "$ALT" ] && [ -d "$ARBEIT/$STANDORT" ]; then
    mkdir -p "$ZIEL"; cp -a "$ZIEL" /data/vorher 2>/dev/null
    rsync -a --delete "$ARBEIT/$STANDORT/" "$ZIEL/"
    ERG=$(curl -s -X POST -H "$AUTH" "$API/config/core/check_config" | jq -r .result)
    if [ "$ERG" = "valid" ]; then
      curl -s -X POST -H "$AUTH" "$API/services/homeassistant/reload_all" >/dev/null
      echo "$NEU" > /data/stand; echo "Stand $NEU geladen ($STANDORT)"
    else
      rm -rf "$ZIEL"; cp -a /data/vorher "$ZIEL" 2>/dev/null
      melden "Neuer Stand $NEU fehlerhaft, alter Stand bleibt aktiv."; echo "Stand $NEU fehlerhaft – zurückgerollt"
    fi
  fi
  sleep $((TAKT*60))
done
