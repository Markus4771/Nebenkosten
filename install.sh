#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Bitte mit sudo ausführen."; exit 1; fi
apt-get update
apt-get install -y python3-venv tesseract-ocr tesseract-ocr-deu poppler-utils smbclient samba sudo
id nebenkosten >/dev/null 2>&1 || useradd --system --home /var/lib/nebenkostenabrechnung --shell /usr/sbin/nologin nebenkosten
getent group nebenkosten-scan >/dev/null || groupadd --system nebenkosten-scan
mkdir -p /opt/nebenkostenabrechnung /var/lib/nebenkostenabrechnung /var/lib/nebenkostenabrechnung/uploads /var/lib/nebenkostenabrechnung/documents /var/lib/nebenkostenabrechnung/backups /var/lib/nebenkostenabrechnung/updates /var/lib/nebenkostenabrechnung/secrets /var/lib/nebenkostenabrechnung/csv-previews /var/lib/nebenkostenabrechnung/scan
chown root:nebenkosten-scan /var/lib/nebenkostenabrechnung/scan
chmod 0711 /var/lib/nebenkostenabrechnung/scan
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
install -m 0755 packaging/debian/nebenkosten-install-update /usr/local/sbin/nebenkosten-install-update
install -m 0440 packaging/debian/nebenkosten-update-sudoers /etc/sudoers.d/nebenkosten-update
install -m 0755 packaging/debian/nebenkosten-scan-share /usr/local/sbin/nebenkosten-scan-share
install -m 0440 packaging/debian/nebenkosten-scan-sudoers /etc/sudoers.d/nebenkosten-scan
if ! grep -q '^\[Nebenkosten-Scan\]$' /etc/samba/smb.conf; then
cat >> /etc/samba/smb.conf <<'SMB'

[Nebenkosten-Scan]
   path = /var/lib/nebenkostenabrechnung/scan
   browseable = yes
   read only = no
   guest ok = no
   valid users = @nebenkosten-scan
   create mask = 0600
   directory mask = 0700
   force group = nebenkosten-scan
SMB
fi
chown -R nebenkosten:nebenkosten /var/lib/nebenkostenabrechnung /opt/nebenkostenabrechnung
chown root:nebenkosten-scan /var/lib/nebenkostenabrechnung/scan
chmod 0711 /var/lib/nebenkostenabrechnung/scan
chmod 0700 /var/lib/nebenkostenabrechnung/secrets
chmod 0750 /var/lib/nebenkostenabrechnung/csv-previews
systemctl daemon-reload
systemctl enable --now smbd.service
systemctl enable --now nebenkostenabrechnung.service
echo "Installation abgeschlossen. Weboberfläche: http://SERVER-IP:8080"
echo "Erster Benutzer: admin"
if [[ -n "$FIRST_PASSWORD" ]]; then echo "Einmaliges Startpasswort: $FIRST_PASSWORD"; else echo "Das Startpasswort wurde bei einer früheren Installation erzeugt."; fi
