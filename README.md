# Nebenkostenabrechnung 1.4.0

Webanwendung zur Verwaltung und Erstellung von Nebenkostenabrechnungen mit mehreren Benutzern, Objekten, Wohnungen und Mietern. Zusätzlich können erhaltene Abrechnungen der Hausverwaltung lokal eingelesen und geprüft werden.

## Funktionen
- Mehrbenutzerbetrieb mit getrennten Datenbereichen
- Objekte, Wohnungen und mehrere Mieter
- eigene Abrechnungen, Vorauszahlungen und Kostenverteilung
- PDF-Ausgabe
- Upload erhaltener PDF-, Scan- und Bildabrechnungen
- lokale Textauslesung und Tesseract-OCR
- Erkennung von Zeitraum, Kostenpositionen, Mieteranteilen und Verteilerschlüsseln
- Plausibilitätsprüfungen
- Vorjahresvergleich je Mieter
- Kennzeichnung auffälliger Kostenänderungen

## Installation
```bash
sudo ./install.sh
```
Danach: `http://SERVER-IP:8080`

## Datenschutz
Die Dokumentanalyse läuft in Version 1.3 lokal. Es werden ohne weitere Konfiguration keine Dokumente an einen Cloud-KI-Anbieter gesendet.

## Hinweis
Automatische Erkennung kann Fehler enthalten. Ergebnisse müssen vor Verwendung geprüft werden. Die Anwendung ersetzt keine Rechts- oder Steuerberatung.


## Version 2.9.1

Dieser Quellstand wurde aus dem vollstaendigen Entwicklungsarchiv 2.3.0 und
dem installierbaren Anwendungscode des Debian-Pakets 2.9.1 rekonstruiert.
- Zähler- und Verbrauchsverwaltung
- SMTP-E-Mail-Versand
- SMB/NAS-Backup
- Updateinstallation aus der Weboberfläche
