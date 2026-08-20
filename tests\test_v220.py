from app.payment_csv import parse_amount, parse_date, match_tenant, parse_bank_csv

def test_amount_and_date():
    assert parse_amount("1.234,56 €") == 1234.56
    assert parse_date("20.08.2026") == "2026-08-20"

def test_tenant_match():
    tenants=[{"id":1,"name":"Max Mustermann"},{"id":2,"name":"Erika Beispiel"}]
    tid,msg=match_tenant(tenants,"Max Mustermann","Miete August")
    assert tid == 1

def test_bank_csv_parse():
    csv_data=("Buchungstag;Betrag;Verwendungszweck;Zahlungspflichtiger\n"
              "01.08.2026;750,00;Miete August;Max Mustermann\n"
              "02.08.2026;-25,00;Gebühr;Bank\n").encode("utf-8")
    out=parse_bank_csv(csv_data,[{"id":1,"name":"Max Mustermann"}])
    assert len(out["rows"]) == 1
    assert out["rows"][0]["tenant_id"] == 1
    assert out["rows"][0]["amount"] == 750.0
    assert len(out["skipped"]) == 1
