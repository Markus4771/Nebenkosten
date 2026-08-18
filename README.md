# Nebenkostenabrechnung 2.1.0

Webanwendung für Vermieter und Mieter zur Erstellung, Verwaltung und KI-gestützten Prüfung von Nebenkostenabrechnungen.

## Aktueller Stand 2.1.0

- Mehrbenutzerbetrieb mit getrennten Datenbereichen
- Objekte, Wohnungen und mehrere Mieter pro Benutzer
- Nebenkostenabrechnungen mit Verteilerschlüsseln und PDF-Ausgabe
- OCR und KI-Auswertung erhaltener Hausverwaltungsabrechnungen
- KI-Provider: Ollama, OpenAI, Anthropic Claude, OpenRouter und Google Gemini
- Vorjahres- und Mehrjahresvergleich
- Zähler- und Verbrauchsverwaltung
- Vergleich erkannter Verbräuche mit eigenen Zählerständen
- Dokumentenverwaltung
- Backup/Wiederherstellung und SMB/NAS-Backup
- SMTP-Versand
- Debian-Paket und Web-Update-Vorbereitung
- Steuerberater-Bereich mit Jahresübersicht, CSV und Anlage-V-Vorbereitung
- Kaltmiete je Mieter
- Mietzahlungserfassung mit Soll-/Ist-Vergleich
- Zahlungseingänge in den Steuerbereich übernehmen
- automatische Vorschläge für Steuerkategorien

## Installation auf Debian

```bash
sudo apt install ./nebenkostenabrechnung_2.1.0_all.deb
sudo systemctl restart nebenkostenabrechnung
sudo systemctl status nebenkostenabrechnung --no-pager -l
```

Weboberfläche standardmäßig:

```text
http://SERVER-IP:8080
```

## Tests

Version 2.1.0 wurde mit 37 automatisierten Tests geprüft.

## Hinweis

Die Anwendung unterstützt bei Nebenkostenabrechnung und steuerlicher Vorbereitung, ersetzt aber keine Rechts- oder Steuerberatung. Steuerliche Einordnungen sind als Prüfhilfen gedacht und sollten durch den Steuerberater bestätigt werden.
