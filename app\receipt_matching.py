from __future__ import annotations
import re

def _norm(s):
    return re.sub(r"[^a-z0-9äöüß]+"," ",str(s or "").lower()).strip()

def match_property(properties, suggestion, text=""):
    hint=_norm((suggestion or {}).get("property_hint"))
    hay=_norm(" ".join([hint,text[:5000]]))
    scored=[]
    for p in properties:
        name=_norm(p.get("name"))
        address=_norm(p.get("address"))
        score=0
        if name and name in hay: score+=80
        if address and address in hay: score+=100
        for token in [x for x in (name+" "+address).split() if len(x)>=5]:
            if token in hay: score+=5
        if score: scored.append((score,p))
    scored.sort(key=lambda x:x[0],reverse=True)
    return scored[0][1] if scored and (len(scored)==1 or scored[0][0]>scored[1][0]) else None

def match_tax_entry(entries,suggestion):
    cat=(suggestion or {}).get("category")
    amount=(suggestion or {}).get("amount")
    desc=_norm((suggestion or {}).get("description"))
    scored=[]
    for e in entries:
        score=0
        if cat and e.get("category")==cat: score+=50
        try:
            if amount is not None:
                diff=abs(float(e.get("amount") or 0)-float(amount))
                if diff<0.01: score+=100
                elif diff<=1: score+=70
                elif diff<=5: score+=30
        except Exception: pass
        ed=_norm(e.get("description"))
        if desc and ed and (desc in ed or ed in desc): score+=30
        if score: scored.append((score,e))
    scored.sort(key=lambda x:x[0],reverse=True)
    if not scored: return None
    if len(scored)>1 and scored[0][0]==scored[1][0]: return None
    return scored[0][1] if scored[0][0]>=50 else None
