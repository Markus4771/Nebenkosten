import json, os, shutil, sqlite3, tempfile, zipfile
from datetime import datetime
from pathlib import Path

from . import database

BACKUP_DIR=Path(os.getenv('NEBENKOSTEN_BACKUP_DIR','/var/lib/nebenkostenabrechnung/backups'))
UPLOAD_DIR=Path(os.getenv('NEBENKOSTEN_UPLOAD_DIR','/var/lib/nebenkostenabrechnung/uploads'))
DOCUMENT_DIR=Path(os.getenv('NEBENKOSTEN_DOCUMENT_DIR','/var/lib/nebenkostenabrechnung/documents'))
SECRET_DIR=Path(os.getenv('NEBENKOSTEN_SECRET_DIR','/var/lib/nebenkostenabrechnung/secrets'))


def _safe_name(name:str)->str:
    return ''.join(ch for ch in name if ch.isalnum() or ch in ('-','_','.'))


def create_backup(prefix='backup'):
    BACKUP_DIR.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    target=BACKUP_DIR/f'{_safe_name(prefix)}-{stamp}.zip'
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        db_copy=root/'nebenkosten.db'
        src=sqlite3.connect(database.DB_PATH)
        dst=sqlite3.connect(db_copy)
        try: src.backup(dst)
        finally: dst.close(); src.close()
        manifest={'format':1,'created_at':datetime.now().isoformat(timespec='seconds'),'app':'Nebenkostenabrechnung','version':'2.9.1'}
        (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        for source,name in [(UPLOAD_DIR,'uploads'),(DOCUMENT_DIR,'documents'),(SECRET_DIR,'secrets')]:
            if source.exists(): shutil.copytree(source,root/name)
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
            for f in root.rglob('*'):
                if f.is_file(): z.write(f,f.relative_to(root))
    return target


def list_backups():
    BACKUP_DIR.mkdir(parents=True,exist_ok=True)
    return sorted((p for p in BACKUP_DIR.glob('*.zip') if p.is_file()),key=lambda p:p.stat().st_mtime,reverse=True)


def validate_backup(path:Path):
    if not zipfile.is_zipfile(path): return False,'Keine gültige ZIP-Datei.'
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist())
        if 'manifest.json' not in names or 'nebenkosten.db' not in names: return False,'Backup enthält Manifest oder Datenbank nicht.'
        info=json.loads(z.read('manifest.json').decode('utf-8'))
        if info.get('app')!='Nebenkostenabrechnung': return False,'Backup gehört nicht zu dieser Anwendung.'
        with tempfile.TemporaryDirectory() as td:
            dbfile=Path(td)/'check.db'
            dbfile.write_bytes(z.read('nebenkosten.db'))
            try:
                con=sqlite3.connect(dbfile)
                result=con.execute('PRAGMA integrity_check').fetchone()[0]
                con.close()
                if str(result).lower()!='ok': return False,f'Datenbankprüfung fehlgeschlagen: {result}'
            except Exception as exc:
                return False,f'Datenbank im Backup ist nicht lesbar: {exc}'
    return True,''


def restore_backup(path:Path):
    ok,msg=validate_backup(path)
    if not ok: raise ValueError(msg)
    # Sicherheitsbackup vor jeder Wiederherstellung
    safety=create_backup('vor-wiederherstellung')
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        with zipfile.ZipFile(path) as z:
            for member in z.infolist():
                dest=(root/member.filename).resolve()
                if root.resolve() not in dest.parents and dest!=root.resolve(): raise ValueError('Unsicherer ZIP-Pfad.')
            z.extractall(root)
        Path(database.DB_PATH).parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root/'nebenkosten.db',database.DB_PATH)
        for name,target in [('uploads',UPLOAD_DIR),('documents',DOCUMENT_DIR),('secrets',SECRET_DIR)]:
            src=root/name
            if name=='secrets' and not src.exists():
                # Backups vor 2.8.0 enthalten noch keinen Secret-Store. Vorhandene Secrets behalten.
                continue
            if target.exists(): shutil.rmtree(target)
            if src.exists(): shutil.copytree(src,target)
            else: target.mkdir(parents=True,exist_ok=True)
    database.init_db()
    return safety

def copy_backup_to_smb(path):
    import subprocess
    server=os.getenv('NEBENKOSTEN_SMB_SERVER','').strip(); share=os.getenv('NEBENKOSTEN_SMB_SHARE','').strip(); user=os.getenv('NEBENKOSTEN_SMB_USER','').strip(); password=os.getenv('NEBENKOSTEN_SMB_PASSWORD',''); subdir=os.getenv('NEBENKOSTEN_SMB_DIR','Nebenkosten').strip('/\\')
    if not server or not share: raise ValueError('SMB-Ziel ist nicht konfiguriert.')
    remote=f'//{server}/{share}'; auth=['-N'] if not user else ['-U',f'{user}%{password}']
    cmd=(f'mkdir "{subdir}"; cd "{subdir}"; ' if subdir else '')+f'put "{path}" "{path.name}"'
    r=subprocess.run(['smbclient',remote,*auth,'-c',cmd],capture_output=True,text=True,timeout=90)
    if r.returncode: raise RuntimeError((r.stderr or r.stdout or 'SMB-Upload fehlgeschlagen').strip())
    return f'{remote}/{subdir}/{path.name}'
