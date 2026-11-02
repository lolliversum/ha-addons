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
import base64, ipaddress, json, os, re, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
from pathlib import Path

VERSION = "2026-11-02"   # + Selbst-Update (alle 6 h, SHA-256 vom Portal)
_VERSION_01_11 = "2026-11-01"   # + FRITZ!Box: Telefonliste (Namen + interne Nummern) alle 6 h ans Portal
_VERSION_30_10 = "2026-10-30"   # + FRITZ!Box: Wählhilfe (TR-064) und Anrufmonitor (Port 1012), nur mit FRITZ_HOST
_VERSION_ALT = "2026-10-23"   # + Rückkanal: Auftrag mit "antwort": true liest die Antwort des Druckers (Etikettenzähler)


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
    k["fritz_host"] = e.get("FRITZ_HOST") or k.get("fritz_host") or ""            # z. B. 192.168.178.1 (leer = kein Telefon)
    k["fritz_benutzer"] = e.get("FRITZ_BENUTZER") or k.get("fritz_benutzer") or ""
    k["fritz_passwort"] = e.get("FRITZ_PASSWORT") or k.get("fritz_passwort") or ""
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


def abfragen(host, port, inhalt, warten=4.0):
    """Befehl schicken und die Antwort des Druckers lesen (z. B. ! U1 getvar "odometer.total_label_count")."""
    with socket.create_connection((host, port), timeout=6) as s:
        s.sendall(inhalt)
        s.settimeout(warten)
        teile = []
        try:
            while sum(len(t) for t in teile) < 4096:
                t = s.recv(1024)
                if not t:
                    break
                teile.append(t)
                s.settimeout(0.5)   # nach dem ersten Stück nur noch kurz auf den Rest warten
        except OSError:
            pass
    return b"".join(teile)


def drucken(auftrag):
    z = ziel(auftrag["drucker"])
    inhalt = base64.b64decode(auftrag["daten"])
    if auftrag.get("antwort"):
        if z["art"] != "9100":
            raise RuntimeError("Abfragen gehen nur an Netzwerkdrucker (Port 9100)")
        return abfragen(z["host"], int(z.get("port", 9100)), inhalt)
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
    antwort = None
    try:
        antwort = drucken(auftrag)
        ok, meldung = True, ""
    except Exception as e:  # Druckerfehler zurückmelden, nicht abstürzen
        ok, meldung = False, str(e)
    print(time.strftime("%H:%M:%S"), f"#{auftrag['id']} {auftrag.get('titel', '')} → {auftrag['drucker']}:",
          "ok" if ok else meldung, flush=True)
    try:
        rueck = {"ok": ok, "meldung": meldung}
        if auftrag.get("antwort") and antwort is not None:
            rueck["antwort"] = base64.b64encode(antwort).decode()
        _anfrage("POST", f"/druck/api/{KONF['standort']}/fertig/{auftrag['id']}", rueck)
    except (urllib.error.URLError, OSError):
        pass  # Server gibt den Auftrag nach 5 Min. erneut frei
    return True


# ---------------------------------------------------------------- Selbst-Update (N0, 02.11.2026)
# Beim Start und alle 6 h: /version fragen; ist das Portal neuer, Datei vom Portal laden, SHA-256 gegen die Antwort prüfen,
# Syntax + VERSION prüfen, die eigene Datei ersetzen (alte als .alt) und neu starten. Nur vom Portal, nie von anderswo.
UPDATE_ABSTAND = 6 * 3600


