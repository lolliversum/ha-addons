# Lolliversum Druckbrücke

1. Portal → **/druck** → beim Standort (hof / laden / leon) **Schlüssel erzeugen** (nur Inhaber), Wert kopieren.
2. Hier unter **Konfiguration**: Standort wählen, Schlüssel einfügen, `netze` = Netz der Drucker (z. B. `192.168.178.0/24`).
3. Speichern → **Starten**, „Beim Booten starten“ an. Im Protokoll muss die Prüfung „ok“ melden.
4. Portal /druck: der Standort zeigt **● online**.

Die Brücke fragt nur ausgehend beim Portal nach Aufträgen. Kein Port wird geöffnet.

## Telefon über die FRITZ!Box (nur Laden, ab 2026.11.02.1)
Aus dem Portal wählen (📞 in der Kundenakte) und eingehende Anrufe melden.
1. FRITZ!Box: Heimnetz → Netzwerk → Netzwerkeinstellungen → „Zugriff für Anwendungen zulassen“ an.
2. FRITZ!Box: System → FRITZ!Box-Benutzer → Benutzer `portal`, Recht „Sprachnachrichten, Faxnachrichten, FRITZ!App Fon und Anrufliste“.
3. FRITZ!Box: Telefonie → Anrufe → Wählhilfe → „Wählhilfe verwenden“ an.
4. An einem Telefon `#96*5*` wählen (Anrufmonitor an).
5. Hier unter Konfiguration `fritz_host` (z. B. 192.168.178.1), `fritz_benutzer`, `fritz_passwort` eintragen, speichern, Add-on neu starten.
Die Brücke meldet die Telefone dann selbst ans Portal; Zuordnung unter /telefon/zuordnung.
