import importlib, sqlite3
from pathlib import Path

def test_version():
    from app.update_manager import CURRENT_VERSION
    assert CURRENT_VERSION=='2.9.1'

def test_meter_tables(tmp_path, monkeypatch):
    import app.database as d
    monkeypatch.setattr(d,'DB_PATH',str(tmp_path/'db.sqlite'))
    d.init_db()
    with sqlite3.connect(d.DB_PATH) as c:
        tables={x[0] for x in c.execute("select name from sqlite_master where type='table'")}
    assert {'meters','meter_readings'} <= tables

def test_smtp_columns(tmp_path, monkeypatch):
    import app.database as d
    monkeypatch.setattr(d,'DB_PATH',str(tmp_path/'db.sqlite'))
    d.init_db()
    with sqlite3.connect(d.DB_PATH) as c:
        cols={x[1] for x in c.execute('pragma table_info(settings)')}
    assert {'smtp_host','smtp_port','smtp_user','smtp_password','smtp_from','smtp_security'} <= cols

def test_update_path_guard(tmp_path, monkeypatch):
    import app.update_manager as u
    monkeypatch.setattr(u,'STAGING_DIR',tmp_path/'updates')
    bad=tmp_path/'evil.deb'; bad.write_bytes(b'x')
    try: u.install_staged_deb(bad)
    except ValueError: pass
    else: raise AssertionError('path guard missing')
