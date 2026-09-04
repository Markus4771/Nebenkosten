# Changelog

## 2.9.1

- Jinja-Template `tax_advisor.html` korrigiert
- Steuerjahr-Assistent wieder innerhalb des Template-Inhaltsblocks platziert
- Versionsangaben in Anwendung, Healthcheck, Update-Manager und Debian-Paket vereinheitlicht
- Entwicklungsstruktur und Tests aus dem vollständigen 2.3.0-Archiv und dem installierten Paketstand 2.9.1 rekonstruiert

## 2.3.0

- monatliche Kaltmiete und Nebenkostenvorauszahlung je Mieter
- Erfassung und CSV-Import von Mietzahlungen
- automatische Spalten-, Trennzeichen- und Zeichensatzerkennung
- automatische Mieterzuordnung und Dublettenerkennung
- Aufteilung gemeinsamer oder getrennter Zahlungen in Kaltmiet-, Nebenkosten- und Restanteil
- Zusammenfassung von Teilzahlungen und Bewertung von Unter- oder Überzahlungen
- Steuerdaten, Einnahmen und Werbungskosten-Prüfposten je Objekt und Jahr
- Steuerberater-PDF, CSV-Export und Anlage-V-Vorbereitung
- Google Gemini und OpenRouter als zusätzliche KI-Anbieter
- Modelllisten und Verbindungstest für unterstützte KI-Anbieter
- strukturierte Verbrauchserkennung und Vergleich mit eigenen Zählerständen
- Zählerverknüpfung mit Abrechnungen, Verbrauchsermittlung und Mehrjahresvergleich

## 1.6.0

- Zähler- und Verbrauchsverwaltung
- SMTP-Versand
- SMB/NAS-Backup
- Web-Update

## 1.5.0

- Dokumentenverwaltung mit benutzergetrenntem Upload, Download und Löschen
- Backup und Wiederherstellung für Datenbank, Abrechnungen und Dokumente
- automatisches Sicherheitsbackup vor einer Wiederherstellung
- GitHub-Release-Prüfung als kontrollierte Updatefunktion
- Debian-Paketbau mit SHA256-Prüfsumme
- GitHub Actions für Tests und Paketbau
- Systembereich in der Weboberfläche

## 1.4.0

- Kostenpositionen in der OCR-/KI-Prüfung hinzufügen und löschen
- Rekonstruktion einfacher mehrzeiliger Tabellen aus PDF- und OCR-Text
- Prüfbericht mit Plausibilitätswert, Feststellungen und Empfehlungen
- Mehrjahresübersicht je Mieter und verbesserter Vorjahresvergleich

## 1.3.0

- strukturierte Erkennung von Kostenzeilen und Verteilerschlüsseln
- rechnerische Plausibilitätsprüfung für Summen und Saldo
- Vorjahresvergleich und Kennzeichnung von Auffälligkeiten
- OCR-Fallback für reine Scan-PDFs mit Poppler und Tesseract
- manuelle Korrektur erkannter Abrechnungswerte
- KI-Provider-Grundlage für Ollama, OpenAI und Anthropic Claude
- benutzerbezogene Provider-Konfiguration

## 1.1.0

- Upload und lokale OCR-/Textextraktion erhaltener Nebenkostenabrechnungen
