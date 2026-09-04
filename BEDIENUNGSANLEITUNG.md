# Bedienungsanleitung 2.9.1

## Erste Schritte

1. Mit dem Benutzer `admin` und dem vom Installer erzeugten Startpasswort anmelden.
2. Unter **Benutzer** bei Bedarf weitere Zugänge und Rollen anlegen.
3. Unter **Objekte & Wohnungen** ein Gebäude und dessen Wohnungen anlegen.
4. Unter **Mieter** einen Mieter einer Wohnung zuordnen und Mietdaten hinterlegen.
5. Eine Abrechnung anlegen, Vorauszahlungen und Kosten erfassen.
6. Das Ergebnis prüfen und als PDF öffnen oder per SMTP versenden.

Jeder normale Benutzer sieht ausschließlich seine eigenen Daten. Benutzer mit der Rolle **Betrachter** besitzen nur Leserechte.

## Dokumente und erhaltene Abrechnungen

- PDF-, Scan- und Bildabrechnungen können zur lokalen Textauslesung hochgeladen werden.
- Bei Scans verwendet die Anwendung Tesseract-OCR.
- Eine externe KI-Auswertung findet nur statt, wenn ein KI-Anbieter eingerichtet und die Analyse bewusst gestartet wird.
- Erkannte Werte und Vorschläge müssen vor der Übernahme geprüft werden.

## Zahlungen und Steuerbereich

- Mietzahlungen können einzeln oder per CSV importiert werden.
- Die Anwendung unterstützt die Aufteilung in Kaltmiete, Nebenkosten und weitere Anteile.
- Steuerliche Zuordnungen sind Vorschläge zur Vorbereitung für den Steuerberater.

## Zähler

Unter **Zähler** lassen sich Zähler, Stände und Ablesezeiträume verwalten. Aus Start- und Endstand kann der Verbrauch berechnet und einer Kostenposition zugeordnet werden.

## Datensicherung

Im Systembereich können lokale Sicherungen erstellt und geprüft wiederhergestellt werden. Vor jeder Wiederherstellung erzeugt die Anwendung automatisch eine Sicherheitssicherung. Für ein zusätzliches SMB/NAS-Ziel werden die entsprechenden Umgebungsvariablen benötigt.

## Hinweis

Die Anwendung unterstützt bei Abrechnung und steuerlicher Vorbereitung, ersetzt aber keine Rechts- oder Steuerberatung.
