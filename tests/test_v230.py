from app.payment_allocation import allocate_month, allocate_individual_payments

def test_one_combined_payment():
    rows=[{"id":1,"payment_date":"2026-08-01","amount":930}]
    s=allocate_month(rows,750,180)
    assert s["rent"] == 750
    assert s["operating"] == 180
    assert s["difference"] == 0
    assert s["status"] == "vollständig bezahlt"

def test_two_separate_payments():
    rows=[{"id":1,"payment_date":"2026-08-01","amount":750},{"id":2,"payment_date":"2026-08-03","amount":180}]
    s=allocate_month(rows,750,180)
    assert s["total_paid"] == 930
    assert s["rent"] == 750
    assert s["operating"] == 180

def test_partial_payments_are_combined():
    rows=[{"id":1,"payment_date":"2026-08-01","amount":500},{"id":2,"payment_date":"2026-08-05","amount":250},{"id":3,"payment_date":"2026-08-06","amount":180}]
    a=allocate_individual_payments(rows,750,180)
    assert a[0]["rent_part"] == 500
    assert a[1]["rent_part"] == 250
    assert a[2]["operating_part"] == 180

def test_under_and_overpayment():
    assert allocate_month([{"amount":900}],750,180)["status"] == "Unterzahlung"
    assert allocate_month([{"amount":950}],750,180)["status"] == "Überzahlung"

def test_tolerance():
    assert allocate_month([{"amount":929.5}],750,180,tolerance=1)["status"] == "vollständig bezahlt"
