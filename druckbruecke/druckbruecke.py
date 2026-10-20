#!/usr/bin/env python3
"""Druckbrücke für einen Standort (Hof: Docker-Container auf der Synology; Laden: Pi o. ä.).

Holt Druckaufträge AUSGEHEND vom Portal (kein Portforwarding, keine offenen Ports) und gibt sie an die
Drucker im lokalen Netz. Das Portal steht in Falkenstein, die Drucker im Hof-WLAN — die Brücke ist das
einzige Stück, das beide Seiten sieht.

Drucker-Angabe im Auftrag:
  "192.168.3.11:9100"  → rohe Daten per TCP an genau diese Adresse (so kommt es aus der Versand-/Etikettenlogik,
                          die ihr Ziel aus dem Druckerverzeichnis nimmt). Nur Adressen in DRUCK_NETZE.
  "etiketten"          → Name aus der Konfiguration (drucker), art "9100" oder "lp" (CUPS, nur am Pi).
Auftrag mit "wecken": true → vorher "~HS" an den Zebra (weckt den ZQ521 am Gürtel, siehe Station ids_etikett).

Konfiguration per Umgebung (Docker) — oder druckbruecke.json neben dem Skript (alte Form, Pi):
  DRUCK_SERVER   https://intranet.lolliversum.de
  DRUCK_STANDORT hof
  DRUCK_TOKEN    Schlüssel von /druck („Schlüssel erzeugen“, nur Inhaber)
  DRUCK_NETZE    erlaubte Drucker-Netze, Standard 192.168.0.0/16,10.0.0.0/8,172.16.0.0/12
  DRUCK_DRUCKER  optional JSON {"etiketten": {"art": "9100", "host": "192.168.3.11"}}
Start: python3 druckbruecke.py            (Dauerschleife)
       python3 druckbruecke.py --einmal   (abarbeiten, dann Ende)
       python3 druckbruecke.py --pruefen  (Server + Schlüssel testen, nichts drucken)
"""
import base64, ipaddress, json, os, re, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

VERSION = "2026-10-17"


def _konf():
    k = {}
    datei = Path(__file__).with_name("druckbruecke.json")
    if datei.exists():
        k = json.loads(datei.read_text())
    e = os.environ
    k["server"] = e.get("DRUCK_SERVER") or k.get("server") or "https://intranet.lolliversum.de"
    k["standort"] = e.get("DRUCK_STANDORT") or k.get("standort") or "hof"
    k["token"] = e.get("DRUCK_TOKEN") or k.get("token") or ""
    k["netze"] = [ipaddress.ip_network(n.strip()) for n in
                  (e.get("DRUCK_NETZE") or k.get("netze") or "192.168.0.0/16,10.0.0.0/8,172.16.0.0/12").split(",") if n.strip()]
    if e.get("DRUCK_DRUCKER"):
        k["drucker"] = json.loads(e["DRUCK_DRUCKER"])
    k.setdefault("drucker", {})
    k["takt"] = float(e.get("DRUCK_TAKT") or k.get("takt_sekunden") or 2)
    return k


KONF = _konf()
_ZIEL = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})$")


def _anfrage(methode, pfad, daten=None):
    req = urllib.request.Request(KONF["server"].rstrip("/") + pfad, method=methode,
                                 data=json.dumps(daten).encode() if daten is not None else None,
                                 headers={"Authorization": f"Bearer {KONF['token']}", "Content-Type": "application/json",
                                          "X-Bruecke-Version": VERSION,
                                          "X-Bruecke-Info": socket.gethostname()[:60]})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, (r.read() or b"")


def ziel(drucker):
    """(art, host, port | queue) für die Drucker-Angabe eines Auftrags."""
    m = _ZIEL.match(drucker or "")
    if m:
        ip = ipaddress.ip_address(m.group(1))
        if not any(ip in n for n in KONF["netze"]):
            raise RuntimeError(f"{ip} liegt nicht in den erlaubten Netzen (DRUCK_NETZE)")
        return {"art": "9100", "host": str(ip), "port": int(m.group(2))}
    z = KONF["drucker"].get(drucker) or KONF["drucker"].get("standard")
    if not z:
        raise RuntimeError(f"Drucker '{drucker}' ist an der Brücke nicht eingetragen")
    return z


def _roh(host, port, inhalt, wecken=False):
    if wecken:  # ~HS weckt einen schlafenden ZQ521; Antwort abwarten, sonst geht der erste Druck ins Leere
        try:
            with socket.create_connection((host, port), timeout=6) as s:
                s.sendall(b"~HS"); s.settimeout(2)
                try:
                    s.recv(512)
                except OSError:
                    pass
        except OSError:
            pass
    with socket.create_connection((host, port), timeout=15) as s:
        s.sendall(inhalt)


def drucken(auftrag):
    z = ziel(auftrag["drucker"])
    inhalt = base64.b64decode(auftrag["daten"])
    for i in range(int(auftrag.get("kopien") or 1)):
        if z["art"] == "9100":
            _roh(z["host"], int(z.get("port", 9100)), inhalt, wecken=bool(auftrag.get("wecken")) and i == 0)
        elif z["art"] == "lp":
            with tempfile.NamedTemporaryFile(suffix="." + auftrag["format"]) as f:
                f.write(inhalt); f.flush()
                subprocess.run(["lp", "-d", z["queue"], f.name], check=True, capture_output=True, timeout=60)
        else:
            raise RuntimeError(f"unbekannte Druckerart {z['art']}")


def runde():
    try:
        status, roh = _anfrage("GET", f"/druck/api/{KONF['standort']}/naechster")
    except urllib.error.HTTPError as e:
        print(time.strftime("%H:%M:%S"), "Server lehnt ab:", e.code, "(Schlüssel prüfen)" if e.code == 401 else "", flush=True)
        time.sleep(30)
        return False
    except (urllib.error.URLError, OSError) as e:
        print(time.strftime("%H:%M:%S"), "Server nicht erreichbar:", e, flush=True)
        return False
    if status == 204:
        return False
    auftrag = json.loads(roh)
    try:
        drucken(auftrag)
        ok, meldung = True, ""
    except Exception as e:  # Druckerfehler zurückmelden, nicht abstürzen
        ok, meldung = False, str(e)
    print(time.strftime("%H:%M:%S"), f"#{auftrag['id']} {auftrag.get('titel', '')} → {auftrag['drucker']}:",
          "ok" if ok else meldung, flush=True)
    try:
        _anfrage("POST", f"/druck/api/{KONF['standort']}/fertig/{auftrag['id']}", {"ok": ok, "meldung": meldung})
    except (urllib.error.URLError, OSError):
        pass  # Server gibt den Auftrag nach 5 Min. erneut frei
    return True


def main(argv):
    if not KONF["token"]:
        sys.exit("DRUCK_TOKEN fehlt (auf /druck erzeugen)")
    print("Druckbrücke", VERSION, "Standort", KONF["standort"], "→", KONF["server"], flush=True)
    if "--pruefen" in argv:
        try:
            status, _ = _anfrage("GET", f"/druck/api/{KONF['standort']}/naechster")
            print("Server ok, Schlüssel gültig, Status", status)
            return 0
        except urllib.error.HTTPError as e:
            print("Server lehnt ab:", e.code); return 1
    if "--einmal" in argv:
        while runde():
            pass
        return 0
    while True:
        if not runde():
            time.sleep(KONF["takt"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
