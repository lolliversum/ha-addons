#!/usr/bin/env bash
# Kamera-Monitor: zeigt Kameras als Raster am TV (läuft in X, Autostart beim Einschalten).
#
# Quelle der Kameraliste (in dieser Reihenfolge):
#  1) Home Assistant: Helfer input_text (z. B. "presse, halle, tor"), Streams von go2rtc
#     Einstellungen in kamera-monitor.ini (SD-Karte bootfs oder /etc/kamera-monitor/)
#  2) sonst kameras.conf mit Zeilen "Name | rtsp://..." (SD-Karte oder /etc/kamera-monitor/)
# Die Liste wird alle 30 s geprüft; ändert sie sich, wird das Raster neu aufgebaut.
# Ist HA nicht erreichbar, bleibt die zuletzt bekannte Liste stehen.

INI=""; for f in "${KAMERA_INI:-}" /boot/firmware/kamera-monitor.ini /etc/kamera-monitor/kamera-monitor.ini; do
  [ -n "$f" ] && [ -f "$f" ] && { INI="$f"; break; }; done
KONF=""; for f in "${KAMERA_KONF:-}" /boot/firmware/kameras.conf /etc/kamera-monitor/kameras.conf; do
  [ -n "$f" ] && [ -f "$f" ] && { KONF="$f"; break; }; done
CACHE="${KAMERA_CACHE:-$HOME/.kamera-monitor-liste}"
TAKT="${KAMERA_TAKT:-30}"

ini() {   # ini SCHLUESSEL STANDARD
  local w=""
  [ -n "$INI" ] && w="$(tr -d '\r' < "$INI" | sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" | tail -1 | sed 's/[[:space:]]*$//')"
  echo "${w:-$2}"
}
HA_URL="$(ini ha_url "")"; HA_URL="${HA_URL%/}"
HA_TOKEN="$(ini ha_token "")"
HA_HELFER="$(ini ha_helfer "input_text.kamera_monitor_produktion")"
HOST="$(echo "$HA_URL" | sed -E 's#^[a-z]+://##; s#[:/].*$##')"
STREAMS="$(ini stream_basis "rtsp://${HOST:-127.0.0.1}:8554/")"

# Bildschirm wach halten, Mauszeiger weg, Fernseher per CEC an
xset s off 2>/dev/null; xset s noblank 2>/dev/null; xset -dpms 2>/dev/null
command -v unclutter >/dev/null && unclutter -idle 0.5 -root &
xsetroot -solid black 2>/dev/null
if command -v cec-client >/dev/null; then
  ( echo "on 0" | cec-client -s -d 1 >/dev/null 2>&1; sleep 2
    echo "as"   | cec-client -s -d 1 >/dev/null 2>&1 ) &
fi

GROESSE="$(xrandr 2>/dev/null | awk '/\*/{print $1; exit}')"
BREITE="${GROESSE%x*}"; HOEHE="${GROESSE#*x}"
[[ "$BREITE" =~ ^[0-9]+$ ]] || BREITE=1920
[[ "$HOEHE"  =~ ^[0-9]+$ ]] || HOEHE=1080

# Liefert die Kameraliste als Zeilen "Name|URL" (leer = keine Antwort)
liste_holen() {
  if [ -n "$HA_URL" ] && [ -n "$HA_TOKEN" ]; then
    local antwort wert
    antwort="$(curl -fsS -m 8 -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/$HA_HELFER" 2>/dev/null)" || return 1
    wert="$(printf '%s' "$antwort" | jq -r '.state // empty' 2>/dev/null)" || return 1
    case "$wert" in unknown|unavailable) wert="" ;; esac
    printf '%s\n' "$wert" | tr ',;' '\n\n' | while IFS= read -r eintrag; do
      eintrag="$(echo "$eintrag" | xargs)"; [ -z "$eintrag" ] && continue
      case "$eintrag" in
        *=rtsp://*) echo "${eintrag%%=*}|${eintrag#*=}" ;;          # Name=rtsp://... direkt
        rtsp://*)   echo "${eintrag##*/}|$eintrag" ;;
        *)          echo "$eintrag|${STREAMS}${eintrag}" ;;          # Streamname in go2rtc
      esac
    done
    echo "#ok"
  elif [ -n "$KONF" ]; then
    tr -d '\r' < "$KONF" | while IFS='|' read -r name url; do
      name="$(echo "$name" | xargs)"; url="$(echo "${url:-}" | xargs)"
      [ -z "$name" ] || [ -z "$url" ] && continue
      case "$name" in \#*) continue ;; esac
      echo "$name|$url"
    done
    echo "#ok"
  else
    return 1
  fi
}

