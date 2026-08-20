from app.tax_tools import suggest_tax_category, annual_rent_schedule

def test_tax_category_suggestions():
    assert suggest_tax_category("Grundsteuer 2026") == "property_tax"
    assert suggest_tax_category("Wohngebäudeversicherung") == "insurance"
    assert suggest_tax_category("Heizungsreparatur") == "repairs"
    assert suggest_tax_category("Einzahlung Erhaltungsrücklage") == "reserve_contribution"

def test_annual_rent_schedule_partial_year():
    plan=annual_rent_schedule(750,"2026-03-15","2026-10-03",2026)
    assert [x["month"] for x in plan] == list(range(3,11))
    assert sum(x["amount"] for x in plan) == 6000

def test_new_schema(monkeypatch,tmp_path):
    import app.database as database
    database.DB_PATH=tmp_path/"db.sqlite"
    database.init_db()
    with database.db() as c:
        tcols={x[1] for x in c.execute("PRAGMA table_info(tenants)")}
        pcols={x[1] for x in c.execute("PRAGMA table_info(rent_payments)")}
        ecols={x[1] for x in c.execute("PRAGMA table_info(tax_entries)")}
    assert "monthly_cold_rent" in tcols
    assert {"tenant_id","payment_date","payment_type","tax_entry_id"} <= pcols
    assert {"source_type","source_id"} <= ecols
