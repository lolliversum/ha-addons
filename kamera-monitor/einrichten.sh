#!/usr/bin/env bash
# Kamera-Monitor Produktionsstraße – Einrichtung auf Raspberry Pi OS Lite (64 Bit, Bookworm)
# Aufruf auf dem Pi:
#   curl -fsSL https://raw.githubusercontent.com/lolliversum/ha-addons/main/kamera-monitor/einrichten.sh | sudo bash
# Danach Kameras eintragen:  sudo nano /etc/kamera-monitor/kameras.conf   und   sudo reboot
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Bitte mit sudo starten."; exit 1; }

NUTZER="${SUDO_USER:-}"
if [ -z "$NUTZER" ] || [ "$NUTZER" = "root" ]; then
  NUTZER="$(getent passwd 1000 | cut -d: -f1)"
fi
[ -n "$NUTZER" ] || { echo "Kein normaler Benutzer gefunden."; exit 1; }
HEIM="$(getent passwd "$NUTZER" | cut -d: -f6)"
QUELLE="https://raw.githubusercontent.com/lolliversum/ha-addons/main/kamera-monitor"

echo "== Pakete installieren (dauert ein paar Minuten) =="
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  xserver-xorg xinit x11-xserver-utils unclutter mpv cec-utils curl >/dev/null

echo "== Programme ablegen =="
mkdir -p /etc/kamera-monitor
curl -fsSL "$QUELLE/kamera-monitor.sh" -o /usr/local/bin/kamera-monitor
chmod 755 /usr/local/bin/kamera-monitor
if [ ! -f /etc/kamera-monitor/kameras.conf ]; then
  curl -fsSL "$QUELLE/kameras.conf.beispiel" -o /etc/kamera-monitor/kameras.conf
fi
chown root:"$NUTZER" /etc/kamera-monitor/kameras.conf
chmod 640 /etc/kamera-monitor/kameras.conf
usermod -aG video,render,tty,input "$NUTZER" || true

echo "== Automatisch anmelden auf tty1 =="
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $NUTZER --noclear %I \$TERM
EOF

echo "== Grafik beim Anmelden starten =="
PROFIL="$HEIM/.bash_profile"
touch "$PROFIL"
if ! grep -q "kamera-monitor" "$PROFIL"; then
  cat >> "$PROFIL" <<'EOF'
# kamera-monitor: auf tty1 automatisch starten
if [ -z "${DISPLAY:-}" ] && [ "$(tty)" = "/dev/tty1" ]; then
  exec startx /usr/local/bin/kamera-monitor -- -nocursor >/tmp/kamera-monitor-x.log 2>&1
fi
EOF
fi
chown "$NUTZER":"$NUTZER" "$PROFIL"

echo "== Nachts um 4 Uhr neu starten (falls ein Bild hängen bleibt) =="
echo "0 4 * * * root /sbin/reboot" > /etc/cron.d/kamera-monitor
chmod 644 /etc/cron.d/kamera-monitor

echo "== Bildschirm nie abschalten =="
if [ -f /boot/firmware/cmdline.txt ] && ! grep -q "consoleblank=0" /boot/firmware/cmdline.txt; then
  sed -i 's/$/ consoleblank=0/' /boot/firmware/cmdline.txt
fi

systemctl set-default multi-user.target >/dev/null
systemctl daemon-reload

echo
echo "FERTIG. Jetzt Kameras eintragen:"
echo "  sudo nano /etc/kamera-monitor/kameras.conf"
echo "dann:  sudo reboot"
