#!/usr/bin/env bash
# Kamera-Monitor: zeigt die Kameras aus /etc/kamera-monitor/kameras.conf als Raster.
# Läuft innerhalb von X (startx), wird beim Einschalten automatisch gestartet.
# Vorrang: kameras.conf auf der SD-Karte (Boot-Partition, am PC bearbeitbar), sonst /etc
if [ -n "${KAMERA_KONF:-}" ]; then KONF="$KAMERA_KONF"
elif [ -f /boot/firmware/kameras.conf ]; then KONF=/boot/firmware/kameras.conf
else KONF=/etc/kamera-monitor/kameras.conf; fi

# Bildschirm wach halten, Mauszeiger weg
xset s off 2>/dev/null; xset s noblank 2>/dev/null; xset -dpms 2>/dev/null
command -v unclutter >/dev/null && unclutter -idle 0.5 -root &
xsetroot -solid black 2>/dev/null

# Fernseher per HDMI-CEC einschalten und auf diesen Eingang stellen
if command -v cec-client >/dev/null; then
  ( echo "on 0" | cec-client -s -d 1 >/dev/null 2>&1
    sleep 2
    echo "as"   | cec-client -s -d 1 >/dev/null 2>&1 ) &
fi

# Kameras einlesen: Zeilen "Name|rtsp://..." (Leerzeilen und # werden ignoriert)
NAMEN=(); QUELLEN=()
while IFS='|' read -r name url; do
  name="$(echo "$name" | xargs)"; url="$(echo "${url:-}" | xargs)"
  [ -z "$name" ] && continue
  case "$name" in \#*) continue ;; esac
  [ -z "$url" ] && continue
  NAMEN+=("$name"); QUELLEN+=("$url")
done < <(tr -d '\r' < "$KONF")

ANZAHL=${#QUELLEN[@]}
if [ "$ANZAHL" -eq 0 ]; then
  xmessage -center "Keine Kameras eingetragen: $KONF" 2>/dev/null
  sleep 3600; exit 0
fi

# Raster festlegen
if   [ "$ANZAHL" -le 1 ]; then SP=1; ZE=1
elif [ "$ANZAHL" -le 2 ]; then SP=2; ZE=1
elif [ "$ANZAHL" -le 4 ]; then SP=2; ZE=2
elif [ "$ANZAHL" -le 6 ]; then SP=3; ZE=2
else                           SP=3; ZE=3
fi
[ "$ANZAHL" -gt $((SP*ZE)) ] && ANZAHL=$((SP*ZE))

# Bildschirmgröße
GROESSE="$(xrandr 2>/dev/null | awk '/\*/{print $1; exit}')"
BREITE="${GROESSE%x*}"; HOEHE="${GROESSE#*x}"
[[ "$BREITE" =~ ^[0-9]+$ ]] || BREITE=1920
[[ "$HOEHE"  =~ ^[0-9]+$ ]] || HOEHE=1080
KB=$((BREITE / SP)); KH=$((HOEHE / ZE))

kamera() {   # $1 Name, $2 URL, $3 Geometrie
  while true; do
    mpv "$2" \
      --geometry="$3" --no-border --ontop=no --force-window=immediate \
      --keepaspect=yes --no-keepaspect-window \
      --profile=low-latency --untimed --no-cache --rtsp-transport=tcp \
      --network-timeout=5 --hwdec=auto-safe --no-audio \
      --osd-msg1="$1" --osd-level=1 --osd-font-size=26 --osd-align-x=left --osd-align-y=top \
      --no-input-default-bindings --input-vo-keyboard=no --no-osc --really-quiet \
      --title="$1" >/dev/null 2>&1
    sleep 3   # Kamera weg oder Netz weg → neu verbinden
  done
}

for ((i=0; i<ANZAHL; i++)); do
  X=$(( (i % SP) * KB )); Y=$(( (i / SP) * KH ))
  kamera "${NAMEN[$i]}" "${QUELLEN[$i]}" "${KB}x${KH}+${X}+${Y}" &
  sleep 0.5
done

wait