def update_pruefen(datei=None):
    """True = Datei wurde ersetzt (Aufrufer startet neu). Jeder Fehler -> False, die Brücke läuft einfach weiter."""
    import hashlib
    datei = Path(datei or __file__)
    try:
        _, roh = _anfrage("GET", f"/druck/api/{KONF['standort']}/version")
        info = json.loads(roh)
        neu = str(info.get("version", ""))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", neu) or neu <= VERSION:
            return False
        _, code = _anfrage("GET", f"/druck/api/{KONF['standort']}/bruecke.py")
        if hashlib.sha256(code).hexdigest() != str(info.get("sha256", "")).lower():
            print("Update verworfen: SHA-256 stimmt nicht", flush=True)
            return False
        if ('VERSION = "%s"' % neu).encode() not in code:
            print("Update verworfen: Version in der Datei passt nicht", flush=True)
            return False
        compile(code, "druckbruecke.py", "exec")
        tmp = datei.with_name(datei.name + ".neu")
        tmp.write_bytes(code)
        if datei.exists():
            datei.with_name(datei.name + ".alt").write_bytes(datei.read_bytes())
        os.replace(tmp, datei)
        print("Update", VERSION, "->", neu, "eingespielt, starte neu", flush=True)
        return True
    except Exception as e:  # noqa: BLE001
        print("Update-Prüfung fehlgeschlagen:", str(e)[:120], flush=True)
        return False


def neu_starten():
    os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve())] + sys.argv[1:])


# ---------------------------------------------------------------- FRITZ!Box (30.10.2026): Telefon im Portal
# Wählen: Portal-Auftrag {nummer, telefon} → TR-064 X_VoIP: erst das Wählhilfe-Telefon setzen (X_AVM-DE_DialSetConfig),
# dann X_AVM-DE_DialNumber. Die FRITZ!Box klingelt das Telefon an, nach dem Abheben wird gewählt.
# Voraussetzungen in der FRITZ!Box: Heimnetz → Netzwerk → Netzwerkeinstellungen „Zugriff für Anwendungen zulassen“ (TR-064),
# Telefonie → Anrufe → Wählhilfe „Wählhilfe verwenden“, ein FRITZ!Box-Benutzer mit Recht „Sprachnachrichten, Faxnachrichten,
# FRITZ!App Fon und Anrufliste“; Anrufmonitor einmalig mit #96*5* an einem Telefon einschalten.
_TR064 = "urn:dslforum-org:service:X_VoIP:1"


def _tr064(aktion, argumente, dienst=None, pfad="/upnp/control/x_voip"):
    import xml.sax.saxutils as su
    dienst = dienst or _TR064
    rumpf = "".join(f"<{k}>{su.escape(str(v))}</{k}>" for k, v in argumente.items())
    xml = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" '
           'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
           f'<u:{aktion} xmlns:u="{dienst}">{rumpf}</u:{aktion}></s:Body></s:Envelope>').encode()
    url = f"http://{KONF['fritz_host']}:49000{pfad}"
    pw = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    pw.add_password(None, url, KONF["fritz_benutzer"], KONF["fritz_passwort"])
    oeffner = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(pw))
    req = urllib.request.Request(url, data=xml, headers={"Content-Type": 'text/xml; charset="utf-8"',
                                                         "SOAPAction": f"{dienst}#{aktion}"})
    with oeffner.open(req, timeout=10) as r:
        return r.read()


def fritz_waehlen(nummer, telefon=""):
    nummer = re.sub(r"[^0-9*#]", "", str(nummer))
    if not nummer:
        raise ValueError("keine Nummer")
    vorher = ""
    if telefon:
        # 02.11.2026: TAPICall auf den PCs nutzt dieselbe Wählhilfe – vorher eingestelltes Telefon merken und danach
        # zurückstellen, damit deren nächster Anruf nicht beim Telefon des Portal-Nutzers klingelt.
        try:
            vorher = _feld(_tr064("X_AVM-DE_DialGetConfig", {}), "NewX_AVM-DE_PhoneName")
        except Exception:  # noqa
            vorher = ""
        _tr064("X_AVM-DE_DialSetConfig", {"NewX_AVM-DE_PhoneName": telefon})
    _tr064("X_AVM-DE_DialNumber", {"NewX_AVM-DE_PhoneNumber": nummer})
    if vorher and vorher != telefon:
        def _zurueck():
            time.sleep(int(os.environ.get("FRITZ_ZURUECK_SEK", "8")))
            try:
                _tr064("X_AVM-DE_DialSetConfig", {"NewX_AVM-DE_PhoneName": vorher})
            except Exception as e:  # noqa
                print("Wählhilfe zurückstellen fehlgeschlagen:", e, flush=True)
        threading.Thread(target=_zurueck, daemon=True).start()


