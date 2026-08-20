#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(cat "$ROOT/version.txt")"
BUILD_ROOT="$(mktemp -d /tmp/nebenkosten-deb.XXXXXX)"
trap 'rm -rf "$BUILD_ROOT"' EXIT
PKG="$BUILD_ROOT/nebenkostenabrechnung_${VERSION}_all"
rm -rf "$ROOT/dist"; mkdir -p "$PKG/DEBIAN" "$PKG/opt/nebenkostenabrechnung" "$PKG/etc/systemd/system" "$ROOT/dist"
chmod 0755 "$PKG/DEBIAN"
cp "$ROOT/packaging/debian/control" "$PKG/DEBIAN/control"
sed -i "s/^Version:.*/Version: $VERSION/" "$PKG/DEBIAN/control"
cp "$ROOT/packaging/debian/postinst" "$ROOT/packaging/debian/prerm" "$PKG/DEBIAN/"
cp -a "$ROOT/app" "$ROOT/requirements.txt" "$ROOT/run.py" "$ROOT/packaging" "$PKG/opt/nebenkostenabrechnung/"
find "$PKG/opt/nebenkostenabrechnung" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$PKG/opt/nebenkostenabrechnung" -type f -name '*.pyc' -delete
cp "$ROOT/nebenkostenabrechnung.service" "$PKG/etc/systemd/system/"
find "$PKG/DEBIAN" -type d -exec chmod 0755 {} +
dpkg-deb --build --root-owner-group "$PKG" "$ROOT/dist/nebenkostenabrechnung_${VERSION}_all.deb"
sha256sum "$ROOT/dist/nebenkostenabrechnung_${VERSION}_all.deb" > "$ROOT/dist/nebenkostenabrechnung_${VERSION}_all.deb.sha256"
