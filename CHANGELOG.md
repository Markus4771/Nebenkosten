# 2.9.1

- Hotfix fuer das Jinja-Template `tax_advisor.html`
- Steuerjahr-Assistent wieder innerhalb des Template-Blocks
- Versionsangaben in Anwendung, Healthcheck, Update-Manager und Debian-Metadaten vereinheitlicht
- Entwicklungsstruktur und Tests auf Basis des vollstaendigen 2.3.0-Archivs rekonstruiert

# 2.3.0
- Monatliche Nebenkostenvorauszahlung je Mieter
- gemeinsame oder getrennte Überweisungen automatisch aufteilen
- Teilzahlungen monatsweise zusammenfassen
- Kaltmiet-, Nebenkosten- und Restanteil je Zahlung speichern
- Unter-/Überzahlung mit Toleranz bewerten
- CSV-Import nutzt dieselbe Monatslogik

# 2.3.0
- CSV-Import für Mietzahlungen
- automatische Spalten-, Trennzeichen- und Zeichensatzerkennung
- automatische Mieterzuordnung aus Name/Verwendungszweck
- Dublettenerkennung über Import-Fingerprint
- negative/unklare Buchungen werden sicher übersprungen

# 2.3.0
- Monatliche Kaltmiete je Mieter
- Soll/Ist-Mietzahlungen und Zahlungserfassung
- Zahlungseingänge in Steuerbereich übernehmen
- Kosten automatisch Steuerkategorien vorschlagen und übernehmen
- Anlage-V-Vorbereitungs-PDF pro Objekt

# 2.3.0
- Steuerdaten pro Objekt und Jahr erfassen
- Einnahmen, Werbungskosten-Prüfposten, AfA und Zinsen
- Steuerberater-PDF erweitert
- CSV-Export für Steuerberater
- Erhaltungsrücklage wird nur als Prüfposten geführt

# 2.3.0
- Google Gemini als KI-Provider ergänzt
- Gemini-Modellliste und Verbindungstest
- Direkte Gemini-REST-Analyse mit JSON-Ausgabe

## 2.3.0
- Zähler direkt mit Abrechnungen verknüpft
- Ablesezeiträume automatisch ermittelt
- Verbrauch aus Start-/Endablesung nachvollziehbar gespeichert
- Verbrauch automatisch in Kostenpositionen übernehmbar
- Zählerstandsdiagramm ohne externe JS-Bibliothek
- Mehrjahresvergleich des Verbrauchs je Zähler
- Datenbankmigration für Zählerbezug an Kostenpositionen

## 1.6.0
- Zähler und Verbrauch
- SMTP-Versand
- SMB/NAS-Backup
- Web-Update

# Changelog

## 1.5.0
- Dokumentenverwaltung mit benutzergetrenntem Upload, Download und Löschen
- Backup/Wiederherstellung für Datenbank, erhaltene Abrechnungen und Dokumente
- automatisches Sicherheitsbackup vor einer Wiederherstellung
- GitHub-Release-Prüfung als kontrollierte Updatefunktion
- Debian-Paket-Build inklusive SHA256
- GitHub Actions für Tests und .deb-Build
- Systembereich in der Weboberfläche

# Changelog

## 1.4.0
- Kostenpositionen in der OCR-/KI-Prüfung hinzufügen und löschen.
- Rekonstruktion einfacher mehrzeiliger Tabellen aus PDF-/OCR-Text.
- Automatischer Prüfbericht mit Plausibilitätswert, Feststellungen und Empfehlungen.
- KI-Provider können zusätzliche Feststellungen und Empfehlungen liefern.
- Mehrjahresübersicht pro Mieter mit Kostenartenvergleich über alle vorhandenen Abrechnungen.
- Auswahl der zeitlich vorherigen Abrechnung für den Vorjahresvergleich verbessert.

## 1.3.0
- Analysemodell 1.2 für erhaltene Hausverwaltungsabrechnungen
- Kostenzeilen unterscheiden soweit erkennbar zwischen Gesamtkosten und Mieteranteil
- Erkennung typischer Verteilerschlüssel
- rechnerische Plausibilitätsprüfungen für Summen und Saldo
- automatische Kennzeichnung von Auffälligkeiten
- Vorjahresvergleich je zugeordnetem Mieter mit Euro- und Prozentänderung
- Neu-Auswertung bereits hochgeladener Dokumente mit der aktuellen Analyseversion
- OCR-Fallback für reine Scan-PDFs via pdftoppm + Tesseract, wenn verfügbar

## 1.1.0
- Upload und lokale OCR/Extraktion erhaltener Nebenkostenabrechnungen

## 1.3.0
- Manuelle Korrektur erkannter Abrechnungswerte und Kostenpositionen.
- KI-Provider-Gerüst für Ollama, OpenAI und Anthropic Claude.
- KI-Ergebnisse werden mit der lokalen Plausibilitätsprüfung zusammengeführt.
- Provider-Konfiguration pro Benutzer in den Einstellungen.

## 2.3.0
- OpenRouter als KI-Provider mit konfigurierbarer Basis-URL, API-Key, HTTP-Referer und App-Titel.
- OpenRouter/Ollama Modelllisten und KI-Verbindungstest in den Einstellungen.
- KI extrahiert strukturierte Verbrauchswerte aus Hausverwaltungsabrechnungen.
- Automatischer Vergleich erkannter Verbräuche mit eigenen Zählerständen und Abweichungsbewertung.
