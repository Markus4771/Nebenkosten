import os, tempfile, importlib
from pathlib import Path

def test_tax_entries_schema(monkeypatch):
    dbfile=tempfile.NamedTemporaryFile(suffix=".db",delete=False).name
    monkeypatch.setenv("NEBENKOSTEN_DB",dbfile)
    import app.database as database
    database.DB_PATH=Path(dbfile)
    database.init_db()
    with database.db() as c:
        cols={r[1] for r in c.execute("PRAGMA table_info(tax_entries)").fetchall()}
    assert {"user_id","property_id","tax_year","entry_type","category","amount","tax_treatment"} <= cols
