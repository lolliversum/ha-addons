# Lolliversum Sync

Holt den Ordner dieses Standorts (gut / leon / kiel) aus dem privaten Repo `lolliversum/smarthome` nach
`/config/lolliversum/` und lädt Home Assistant neu. Die bestehende Konfiguration bleibt unberührt.

Einmalig in `configuration.yaml` ergänzen:

```yaml
homeassistant:
  packages: !include_dir_named lolliversum/packages
```

GitHub-Schlüssel: fein eingegrenzter Token, **nur** Repo `lolliversum/smarthome`, Recht „Contents: Read“.
