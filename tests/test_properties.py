import os, tempfile, importlib

def test_property_schema():
    fd,path=tempfile.mkstemp(); os.close(fd); os.unlink(path)
    os.environ['NEBENKOSTEN_DB']=path
    import app.database as database
    importlib.reload(database); database.init_db()
    with database.db() as c:
        uid=c.execute('select id from users where username="admin"').fetchone()[0]
        pid=c.execute('insert into properties(user_id,name) values(?,?)',(uid,'Haus A')).lastrowid
        aid=c.execute('insert into apartments(property_id,name,area) values(?,?,?)',(pid,'EG',80)).lastrowid
        c.execute('insert into tenants(user_id,apartment_id,name) values(?,?,?)',(uid,aid,'Mieter A'))
        assert c.execute('select count(*) from tenants where apartment_id=?',(aid,)).fetchone()[0] == 1
    os.unlink(path)

def test_documents_schema_has_storage_columns():
    import tempfile, importlib
    fd,path=tempfile.mkstemp(); os.close(fd); os.unlink(path)
    os.environ['NEBENKOSTEN_DB']=path
    import app.database as database
    importlib.reload(database); database.init_db()
    with database.db() as c:
        cols={r[1] for r in c.execute('pragma table_info(documents)').fetchall()}
        assert {'stored_name','content_type','notes'} <= cols
    os.unlink(path)
