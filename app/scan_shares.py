from __future__ import annotations

import re
import secrets
import socket
import subprocess
import tempfile
from pathlib import Path

from fastapi import Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .database import db
from .secret_store import load as load_secrets, save as save_secrets

HELPER = "/usr/local/sbin/nebenkosten-scan-share"
USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{2,30}$")
FOLDER_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SHARE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _ensure_schema():
    with db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS scan_shares (
              user_id INTEGER PRIMARY KEY,
              enabled INTEGER NOT NULL DEFAULT 0,
              smb_username TEXT NOT NULL,
              folder_name TEXT NOT NULL,
              share_name TEXT NOT NULL DEFAULT 'Nebenkosten-Scan',
              server_name TEXT,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)


def _safe_folder(username: str, uid: int) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", (username or "").strip()).strip("._-")
    return value[:48] or f"user-{uid}"


def _defaults(user):
    uid = int(user["id"])
    return {
        "user_id": uid,
        "enabled": 0,
        "smb_username": f"nk_scan_{uid}",
        "folder_name": _safe_folder(user["username"], uid),
        "share_name": "Nebenkosten-Scan",
        "server_name": "",
    }


def _get_settings(user):
    _ensure_schema()
    with db() as c:
        row = c.execute("SELECT * FROM scan_shares WHERE user_id=?", (user["id"],)).fetchone()
    data = dict(row) if row else _defaults(user)
    data["password"] = load_secrets(int(user["id"])).get("scan_smb_password", "")
    return data


def _validate(smb_username: str, folder_name: str, share_name: str):
    if not USERNAME_RE.fullmatch(smb_username):
        raise HTTPException(400, "SMB-Benutzername: nur Kleinbuchstaben, Ziffern, _ und -; 3 bis 31 Zeichen.")
    if not FOLDER_RE.fullmatch(folder_name):
        raise HTTPException(400, "Ungültiger Scan-Ordnername.")
    if not SHARE_RE.fullmatch(share_name):
        raise HTTPException(400, "Ungültiger Freigabename.")


def _apply_system(uid: int, smb_username: str, folder_name: str, enabled: bool, password: str):
    if not Path(HELPER).is_file():
        return "System-Helfer ist noch nicht installiert. Bitte install.sh erneut ausführen."
    proc = subprocess.run(
        ["sudo", HELPER, "configure", str(uid), smb_username, folder_name, "1" if enabled else "0"],
        input=password + "\n",
        text=True,
        capture_output=True,
        timeout=20,
    )
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout or "SMB-Konfiguration fehlgeschlagen.").strip()
    return ""


def _save_for_user(target, enabled: int, smb_username: str, folder_name: str, share_name: str,
                   server_name: str, smb_password: str):
    smb_username = smb_username.strip().lower()
    folder_name = folder_name.strip()
    share_name = share_name.strip() or "Nebenkosten-Scan"
    server_name = server_name.strip()
    _validate(smb_username, folder_name, share_name)
    existing = load_secrets(int(target["id"])).get("scan_smb_password", "")
    password = smb_password.strip() or existing or secrets.token_urlsafe(12)
    if len(password) < 8:
        raise HTTPException(400, "Das SMB-Passwort muss mindestens 8 Zeichen haben.")
    enabled_bool = bool(enabled)
    error = _apply_system(int(target["id"]), smb_username, folder_name, enabled_bool, password)
    if error:
        raise HTTPException(500, error)
    with db() as c:
        c.execute("""
            INSERT INTO scan_shares(user_id,enabled,smb_username,folder_name,share_name,server_name,updated_at)
            VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
              enabled=excluded.enabled,smb_username=excluded.smb_username,
              folder_name=excluded.folder_name,share_name=excluded.share_name,
              server_name=excluded.server_name,updated_at=CURRENT_TIMESTAMP
        """, (target["id"], 1 if enabled_bool else 0, smb_username, folder_name, share_name, server_name))
    save_secrets(int(target["id"]), scan_smb_password=password)


def _path(settings, request: Request):
    server = settings.get("server_name") or request.url.hostname or socket.gethostname()
    return f"\\\\{server}\\{settings['share_name']}\\{settings['folder_name']}"


