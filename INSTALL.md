# Installation auf Debian

Die Anwendung ist für Debian 12 und Debian 13 vorgesehen. Alle folgenden Befehle werden auf dem Zielserver ausgeführt.

## Variante A: Installation aus dem Repository

```bash
sudo apt update
sudo apt install -y git sudo
git clone https://github.com/Markus4771/Nebenkosten.git
cd Nebenkosten
sudo ./install.sh
```

## Variante B: Installation des Debian-Pakets

Ein lokal gebautes oder aus einem GitHub-Release geladenes Paket wird so installiert:

```bash
sudo apt install ./nebenkostenabrechnung_2.9.1_all.deb
```

Soll das Paket selbst gebaut werden:

```bash
sudo apt update
sudo apt install -y git dpkg-dev
git clone https://github.com/Markus4771/Nebenkosten.git
cd Nebenkosten
./scripts/build_deb.sh
sudo apt install ./dist/nebenkostenabrechnung_2.9.1_all.deb
```

## Anmeldung und Dienststatus

Die Weboberfläche ist standardmäßig unter `http://SERVER-IP:8080` erreichbar. Der erste Benutzer heißt `admin`. Das zufällig erzeugte Startpasswort wird bei der ersten Installation ausgegeben und steht in `/etc/default/nebenkostenabrechnung`:

```bash
sudo grep '^NEBENKOSTEN_ADMIN_PASSWORD=' /etc/default/nebenkostenabrechnung
sudo systemctl status nebenkostenabrechnung --no-pager -l
```

Die SQLite-Datenbank liegt unter `/var/lib/nebenkostenabrechnung/nebenkosten.db`.

## Aktualisierung

Ein neueres Debian-Paket kann erneut mit `apt` installiert werden. Daten unter `/var/lib/nebenkostenabrechnung` und die Konfiguration unter `/etc/default/nebenkostenabrechnung` bleiben erhalten:

```bash
sudo apt install ./nebenkostenabrechnung_NEUE_VERSION_all.deb
```

Die Updatefunktion der Weboberfläche setzt ein veröffentlichtes GitHub-Release mit einem passenden `_all.deb`-Asset voraus.

## Deinstallation

```bash
sudo apt remove nebenkostenabrechnung
```

Die Anwendungsdaten werden dabei nicht automatisch gelöscht.
