# KI-Chat-Übergabe – Nebenkostenabrechnung

Stand der Übergabe: 11.11.2026. Diese Datei dient als Einstieg für einen neuen KI-Chat. Sie dokumentiert bekannte Fakten und offene Prüfungen; sie ist **kein** Nachweis für einen erfolgreichen aktuellen Produktivtest.

## Einstieg für den neuen Chat

Arbeite am GitHub-Repository `Markus4771/Nebenkosten` (Standardbranch `main`). Lies zuerst diese Datei, `README.md`, `INSTALL.md`, `CHANGELOG.md`, `PROJECT.md`, `version.txt`, `packaging/debian/`, `scripts/build_deb.sh` und die GitHub-Actions-Workflows. Prüfe den tatsächlichen Code- und Release-Status, bevor du Änderungen oder Installationsbefehle empfiehlst. Führe Änderungen schrittweise, testbar und mit Datensicherung durch. Nenne ausdrücklich, was verifiziert ist und was noch getestet werden muss.

## Projekt und Funktionsumfang

Webanwendung für Vermieter zur Nebenkostenabrechnung und Prüfung erhaltener Hausverwaltungsabrechnungen. Laut README auf `main` umfasst sie:
- Mehrbenutzerbetrieb und Rollen, Objekte, Wohnungen, Mieter
- Nebenkostenabrechnungen mit Verteilerschlüsseln und PDF
- Mietzahlungen, Soll/Ist und CSV-Import
- Steuerberaterübersicht, CSV und Anlage-V-Vorbereitung
- Zählerstände, Verbrauchs- und Mehrjahresauswertung
- Dokumente, lokale PDF-Textauslesung und Tesseract-OCR
- optionale KI-Anbieter (Ollama, OpenAI, Anthropic, OpenRouter, Gemini) und Paperless-ngx
- Backup/Wiederherstellung einschließlich SMB/NAS, SMTP und Updateverwaltung

Die Aufzählung stammt aus der Projektdokumentation; einzelne Funktionen müssen bei Bedarf praktisch geprüft werden.

## Bekannter Stand im GitHub

- Repository: https://github.com/Markus4771/Nebenkosten
- Standardbranch: `main`
- `version.txt` auf `main` meldete bei Erstellung dieser Übergabe **2.10.0**.
- Die README-Überschrift bezeichnete noch **2.9.1**: Dokumentation und Versionsangaben daher auf Konsistenz prüfen.
- Historisch wurde 2.9.1 rekonstruiert und für `main` vorbereitet. Der PR zur Vorbereitung meldete 50 erfolgreiche Tests, Debian-Paketbau, Healthcheck, Login und Dashboard; dies belegt **nicht** automatisch die Qualität von 2.10.0.
- In späteren Commits wurden 2.10.0-Versionsangaben sowie persönliche Samba-Scanfreigaben, Navigations-/Routeneinbindung und Debian-Installationsunterstützung ergänzt.
- Ob 2.10.0 vollständig getestet, als GitHub-Release veröffentlicht und produktiv ausgerollt wurde, muss neu geprüft werden.

## Zuletzt vom Nutzer bestätigter Serverstand

Host: `Debian-Nebenk` (Debian; genaue Version bei Bedarf prüfen).
- `dpkg -l` zeigte: `nebenkostenabrechnung 2.9.1`, installiert.
- `nebenkostenabrechnung.service`: aktiv und laufend, Uvicorn über `/opt/nebenkostenabrechnung/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080`.
- Weboberfläche: `http://SERVER-IP:8080`; Login funktionierte nach anfänglichen 400-Antworten.
- Datenbank: `/var/lib/nebenkostenabrechnung/nebenkosten.db` (damals etwa 96 KB).
- Weitere Anwendungsdaten: `/var/lib/nebenkostenabrechnung/{backups,csv-previews,documents,secrets,updates,uploads}`.
- Konfiguration: `/etc/default/nebenkostenabrechnung` (root-only, **keine Passwörter im Chat oder Repository veröffentlichen**).
- Quellcheckout: `~/Nebenkosten`; ursprünglich Branch `codex/reconstruct-2.9.1`, später `version.txt` mit 2.9.1. Ein unversioniertes Unterverzeichnis `Nebenkosten/` wurde angezeigt. Ob inzwischen auf `main` gewechselt wurde, ist nicht bestätigt.
- Keine Bestätigung, dass 2.10.0 auf dem Server installiert wurde.

## Sichere Diagnose vor einem Update

Auf dem Zielserver zuerst ohne Änderungen prüfen:

```bash
dpkg-query -W -f='${Package} ${Version}\n' nebenkostenabrechnung
systemctl status nebenkostenabrechnung --no-pager -l
cd ~/Nebenkosten && git branch --show-current && git status --short && git fetch origin && git log -1 --oneline origin/main
```

Vor einem Update Datenbank **konsistent** sichern (bei laufendem SQLite nicht einfach blind kopieren; SQLite-Backup-API oder einen geplanten Dienststopp nutzen), außerdem Dokumente/Uploads und Konfiguration sichern. Sicherung und Wiederherstellbarkeit prüfen. Die Konfigurationsdatei enthält Zugangsdaten und darf nicht ins Git gelangen.

Das Debian-Paket wird laut Projektdokumentation über `./scripts/build_deb.sh` erstellt und anschließend mit `sudo apt install ./dist/<paketname>.deb` installiert. Den **tatsächlichen** Paketnamen und die Version erst nach dem Build prüfen. Für GitHub-Release-Updates muss ein entsprechendes veröffentlichtes Release mit Paket-Asset vorhanden sein. Nicht allein anhand von `version.txt` annehmen, dass ein Release bereitsteht.

## Nächste sinnvolle Aufgaben

1. `main`, offene PRs/Issues, GitHub Actions, Releases, Versionsdateien und Paketmetadaten vergleichen.
2. Automatische Tests ausführen; Paketbau, Installation und Update von 2.9.1 auf 2.10.0 in einer Testumgebung prüfen.
3. Persönliche Scan-Freigaben/Samba besonders auf Berechtigungen, Trennung zwischen Benutzern und sichere Installation prüfen.
4. End-to-End-Test: Anmeldung, Objekte/Wohnungen/Mieter, Abrechnung und PDF, Zahlungen/CSV, Zähler, OCR, Backup/Wiederherstellung.
5. Dokumentation, Changelog und gegebenenfalls Backlog aktualisieren; erst nach erfolgreicher Prüfung Release/Produktivupdate empfehlen.

## Arbeitsregeln für die KI

- Niemals produktive Datenbank, Dokumente oder `secrets` durch `git reset --hard`, Löschbefehle oder eine Neuinstallation gefährden.
- Git-Arbeitsverzeichnis (`~/Nebenkosten`) und installierte Anwendung (`/opt/nebenkostenabrechnung`) unterscheiden.
- Vor GitHub-Schreibaktionen Änderungen und Tests nachvollziehbar dokumentieren; keine Geheimnisse committen.
- Ungeprüfte Funktionen und vermutete Versionsstände als offen kennzeichnen.
