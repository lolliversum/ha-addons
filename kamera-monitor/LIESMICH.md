# Kamera-Monitor Produktionsstraße

Raspberry Pi am Fernseher zeigt 1–6 Kameras als Raster, live (RTSP, mpv, geringe Verzögerung).
Strom an → Pi startet, schaltet TV per HDMI-CEC ein, Bild läuft. Niemand muss tippen.

## Einrichten
1. Raspberry Pi Imager: **Raspberry Pi OS Lite (64-bit)**, Einstellungen: Hostname `kamera-monitor`, Benutzer `monitor` + Passwort, LAN/WLAN, **SSH an**.
2. Pi ans LAN, per SSH verbinden: `ssh monitor@kamera-monitor.local`
3. `curl -fsSL https://raw.githubusercontent.com/lolliversum/ha-addons/main/kamera-monitor/einrichten.sh | sudo bash`
4. Kameras eintragen: `sudo nano /etc/kamera-monitor/kameras.conf` (Strg+O, Enter, Strg+X)
5. `sudo reboot`

Kameras ändern: Schritt 4 + Neustart. Täglich 4 Uhr Neustart automatisch.
Zugangsdaten stehen nur auf dem Pi, nie im Repo.
