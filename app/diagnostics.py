from __future__ import annotations
import os, sqlite3
from pathlib import Path

def production_checks(db_path, upload_dir, document_dir, backup_dir, secret_dir, settings=None):
    settings=settings or {}
    checks=[]
    def add(key,label,ok,detail="",level=None):
        checks.append({"key":key,"label":label,"ok":bool(ok),"detail":str(detail or ""),
                       "level":level or ("ok" if ok else "error")})
    # database
    try:
        con=sqlite3.connect(str(db_path))
        result=con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        add("database","SQLite-Datenbank",str(result).lower()=="ok",result)
    except Exception as exc:
        add("database","SQLite-Datenbank",False,exc)
    # storage
    for key,label,path in [
        ("uploads","Upload-Verzeichnis",Path(upload_dir)),
        ("documents","Dokumenten-Verzeichnis",Path(document_dir)),
        ("backups","Backup-Verzeichnis",Path(backup_dir)),
        ("secrets","Secret-Verzeichnis",Path(secret_dir)),
    ]:
        try:
            path.mkdir(parents=True,exist_ok=True)
            test=path/".write-test"
            test.write_text("ok",encoding="utf-8"); test.unlink()
            add(key,label,True,str(path))
        except Exception as exc:
            add(key,label,False,f"{path}: {exc}")
    # secrets permissions
    try:
        p=Path(secret_dir)
        mode=(p.stat().st_mode & 0o777) if p.exists() else 0
        secure=mode in (0o700,0o750)
        add("secret_permissions","Secret-Verzeichnisrechte",secure,oct(mode),
            "ok" if secure else "warn")
    except Exception as exc:
        add("secret_permissions","Secret-Verzeichnisrechte",False,exc)
    # integration configuration (configuration checks only, no external request here)
    ai=settings.get("ai_provider") or "none"
    add("ai_config","KI-Konfiguration",ai!="none",f"Provider: {ai}",
        "ok" if ai!="none" else "warn")
    if settings.get("paperless_enabled"):
        ok=bool(settings.get("paperless_url") and settings.get("paperless_token"))
        add("paperless_config","Paperless-Konfiguration",ok,
            settings.get("paperless_url") or "URL/Token unvollständig",
            "ok" if ok else "warn")
    else:
        add("paperless_config","Paperless-Konfiguration",True,"optional deaktiviert","ok")
    # operational warnings
    summary={"ok":sum(1 for c in checks if c["level"]=="ok"),
             "warn":sum(1 for c in checks if c["level"]=="warn"),
             "error":sum(1 for c in checks if c["level"]=="error")}
    summary["ready"]=summary["error"]==0
    return checks,summary
