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

## Ohne SSH: alles über die SD-Karte
Nach dem Schreiben mit dem Imager die SD-Karte am PC lassen, Laufwerk **bootfs** öffnen:
1. Datei `kameras.conf` dort anlegen (gleicher Aufbau wie die Vorlage). Wird bevorzugt gelesen; ändern = Karte in den PC, Datei bearbeiten, zurück.
2. Datei `user-data` mit Editor öffnen, ganz unten anfügen (gibt es schon `runcmd:`, nur die Zeile mit `- ` darunter setzen):
```
runcmd:
  - [ sh, -c, "curl -fsSL https://raw.githubusercontent.com/lolliversum/ha-addons/main/kamera-monitor/einrichten.sh | bash && reboot" ]
```
Erster Start mit LAN-Kabel, dauert 5–10 Min., dann startet er neu und zeigt die Kameras.
