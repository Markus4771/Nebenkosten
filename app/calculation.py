from datetime import date

def calc_share(total_cost, key, tenant_value=0, total_value=0, direct_amount=0):
    total_cost=float(total_cost or 0); tenant_value=float(tenant_value or 0); total_value=float(total_value or 0); direct_amount=float(direct_amount or 0)
    if key=='direct': return round(direct_amount,2)
    if key=='percent': return round(total_cost*tenant_value/100,2)
    if key in {'area','persons','consumption','units'}:
        return round(total_cost*tenant_value/total_value,2) if total_value else 0.0
    return 0.0

def days_inclusive(start,end):
    return (date.fromisoformat(end)-date.fromisoformat(start)).days+1