kamera() {   # $1 Name, $2 URL, $3 Geometrie
  while true; do
    mpv "$2" \
      --geometry="$3" --no-border --ontop=no --force-window=immediate \
      --keepaspect=yes --no-keepaspect-window \
      --profile=low-latency --untimed --no-cache --rtsp-transport=tcp \
      --network-timeout=5 --hwdec=auto-safe --no-audio \
      --osd-msg1="$1" --osd-level=1 --osd-font-size=26 --osd-align-x=left --osd-align-y=top \
      --no-input-default-bindings --input-vo-keyboard=no --no-osc --really-quiet \
      --title="kmon $1" >/dev/null 2>&1
    sleep 3   # Kamera oder Netz weg → neu verbinden
  done
}

SCHLEIFEN=()
alle_stoppen() {
  for p in "${SCHLEIFEN[@]}"; do kill "$p" 2>/dev/null; done
  SCHLEIFEN=()
  pkill -f "title=kmon " 2>/dev/null
  pkill -x xmessage 2>/dev/null
}

raster_starten() {   # Zeilen "Name|URL" auf stdin
  local namen=() quellen=() n s z i x y kb kh
  while IFS='|' read -r name url; do [ -n "$url" ] && { namen+=("$name"); quellen+=("$url"); }; done
  n=${#quellen[@]}
  if [ "$n" -eq 0 ]; then
    (xmessage -center "Keine Kameras ausgewählt (Home Assistant: Kamera-Monitor Produktion)" 2>/dev/null &)
    return
  fi
  if   [ "$n" -le 1 ]; then s=1; z=1
  elif [ "$n" -le 2 ]; then s=2; z=1
  elif [ "$n" -le 4 ]; then s=2; z=2
  elif [ "$n" -le 6 ]; then s=3; z=2
  else                      s=3; z=3; fi
  [ "$n" -gt $((s*z)) ] && n=$((s*z))
  kb=$((BREITE / s)); kh=$((HOEHE / z))
  for ((i=0; i<n; i++)); do
    x=$(( (i % s) * kb )); y=$(( (i / s) * kh ))
    kamera "${namen[$i]}" "${quellen[$i]}" "${kb}x${kh}+${x}+${y}" &
    SCHLEIFEN+=($!)
    sleep 0.3
  done
}

trap 'alle_stoppen; exit 0' TERM INT

AKTUELL="__start__"
while true; do
  if NEU="$(liste_holen)" && printf '%s' "$NEU" | grep -q '^#ok$'; then
    NEU="$(printf '%s\n' "$NEU" | grep -v '^#ok$')"
    printf '%s\n' "$NEU" > "$CACHE" 2>/dev/null
  elif [ "$AKTUELL" = "__start__" ] && [ -f "$CACHE" ]; then
    NEU="$(cat "$CACHE")"          # HA beim Start nicht erreichbar → letzte bekannte Liste
  else
    NEU="$AKTUELL"                 # HA gerade weg → so lassen
  fi
  if [ "$NEU" != "$AKTUELL" ]; then
    alle_stoppen
    raster_starten < <(printf "%s\n" "$NEU")
    AKTUELL="$NEU"
  fi
  sleep "$TAKT"
done
