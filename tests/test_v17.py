import sqlite3
from app.meter_analysis import period_consumption, yearly_consumption, chart_points

def test_period_consumption_traceable():
    r=[{'id':1,'reading_date':'2025-12-31','value':100.0},{'id':2,'reading_date':'2026-12-31','value':155.5}]
    out=period_consumption(r,'2026-01-01','2026-12-31')
    assert out['start_id']==1 and out['end_id']==2
    assert out['consumption']==55.5

def test_period_consumption_warns_negative():
    r=[{'id':1,'reading_date':'2026-01-01','value':200},{'id':2,'reading_date':'2026-12-31','value':10}]
    assert period_consumption(r,'2026-01-01','2026-12-31')['warning']

def test_yearly_consumption_and_chart():
    r=[{'id':1,'reading_date':'2025-01-01','value':10},{'id':2,'reading_date':'2025-12-31','value':20},{'id':3,'reading_date':'2026-12-31','value':35}]
    assert yearly_consumption(r)==[{'year':2025,'consumption':10.0},{'year':2026,'consumption':15.0}]
    assert chart_points(r)['points']

def test_cost_meter_migration(tmp_path, monkeypatch):
    import app.database as d
    monkeypatch.setattr(d,'DB_PATH',str(tmp_path/'db.sqlite'))
    d.init_db()
    with sqlite3.connect(d.DB_PATH) as c:
        cols={x[1] for x in c.execute('pragma table_info(costs)')}
    assert {'meter_id','meter_reading_start_id','meter_reading_end_id','meter_consumption','meter_unit'} <= cols
