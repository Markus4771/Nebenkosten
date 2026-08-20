#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Bitte mit sudo ausführen."; exit 1; fi
apt-get update
apt-get install -y python3-venv tesseract-ocr tesseract-ocr-deu poppler-utils
id nebenkosten >/dev/null 2>&1 || useradd --system --home /var/lib/nebenkostenabrechnung --shell /usr/sbin/nologin nebenkosten
mkdir -p /opt/nebenkostenabrechnung /var/lib/nebenkostenabrechnung /var/lib/nebenkostenabrechnung/uploads /var/lib/nebenkostenabrechnung/documents /var/lib/nebenkostenabrechnung/backups /var/lib/nebenkostenabrechnung/updates
cp -a app requirements.txt run.py /opt/nebenkostenabrechnung/
python3 -m venv /opt/nebenkostenabrechnung/venv
/opt/nebenkostenabrechnung/venv/bin/pip install --upgrade pip
/opt/nebenkostenabrechnung/venv/bin/pip install -r /opt/nebenkostenabrechnung/requirements.txt
chown -R nebenkosten:nebenkosten /opt/nebenkostenabrechnung/venv
chmod -R u+rwX,go+rX /opt/nebenkostenabrechnung/venv

FIRST_PASSWORD=""
if [[ ! -f /etc/default/nebenkostenabrechnung ]]; then
  SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  FIRST_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
  umask 077
  cat > /etc/default/nebenkostenabrechnung <<CFG
NEBENKOSTEN_SESSION_SECRET=${SESSION_SECRET}
NEBENKOSTEN_ADMIN_PASSWORD=${FIRST_PASSWORD}
CFG
fi

cp nebenkostenabrechnung.service /etc/systemd/system/
chown -R nebenkosten:nebenkosten /var/lib/nebenkostenabrechnung /opt/nebenkostenabrechnung
systemctl daemon-reload
systemctl enable --now nebenkostenabrechnung.service
echo "Installation abgeschlossen. Weboberfläche: http://SERVER-IP:8080"
echo "Erster Benutzer: admin"
if [[ -n "$FIRST_PASSWORD" ]]; then echo "Einmaliges Startpasswort: $FIRST_PASSWORD"; else echo "Das Startpasswort wurde bei einer früheren Installation erzeugt."; fi