def _feld(xml, name):
    m = re.search(rb"<" + re.escape(name.encode()) + rb">([^<]*)</", xml)
    return m.group(1).decode("utf-8", "replace").strip() if m else ""


def fritz_telefone():
    """01.11.2026: alle Telefone der FRITZ!Box mit Namen (so wie die Wählhilfe sie braucht) und – soweit ableitbar – der
    internen Nummer, die der Anrufmonitor meldet (FON1–3 → 0–2, DECT 1–6 → 10–15, IP-Telefone → 20…)."""
    dect = {}
    try:
        ids = _feld(_tr064("GetDECTHandsetList", {}, "urn:dslforum-org:service:X_AVM-DE_OnTel:1", "/upnp/control/x_contact"), "NewDectIDList")
        for i in [x for x in ids.split(",") if x.strip().isdigit()]:
            name = _feld(_tr064("GetDECTHandsetInfo", {"NewDectID": i}, "urn:dslforum-org:service:X_AVM-DE_OnTel:1", "/upnp/control/x_contact"), "NewHandsetName")
            if name:
                dect[name] = str(9 + int(i))
    except Exception:  # noqa — ohne DECT-Liste nur die Namen
        pass
    aus, ip = [], 20
    for idx in range(1, 41):
        try:
            name = _feld(_tr064("X_AVM-DE_GetPhonePort", {"NewIndex": idx}), "NewX_AVM-DE_PhoneName")
        except Exception:  # noqa — Ende der Liste
            break
        if not name:
            continue
        intern = ""
        m = re.match(r"FON(\d)", name)
        if name.startswith("DECT: "):
            intern = dect.get(name[6:].strip(), "")
        elif m:
            intern = str(int(m.group(1)) - 1)
        elif re.match(r"(LAN|WLAN|IP|ISDN)", name, re.I):
            intern, ip = str(ip), ip + 1
        aus.append({"name": name, "intern": intern})
    return aus


def telefone_melden():
    try:
        liste = fritz_telefone()
        if liste:
            _anfrage("POST", f"/telefon/api/{KONF['standort']}/telefone", {"telefone": liste, "version": VERSION})
            print(time.strftime("%H:%M:%S"), f"Telefonliste gemeldet: {len(liste)} Telefone", flush=True)
    except Exception as e:  # noqa
        print(time.strftime("%H:%M:%S"), "Telefonliste:", str(e)[:200], flush=True)


def telefon_runde():
    try:
        status, roh = _anfrage("GET", f"/telefon/api/{KONF['standort']}/naechster")
    except (urllib.error.URLError, OSError):
        return False
    if status == 204:
        return False
    a = json.loads(roh)
    try:
        fritz_waehlen(a["nummer"], a.get("telefon", ""))
        ok, meldung = True, ""
    except urllib.error.HTTPError as e:
        ok, meldung = False, f"FRITZ!Box lehnt ab ({e.code}) – TR-064, Wählhilfe und Benutzer prüfen"
    except Exception as e:  # noqa
        ok, meldung = False, str(e)[:200]
    print(time.strftime("%H:%M:%S"), f"Telefon #{a['id']} → {a.get('telefon', '')}:", "ok" if ok else meldung, flush=True)
    try:
        _anfrage("POST", f"/telefon/api/{KONF['standort']}/fertig/{a['id']}", {"ok": ok, "meldung": meldung})
    except (urllib.error.URLError, OSError):
        pass
    return True


