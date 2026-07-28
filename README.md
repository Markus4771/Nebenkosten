# Nebenkostenabrechnung 0.2.0

Webanwendung zur Erstellung einer einzelnen Nebenkostenabrechnung pro Mieter und Abrechnungszeitraum.

## Funktionen
- Vermieter-, Mieter- und Wohnungsdaten
- Abrechnungszeiträume und Vorauszahlungen
- Umlage nach Wohnfläche, Personen, Verbrauch, Wohneinheiten, Prozent oder Direktbetrag
- automatische Berechnung von Guthaben/Nachzahlung
- PDF-Ausgabe
- SQLite-Datenbank

## Lokaler Start
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export NEBENKOSTEN_DB="$PWD/data/nebenkosten.db"
python run.py
```
Aufruf: http://localhost:8080

## Hinweis
Vor produktivem Einsatz müssen Berechnung, umlagefähige Kosten und Abrechnungsfristen durch den Vermieter beziehungsweise eine fachkundige Stelle geprüft werden. Das Programm ersetzt keine Rechts- oder Steuerberatung.


## Mehrbenutzerbetrieb (Version 0.2.0)

- Administratoren legen Benutzerkonten an und können sie sperren.
- Jeder Benutzer verwaltet mehrere eigene Mieter und Abrechnungen.
- Mieter, Abrechnungen, Kosten, PDF-Dokumente und Vermieterdaten sind strikt dem angemeldeten Benutzer zugeordnet.
- Bestehende Daten aus Version 0.1.0 werden beim ersten Start dem Administratorkonto zugeordnet.
- Erstanmeldung: Benutzer `admin`, Passwort aus `NEBENKOSTEN_ADMIN_PASSWORD` (ohne Vorgabe zunächst `admin`). Das Passwort sollte unmittelbar geändert bzw. die Umgebungsvariable vor dem ersten Start gesetzt werden.
