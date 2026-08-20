import os, tempfile
from app import database

def test_v18_settings_columns():
    old=database.DB_PATH
    with tempfile.TemporaryDirectory() as td:
        database.DB_PATH=td+'/db.sqlite'
        database.init_db()
        with database.db() as c:
            cols={x[1] for x in c.execute('PRAGMA table_info(settings)').fetchall()}
            assert {'ai_referer','ai_app_title'} <= cols
    database.DB_PATH=old