def monitor_zeile(z):
    """Anrufmonitor-Zeile → Meldung ans Portal oder None. RING = klingelt, CONNECT (eingehend) = angenommen."""
    t = z.strip().split(";")
    if len(t) >= 5 and t[1] == "RING":
        return {"art": "klingelt", "nummer": t[3], "nebenstelle": "", "verbindung": t[2]}
    if len(t) >= 5 and t[1] == "CONNECT":
        return {"art": "angenommen", "nummer": t[4], "nebenstelle": t[3], "verbindung": t[2]}
    if len(t) >= 4 and t[1] == "DISCONNECT":   # 02.11.2026: Ende mit Dauer in Sekunden (0 = nie verbunden)
        return {"art": "ende", "dauer": int(t[3]) if t[3].strip().isdigit() else 0, "verbindung": t[2]}
    return None


def monitor_folge(offen, m):
    """02.11.2026: Monitor-Zeile → Meldung ans Portal (oder None). offen = {verbindung: {nummer, nebenstelle, angenommen}}.
    Nur eingehende Gespräche. Ende: angenommen → „beendet“ mit Dauer, sonst „verpasst“."""
    v = m["verbindung"]
    if m["art"] == "klingelt":
        offen[v] = {"nummer": m["nummer"], "nebenstelle": "", "angenommen": False}
        return m
    if v not in offen:   # ausgehendes Gespräch: nicht melden
        return None
    if m["art"] == "angenommen":
        offen[v].update(angenommen=True, nebenstelle=m["nebenstelle"])
        return m
    a = offen.pop(v)
    if a["angenommen"]:
        return {"art": "beendet", "nummer": a["nummer"], "nebenstelle": a["nebenstelle"], "dauer": m["dauer"], "verbindung": v}
    return {"art": "verpasst", "nummer": a["nummer"], "nebenstelle": "", "verbindung": v}


def anrufmonitor():
    offen = {}
    while True:
        try:
            with socket.create_connection((KONF["fritz_host"], 1012), timeout=30) as s:
                s.settimeout(None)
                puffer = b""
                print(time.strftime("%H:%M:%S"), "Anrufmonitor verbunden", flush=True)
                while True:
                    teil = s.recv(1024)
                    if not teil:
                        break
                    puffer += teil
                    while b"\n" in puffer:
                        zeile, puffer = puffer.split(b"\n", 1)
                        m = monitor_zeile(zeile.decode("utf-8", "replace"))
                        m = monitor_folge(offen, m) if m else None
                        if not m:
                            continue
                        try:
                            _anfrage("POST", f"/telefon/api/{KONF['standort']}/anruf", m)
                        except (urllib.error.URLError, OSError):
                            pass
        except OSError as e:
            print(time.strftime("%H:%M:%S"), "Anrufmonitor:", e, "(mit #96*5* einschalten?)", flush=True)
        time.sleep(20)


def telefon_starten():
    if not KONF.get("fritz_host"):
        return
    import threading
    threading.Thread(target=anrufmonitor, daemon=True, name="anrufmonitor").start()

    def _waehlen():
        letzte = 0
        while True:
            if time.time() - letzte > 6 * 3600:   # Telefonliste beim Start und alle 6 h
                letzte = time.time()
                telefone_melden()
            if not telefon_runde():
                time.sleep(1.5)
    threading.Thread(target=_waehlen, daemon=True, name="waehlhilfe").start()
    print("Telefon: FRITZ!Box", KONF["fritz_host"], "(Wählhilfe + Anrufmonitor)", flush=True)


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
    if update_pruefen():
        neu_starten()
    letzt = time.time()
    telefon_starten()
    while True:
        if time.time() - letzt > UPDATE_ABSTAND:
            letzt = time.time()
            if update_pruefen():
                neu_starten()
        if not runde():
            time.sleep(KONF["takt"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
