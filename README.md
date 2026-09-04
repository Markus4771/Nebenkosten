# Nebenkostenabrechnung 2.9.1

Webanwendung für Vermieter zur Erstellung und Verwaltung von Nebenkostenabrechnungen sowie zur Prüfung erhaltener Hausverwaltungsabrechnungen.

## Funktionen

- Mehrbenutzerbetrieb mit getrennten Datenbereichen und Rollen
- Objekte, Wohnungen und mehrere Mieter
- Nebenkostenabrechnungen mit Verteilerschlüsseln und PDF-Ausgabe
- Mietzahlungen mit Soll-/Ist-Vergleich und CSV-Import
- Steuerberater-Jahresübersicht, CSV-Export und Anlage-V-Vorbereitung
- Zählerstände, Verbrauchsauswertung und Mehrjahresvergleich
- Dokumentenverwaltung mit lokaler PDF-Texterkennung und Tesseract-OCR
- optionale KI-Auswertung über Ollama, OpenAI, Anthropic Claude, OpenRouter oder Google Gemini
- optionale Paperless-ngx-Anbindung
- Backup, Wiederherstellung und SMB/NAS-Backup
- SMTP-Versand und kontrollierte Updateinstallation

## Unterstützte Plattform

Die produktive Installation ist für Debian 12 und Debian 13 vorgesehen. Benötigt werden ein Internetzugang während der Installation und ein Benutzer mit `sudo`-Rechten.

## Installation

Die ausführliche Anleitung steht in [INSTALL.md](INSTALL.md). Für eine Installation direkt aus dem Quellcode:

```bash
git clone https://github.com/Markus4771/Nebenkosten.git
cd Nebenkosten
sudo ./install.sh
```

Danach ist die Weboberfläche standardmäßig unter `http://SERVER-IP:8080` erreichbar.

## Erster Login

Der Installer erzeugt bei der ersten Installation ein zufälliges Passwort für den Benutzer `admin` und zeigt es am Ende an. Die Zugangsdaten werden außerdem ausschließlich für `root` lesbar in `/etc/default/nebenkostenabrechnung` gespeichert.

## Entwicklung und Tests

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest -q
```

Debian-Paket bauen:

```bash
./scripts/build_deb.sh
```

Das Paket und seine SHA256-Prüfsumme werden unter `dist/` erzeugt.

## Datenschutz

PDF-Textauslesung und OCR laufen lokal. Dokumente werden nur dann an einen externen KI-Anbieter oder an Paperless-ngx übertragen, wenn die jeweilige Integration eingerichtet und bewusst verwendet wird.

## Herkunft des Quellstands

Version 2.9.1 wurde aus dem vollständigen Entwicklungsarchiv 2.3.0 und dem installierbaren Anwendungscode des Debian-Pakets 2.9.1 rekonstruiert. Die Rekonstruktion wird durch automatisierte Tests und einen reproduzierbaren Debian-Paketbau abgesichert.

## Hinweis

Automatische Erkennung und steuerliche Einordnungen können Fehler enthalten. Ergebnisse müssen vor Verwendung geprüft werden. Die Anwendung ersetzt keine Rechts- oder Steuerberatung.
