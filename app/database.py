import os, sqlite3
from contextlib import closing, contextmanager
from .auth import hash_password

DB_PATH=os.getenv('NEBENKOSTEN_DB','/var/lib/nebenkostenabrechnung/nebenkosten.db')
DEFAULT_ADMIN_PASSWORD=os.getenv('NEBENKOSTEN_ADMIN_PASSWORD','admin')

def _columns(c, table):
    return {r[1] for r in c.execute(f'PRAGMA table_info({table})').fetchall()}

def init_db():
    directory=os.path.dirname(DB_PATH)
    if directory: os.makedirs(directory, exist_ok=True)
    # sqlite3.Connection.__exit__ commits or rolls back but does not close the
    # connection. Explicit closing prevents locked database files, notably on
    # Windows and during backup/restore tests.
    with closing(sqlite3.connect(DB_PATH)) as c:
        c.execute('PRAGMA foreign_keys=OFF')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'manager', is_admin INTEGER NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE,
          landlord_name TEXT, landlord_address TEXT, landlord_email TEXT, landlord_phone TEXT, iban TEXT,
          ai_provider TEXT DEFAULT 'none', ai_model TEXT, ai_base_url TEXT, ai_api_key TEXT,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS properties (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
          name TEXT NOT NULL, address TEXT, notes TEXT, active INTEGER DEFAULT 1,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS apartments (
          id INTEGER PRIMARY KEY AUTOINCREMENT, property_id INTEGER NOT NULL,
          name TEXT NOT NULL, area REAL DEFAULT 0, building_area REAL DEFAULT 0,
          persons_total REAL DEFAULT 1, units_total REAL DEFAULT 1, active INTEGER DEFAULT 1,
          FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS tenants (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, apartment_id INTEGER,
          name TEXT NOT NULL, address TEXT, rental_object TEXT,
          apartment_area REAL DEFAULT 0, building_area REAL DEFAULT 0,
          persons REAL DEFAULT 1, building_persons REAL DEFAULT 1, units REAL DEFAULT 1,
          start_date TEXT, end_date TEXT, monthly_cold_rent REAL DEFAULT 0, monthly_operating_advance REAL DEFAULT 0, active INTEGER DEFAULT 1,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(apartment_id) REFERENCES apartments(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS statements (
          id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER NOT NULL, period_start TEXT NOT NULL,
          period_end TEXT NOT NULL, advance_payments REAL DEFAULT 0, status TEXT DEFAULT 'Entwurf',
          notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS costs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, statement_id INTEGER NOT NULL, title TEXT NOT NULL,
          total_cost REAL NOT NULL, allocation_key TEXT NOT NULL, tenant_value REAL DEFAULT 0,
          total_value REAL DEFAULT 0, direct_amount REAL DEFAULT 0, tenant_share REAL DEFAULT 0,
          document_no TEXT, notes TEXT,
          FOREIGN KEY(statement_id) REFERENCES statements(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS documents (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, tenant_id INTEGER,
          title TEXT NOT NULL, category TEXT DEFAULT 'Sonstiges', filename TEXT, stored_name TEXT, content_type TEXT, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS meters (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, tenant_id INTEGER, name TEXT NOT NULL, meter_type TEXT DEFAULT 'Sonstiges', meter_number TEXT, unit TEXT DEFAULT '', active INTEGER DEFAULT 1, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS meter_readings (
          id INTEGER PRIMARY KEY AUTOINCREMENT, meter_id INTEGER NOT NULL, reading_date TEXT NOT NULL, value REAL NOT NULL, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(meter_id) REFERENCES meters(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS tax_entries (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          property_id INTEGER NOT NULL,
          tax_year INTEGER NOT NULL,
          entry_date TEXT,
          entry_type TEXT NOT NULL DEFAULT 'expense',
          category TEXT NOT NULL,
          description TEXT,
          amount REAL NOT NULL DEFAULT 0,
          tax_treatment TEXT DEFAULT 'review',
          notes TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS rent_payments (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          tenant_id INTEGER NOT NULL,
          payment_date TEXT NOT NULL,
          amount REAL NOT NULL,
          payment_type TEXT DEFAULT 'rent',
          reference TEXT,
          notes TEXT,
          tax_entry_id INTEGER,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
          FOREIGN KEY(tax_entry_id) REFERENCES tax_entries(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS tax_year_closures (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          tax_year INTEGER NOT NULL,
          status TEXT DEFAULT 'offen',
          notes TEXT,
          closed_at TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id,tax_year),
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER,
          action TEXT NOT NULL,
          path TEXT,
          method TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS received_statements (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, tenant_id INTEGER,
          original_name TEXT NOT NULL, stored_name TEXT NOT NULL, content_type TEXT,
          extraction_method TEXT, extracted_text TEXT, parsed_json TEXT, status TEXT DEFAULT 'Zu prüfen',
          notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(tenant_id) REFERENCES tenants(id) ON DELETE SET NULL
        );
        ''')
        if 'import_hash' not in _columns(c,'rent_payments'):
            c.execute("ALTER TABLE rent_payments ADD COLUMN import_hash TEXT")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_rent_payments_import_hash ON rent_payments(user_id,import_hash) WHERE import_hash IS NOT NULL")
        if 'monthly_operating_advance' not in _columns(c,'tenants'):
            c.execute("ALTER TABLE tenants ADD COLUMN monthly_operating_advance REAL DEFAULT 0")
        for col, ddl in {
            'rent_part': 'REAL DEFAULT 0',
            'operating_part': 'REAL DEFAULT 0',
            'other_part': 'REAL DEFAULT 0',
            'allocation_month': 'TEXT',
        }.items():
            if col not in _columns(c,'rent_payments'):
                c.execute(f'ALTER TABLE rent_payments ADD COLUMN {col} {ddl}')
        if 'monthly_cold_rent' not in _columns(c,'tenants'):
            c.execute("ALTER TABLE tenants ADD COLUMN monthly_cold_rent REAL DEFAULT 0")
        for col, ddl in {
            'source_type': 'TEXT',
            'source_id': 'INTEGER',
        }.items():
            if col not in _columns(c,'tax_entries'):
                c.execute(f'ALTER TABLE tax_entries ADD COLUMN {col} {ddl}')
        if 'role' not in _columns(c,'users'):
            c.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'manager'")

        for col, ddl in {
            'meter_id': 'INTEGER',
            'meter_reading_start_id': 'INTEGER',
            'meter_reading_end_id': 'INTEGER',
            'meter_consumption': 'REAL',
            'meter_unit': 'TEXT',
        }.items():
            if col not in _columns(c,'costs'):
                c.execute(f'ALTER TABLE costs ADD COLUMN {col} {ddl}')

        for col, ddl in {
            'stored_name': 'TEXT',
            'content_type': 'TEXT',
            'notes': 'TEXT',
            'property_id': 'INTEGER',
            'tax_year': 'INTEGER',
            'tax_entry_id': 'INTEGER',
            'paperless_task_id': 'TEXT',
            'paperless_document_id': 'INTEGER',
            'paperless_status': 'TEXT',
            'receipt_ai_json': 'TEXT',
            'review_status': "TEXT DEFAULT 'neu'",
        }.items():
            if col not in _columns(c,'documents'):
                c.execute(f'ALTER TABLE documents ADD COLUMN {col} {ddl}')

        if 'user_id' not in _columns(c,'tenants'):
            c.execute('ALTER TABLE tenants ADD COLUMN user_id INTEGER')
        if 'apartment_id' not in _columns(c,'tenants'):
            c.execute('ALTER TABLE tenants ADD COLUMN apartment_id INTEGER')
        if 'user_id' not in _columns(c,'settings'):
            # Version 0.1 hatte genau eine Einstellungszeile ohne Benutzerbezug.
            legacy=c.execute('SELECT landlord_name,landlord_address,landlord_email,landlord_phone,iban FROM settings LIMIT 1').fetchone()
            c.execute('ALTER TABLE settings RENAME TO settings_legacy')
            c.execute('''CREATE TABLE settings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE,
              landlord_name TEXT, landlord_address TEXT, landlord_email TEXT, landlord_phone TEXT, iban TEXT)''')
        else:
            legacy=None
        for col, ddl in {
            'ai_provider': "TEXT DEFAULT 'none'",
            'ai_model': 'TEXT',
            'ai_base_url': 'TEXT',
            'ai_api_key': 'TEXT',
            'ai_referer': 'TEXT',
            'ai_app_title': 'TEXT',
            'smtp_host': 'TEXT',
            'smtp_port': 'INTEGER DEFAULT 587',
            'smtp_user': 'TEXT',
            'smtp_password': 'TEXT',
            'smtp_from': 'TEXT',
            'smtp_security': "TEXT DEFAULT 'starttls'",
            'paperless_enabled': 'INTEGER DEFAULT 0',
            'paperless_url': 'TEXT',
            'paperless_token': 'TEXT',
            'paperless_auto_upload': 'INTEGER DEFAULT 0',
            'paperless_default_tags': 'TEXT',
        }.items():
            if col not in _columns(c,'settings'):
                c.execute(f'ALTER TABLE settings ADD COLUMN {col} {ddl}')
        admin=c.execute('SELECT id FROM users ORDER BY id LIMIT 1').fetchone()
        if not admin:
            cur=c.execute('INSERT INTO users(username,display_name,password_hash,role,is_admin) VALUES(?,?,?,?,1)',('admin','Administrator',hash_password(DEFAULT_ADMIN_PASSWORD),'admin'))
            admin_id=cur.lastrowid
        else:
            admin_id=admin[0]
        c.execute('UPDATE tenants SET user_id=? WHERE user_id IS NULL',(admin_id,))
        for uid, in c.execute('SELECT id FROM users').fetchall():
            c.execute('INSERT OR IGNORE INTO settings(user_id,landlord_name,landlord_address,landlord_email,landlord_phone,iban) VALUES(?,?,?,?,?,?)',(uid,'','','','',''))
        if legacy:
            c.execute('UPDATE settings SET landlord_name=?,landlord_address=?,landlord_email=?,landlord_phone=?,iban=? WHERE user_id=?',(*legacy,admin_id))
            c.execute('DROP TABLE IF EXISTS settings_legacy')
        from .secret_store import migrate_plaintext
        migrate_plaintext(c)
                # Bestehende Mieter ohne Wohnung in ein automatisch erzeugtes Objekt migrieren.
        for t in c.execute('SELECT * FROM tenants WHERE apartment_id IS NULL').fetchall():
            uid=t[1] or admin_id
            prop_name=(t[4] or 'Bestandsobjekt').strip() if len(t)>4 else 'Bestandsobjekt'
            address=(t[3] or '').strip()
            prop=c.execute('SELECT id FROM properties WHERE user_id=? AND name=? AND address=?',(uid,prop_name,address)).fetchone()
            if not prop:
                pcur=c.execute('INSERT INTO properties(user_id,name,address,notes) VALUES(?,?,?,?)',(uid,prop_name,address,'Automatisch aus Version 0.2 migriert'))
                pid=pcur.lastrowid
            else: pid=prop[0]
            acur=c.execute('INSERT INTO apartments(property_id,name,area,building_area,persons_total,units_total) VALUES(?,?,?,?,?,?)',(pid,'Wohnung',t[5] or 0,t[6] or 0,t[8] or 1,t[9] or 1))
            c.execute('UPDATE tenants SET apartment_id=? WHERE id=?',(acur.lastrowid,t[0]))
        c.execute('PRAGMA foreign_keys=ON'); c.commit()

@contextmanager
def db():
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try: yield con; con.commit()
    finally: con.close()
