from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Allocation:
    rent: float
    operating: float
    other: float
    status: str

def allocate_month(payments, cold_rent: float, operating_advance: float, tolerance: float = 1.0):
    """Verteilt alle positiven Zahlungen eines Monats auf Kaltmiete, NK und Rest."""
    cold=max(float(cold_rent or 0),0)
    op=max(float(operating_advance or 0),0)
    total=round(sum(max(float(p.get("amount",0) or 0),0) for p in payments),2)
    expected=round(cold+op,2)

    rent=min(total,cold)
    remaining=round(total-rent,2)
    operating=min(remaining,op)
    other=round(max(remaining-operating,0),2)

    diff=round(total-expected,2)
    if abs(diff) <= tolerance:
        status="vollständig bezahlt"
    elif diff < -tolerance:
        status="Unterzahlung"
    else:
        status="Überzahlung"
    return {
        "total_paid": total,
        "expected": expected,
        "rent": round(rent,2),
        "operating": round(operating,2),
        "other": other,
        "difference": diff,
        "status": status,
    }

def allocate_individual_payments(payments, cold_rent: float, operating_advance: float):
    """Ordnet chronologisch jede einzelne Zahlung dem Monats-Soll zu."""
    rent_left=max(float(cold_rent or 0),0)
    op_left=max(float(operating_advance or 0),0)
    out=[]
    for p in sorted(payments,key=lambda x:(x.get("payment_date",""),x.get("id",0))):
        amount=max(float(p.get("amount",0) or 0),0)
        rent=min(amount,rent_left)
        rent_left=round(rent_left-rent,2)
        rest=round(amount-rent,2)
        operating=min(rest,op_left)
        op_left=round(op_left-operating,2)
        other=round(rest-operating,2)
        out.append({**p,"rent_part":round(rent,2),"operating_part":round(operating,2),"other_part":other})
    return out
