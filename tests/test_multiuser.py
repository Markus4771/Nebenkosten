import sqlite3
from pathlib import Path
from app import database


def test_fresh_database_creates_admin_and_user_scoped_settings(tmp_path, monkeypatch):
    path=tmp_path/'fresh.db'
    monkeypatch.setattr(database,'DB_PATH',str(path))
    monkeypatch.setattr(database,'DEFAULT_ADMIN_PASSWORD','secret123')
    database.init_db()
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT username,is_admin FROM users").fetchone()==('admin',1)
        assert c.execute("SELECT COUNT(*) FROM settings WHERE user_id IS NOT NULL").fetchone()[0]==1
        assert 'user_id' in {r[1] for r in c.execute('PRAGMA table_info(tenants)')}


def test_v01_data_is_migrated_to_admin(tmp_path, monkeypatch):
    path=tmp_path/'old.db'
    with sqlite3.connect(path) as c:
        c.executescript('''
        CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK(id=1), landlord_name TEXT, landlord_address TEXT, landlord_email TEXT, landlord_phone TEXT, iban TEXT);
        INSERT INTO settings VALUES(1,'Altvermieter','Adresse','mail@test.de','1','DE00');
        CREATE TABLE tenants (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, address TEXT, rental_object TEXT, apartment_area REAL DEFAULT 0, building_area REAL DEFAULT 0, persons REAL DEFAULT 1, building_persons REAL DEFAULT 1, units REAL DEFAULT 1, start_date TEXT, end_date TEXT, active INTEGER DEFAULT 1);
        INSERT INTO tenants(name) VALUES('Bestandsmieter');
        CREATE TABLE statements (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL, advance_payments REAL DEFAULT 0, status TEXT DEFAULT 'Entwurf', notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE costs (id INTEGER PRIMARY KEY AUTOINCREMENT, statement_id INTEGER NOT NULL, title TEXT NOT NULL, total_cost REAL NOT NULL, allocation_key TEXT NOT NULL, tenant_value REAL DEFAULT 0, total_value REAL DEFAULT 0, direct_amount REAL DEFAULT 0, tenant_share REAL DEFAULT 0, document_no TEXT, notes TEXT);
        ''')
    monkeypatch.setattr(database,'DB_PATH',str(path))
    database.init_db()
    with sqlite3.connect(path) as c:
        admin_id=c.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
        assert c.execute("SELECT user_id FROM tenants WHERE name='Bestandsmieter'").fetchone()[0]==admin_id
        assert c.execute("SELECT landlord_name FROM settings WHERE user_id=?",(admin_id,)).fetchone()[0]=='Altvermieter'
