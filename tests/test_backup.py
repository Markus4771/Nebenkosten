import sqlite3, zipfile
from pathlib import Path
from app import database
from app import backup


def test_backup_and_restore(tmp_path, monkeypatch):
    dbp=tmp_path/'db.sqlite'; up=tmp_path/'uploads'; docs=tmp_path/'documents'; backups=tmp_path/'backups'
    monkeypatch.setattr(database,'DB_PATH',str(dbp)); monkeypatch.setattr(backup.database,'DB_PATH',str(dbp))
    monkeypatch.setattr(backup,'UPLOAD_DIR',up); monkeypatch.setattr(backup,'DOCUMENT_DIR',docs); monkeypatch.setattr(backup,'BACKUP_DIR',backups)
    database.init_db(); up.mkdir(); docs.mkdir(); (up/'a.txt').write_text('ocr'); (docs/'b.txt').write_text('doc')
    with database.db() as c: c.execute("insert into properties(user_id,name) values(1,'Haus')")
    path=backup.create_backup()
    ok,msg=backup.validate_backup(path); assert ok, msg
    with database.db() as c: c.execute("delete from properties")
    (up/'a.txt').unlink(); (docs/'b.txt').unlink()
    safety=backup.restore_backup(path)
    assert safety.exists()
    with database.db() as c: assert c.execute("select count(*) from properties where name='Haus'").fetchone()[0]==1
    assert (up/'a.txt').read_text()=='ocr' and (docs/'b.txt').read_text()=='doc'


def test_invalid_backup(tmp_path):
    p=tmp_path/'x.zip'
    with zipfile.ZipFile(p,'w') as z: z.writestr('x.txt','bad')
    ok,msg=backup.validate_backup(p)
    assert not ok