def register_scan_routes(app, templates, ctx, require_user, require_write):
    _ensure_schema()

    @app.get("/scan-share", response_class=HTMLResponse)
    def scan_share_get(request: Request):
        user = require_user(request)
        settings = _get_settings(user)
        return templates.TemplateResponse("scan_shares.html", ctx(
            request, scan=settings, scan_path=_path(settings, request), users=None, message=None, error=None
        ))

    @app.post("/scan-share")
    def scan_share_save(request: Request, enabled: int = Form(0), smb_username: str = Form(...),
                        folder_name: str = Form(...), share_name: str = Form("Nebenkosten-Scan"),
                        server_name: str = Form(""), smb_password: str = Form("")):
        user = require_write(request)
        _save_for_user(user, enabled, smb_username, folder_name, share_name, server_name, smb_password)
        return RedirectResponse("/scan-share", 303)

    @app.post("/scan-share/regenerate")
    def scan_share_regenerate(request: Request):
        user = require_write(request)
        settings = _get_settings(user)
        new_password = secrets.token_urlsafe(12)
        _save_for_user(user, settings["enabled"], settings["smb_username"], settings["folder_name"],
                       settings["share_name"], settings.get("server_name") or "", new_password)
        return RedirectResponse("/scan-share", 303)

    @app.post("/scan-share/test", response_class=HTMLResponse)
    def scan_share_test(request: Request):
        user = require_user(request)
        settings = _get_settings(user)
        server = settings.get("server_name") or "127.0.0.1"
        password = settings.get("password") or ""
        if not settings.get("enabled") or not password:
            error = "Die Scan-Freigabe ist nicht aktiviert oder es fehlen Zugangsdaten."
        else:
            auth_path = None
            try:
                with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
                    auth_path = f.name
                    f.write(f"username = {settings['smb_username']}\npassword = {password}\n")
                Path(auth_path).chmod(0o600)
                proc = subprocess.run([
                    "smbclient", f"//{server}/{settings['share_name']}", "-A", auth_path,
                    "-c", f"cd {settings['folder_name']}; ls"
                ], capture_output=True, text=True, timeout=15)
                error = "" if proc.returncode == 0 else (proc.stderr or proc.stdout).strip()
            except Exception as exc:
                error = str(exc)
            finally:
                if auth_path:
                    Path(auth_path).unlink(missing_ok=True)
        return templates.TemplateResponse("scan_shares.html", ctx(
            request, scan=settings, scan_path=_path(settings, request), users=None,
            message="Verbindung erfolgreich getestet." if not error else None, error=error or None
        ))

    @app.get("/scan-shares", response_class=HTMLResponse)
    def scan_shares_admin(request: Request):
        user = require_user(request)
        if not user["is_admin"]:
            raise HTTPException(403)
        with db() as c:
            rows = c.execute("""
                SELECT u.id,u.username,u.display_name,u.active,
                       COALESCE(s.enabled,0) enabled,s.smb_username,s.folder_name,s.share_name,s.server_name
                FROM users u LEFT JOIN scan_shares s ON s.user_id=u.id ORDER BY u.username
            """).fetchall()
        users = []
        for row in rows:
            item = dict(row)
            defaults = _defaults(row)
            for key in ("smb_username", "folder_name", "share_name", "server_name"):
                if not item.get(key): item[key] = defaults[key]
            item["password"] = load_secrets(int(row["id"])).get("scan_smb_password", "")
            users.append(item)
        own = _get_settings(user)
        return templates.TemplateResponse("scan_shares.html", ctx(
            request, scan=own, scan_path=_path(own, request), users=users, message=None, error=None
        ))

    @app.post("/scan-shares/{uid}")
    def scan_share_admin_save(uid: int, request: Request, enabled: int = Form(0), smb_username: str = Form(...),
                              folder_name: str = Form(...), share_name: str = Form("Nebenkosten-Scan"),
                              server_name: str = Form(""), smb_password: str = Form("")):
        admin = require_write(request)
        if not admin["is_admin"]:
            raise HTTPException(403)
        with db() as c:
            target = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not target:
            raise HTTPException(404)
        _save_for_user(target, enabled, smb_username, folder_name, share_name, server_name, smb_password)
        return RedirectResponse("/scan-shares", 303)
