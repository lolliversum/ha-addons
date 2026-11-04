# Kamera-Monitor Produktionsstraße

Raspberry Pi am Fernseher zeigt 1–6 Kameras als Raster, live mit < 1 s Verzögerung.
Strom an → Pi startet, schaltet TV per HDMI-CEC ein, Bild läuft. Niemand muss tippen.

**Kameras:** liegen in Home Assistant Gut in der App **go2rtc** (`/config/go2rtc.yaml`, Vorlage `go2rtc.yaml.beispiel`).
**Auswahl:** HA-Helfer **Kamera-Monitor Produktion** (kommt per Lolliversum Sync), z. B. `presse, halle, tor`.
Reihenfolge = Platz im Raster. Der Pi prüft alle 30 s und baut das Raster neu. Von überall über die HA-App änderbar.
Auch direkt möglich: `Hof=rtsp://…` als Eintrag. Ist HA weg, läuft die letzte Liste weiter.

## Einrichten (ohne SSH)
1. Raspberry Pi Imager: **Raspberry Pi OS Lite (64-bit)**, Zahnrad: Hostname `kamera-monitor`, Benutzer `monitor` + Passwort.
2. SD-Karte am PC lassen, Laufwerk **bootfs**:
   - `kamera-monitor.ini` anlegen (Vorlage `kamera-monitor.ini.beispiel`, Token eintragen)
   - in `user-data` ganz unten anfügen (gibt es `runcmd:` schon, nur die Zeile mit `- [` darunter):
```
runcmd:
  - [ sh, -c, "curl -fsSL https://raw.githubusercontent.com/lolliversum/ha-addons/main/kamera-monitor/einrichten.sh | bash && reboot" ]
```
3. Karte in den Pi, LAN-Kabel, Strom. Nach 5–10 Min. Neustart, dann Bild.

Ohne HA geht weiter: `kameras.conf` mit Zeilen `Name | rtsp://…` statt der ini.
