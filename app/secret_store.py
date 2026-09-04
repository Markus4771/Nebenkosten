from __future__ import annotations
import json, os
from pathlib import Path

SECRET_DIR=Path(os.getenv("NEBENKOSTEN_SECRET_DIR","/var/lib/nebenkostenabrechnung/secrets"))
SECRET_FIELDS=("ai_api_key","paperless_token","smtp_password","scan_smb_password")

def _path(user_id:int)->Path:
    return SECRET_DIR/f"user-{int(user_id)}.json"

def load(user_id:int)->dict:
    path=_path(user_id)
    if not path.is_file(): return {}
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}

def save(user_id:int, **values):
    SECRET_DIR.mkdir(parents=True,exist_ok=True)
    try: os.chmod(SECRET_DIR,0o700)
    except Exception: pass
    data=load(user_id)
    for key,value in values.items():
        if key in SECRET_FIELDS and value not in (None,""):
            data[key]=str(value)
    path=_path(user_id)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    os.chmod(tmp,0o600)
    tmp.replace(path)
    os.chmod(path,0o600)

def hydrate(row)->dict:
    if not row: return {}
    data=dict(row)
    uid=data.get("user_id")
    if uid:
        sec=load(uid)
        for field in SECRET_FIELDS:
            if sec.get(field): data[field]=sec[field]
    return data

def migrate_plaintext(conn):
    """Verschiebt vorhandene Klartext-Secrets aus SQLite in den geschützten Secret-Store."""
    try:
        rows=conn.execute("SELECT user_id,ai_api_key,paperless_token,smtp_password FROM settings").fetchall()
    except Exception:
        return
    for row in rows:
        uid=row[0]
        values={}
        for field,value in zip(("ai_api_key","paperless_token","smtp_password"),row[1:]):
            if value and value!="__secret_store__":
                values[field]=value
        if values:
            save(uid,**values)
            for field in values:
                conn.execute(f"UPDATE settings SET {field}='__secret_store__' WHERE user_id=?",(uid,))
