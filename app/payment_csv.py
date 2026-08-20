from __future__ import annotations
import csv, io, re, hashlib
from datetime import datetime
from typing import Any

DATE_KEYS=("buchungstag","buchungsdatum","datum","date","valutadatum","wertstellung")
AMOUNT_KEYS=("betrag","umsatz","amount","wert","buchungsbetrag")
REFERENCE_KEYS=("verwendungszweck","buchungstext","referenz","reference","beschreibung","text")
PAYER_KEYS=("name zahlungsbeteiligter","zahlungspflichtiger","auftraggeber","name","payer","gegenkonto name","empfänger/auftraggeber","beguenstigter/zahlungspflichtiger","begünstigter/zahlungspflichtiger")

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+"," ",(s or "").strip().lower()).strip()

def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig","utf-8","cp1252","latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8",errors="replace")

def _delimiter(text: str) -> str:
    lines=text.splitlines()
    header=lines[0] if lines else ""
    # Deutsche Bank-CSV nutzt sehr häufig ;, während Beträge Dezimal-Kommas enthalten.
    counts={d:header.count(d) for d in (";","\t","|",",")}
    best=max(counts,key=counts.get)
    if counts[best] > 0:
        return best
    sample="\n".join(lines[:10])
    try:
        return csv.Sniffer().sniff(sample,delimiters=";,\t|").delimiter
    except Exception:
        return ";"

def _find(headers: list[str], aliases: tuple[str,...]) -> str|None:
    normalized={_norm(h):h for h in headers}
    for alias in aliases:
        a=_norm(alias)
        if a in normalized:
            return normalized[a]
    for n,orig in normalized.items():
        if any(_norm(a) in n or n in _norm(a) for a in aliases):
            return orig
    return None

def parse_amount(value: str) -> float:
    s=(value or "").strip().replace("\xa0","").replace("€","").replace(" ","")
    if not s:
        raise ValueError("Betrag fehlt")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s=s.replace(".","").replace(",",".")
        else:
            s=s.replace(",","")
    elif "," in s:
        s=s.replace(".","").replace(",",".")
    return float(s)

def parse_date(value: str) -> str:
    s=(value or "").strip()
    for fmt in ("%d.%m.%Y","%d.%m.%y","%Y-%m-%d","%d/%m/%Y","%m/%d/%Y"):
        try:
            return datetime.strptime(s,fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Datum nicht erkannt: {s}")

def payment_fingerprint(payment_date:str, amount:float, payer:str, reference:str) -> str:
    raw=f"{payment_date}|{amount:.2f}|{_norm(payer)}|{_norm(reference)}".encode()
    return hashlib.sha256(raw).hexdigest()

def match_tenant(tenants: list[dict[str,Any]], payer: str, reference: str, explicit_name: str="") -> tuple[int|None,str]:
    hay=_norm(" ".join([explicit_name,payer,reference]))
    if not hay:
        return None,"keine Namensinformation"
    scored=[]
    for t in tenants:
        name=_norm(str(t.get("name") or ""))
        if not name:
            continue
        score=0
        if name in hay:
            score=100
        else:
            parts=[x for x in name.split() if len(x)>=3]
            hits=sum(1 for x in parts if x in hay)
            if parts:
                score=round(100*hits/len(parts))
        if score:
            scored.append((score,int(t["id"]),str(t["name"])))
    scored.sort(reverse=True)
    if not scored:
        return None,"kein Mieter erkannt"
    if len(scored)>1 and scored[0][0]==scored[1][0]:
        return None,"Zuordnung nicht eindeutig"
    if scored[0][0] < 60:
        return None,"Zuordnung zu unsicher"
    return scored[0][1],f"{scored[0][2]} ({scored[0][0]}%)"

def parse_bank_csv(data: bytes, tenants: list[dict[str,Any]], default_tenant_id:int=0, default_type:str="rent") -> dict[str,Any]:
    text=_decode(data)
    delim=_delimiter(text)
    reader=csv.DictReader(io.StringIO(text),delimiter=delim)
    headers=reader.fieldnames or []
    date_col=_find(headers,DATE_KEYS)
    amount_col=_find(headers,AMOUNT_KEYS)
    ref_col=_find(headers,REFERENCE_KEYS)
    payer_col=_find(headers,PAYER_KEYS)
    tenant_col=_find(headers,("mieter","mietername","tenant"))
    if not date_col or not amount_col:
        raise ValueError("CSV benötigt mindestens eine Datums- und eine Betragsspalte.")
    rows=[]
    skipped=[]
    for lineno,row in enumerate(reader,start=2):
        try:
            date=parse_date(row.get(date_col,""))
            amount=parse_amount(row.get(amount_col,""))
            if amount <= 0:
                skipped.append({"line":lineno,"reason":"kein positiver Zahlungseingang"})
                continue
            reference=(row.get(ref_col,"") if ref_col else "").strip()
            payer=(row.get(payer_col,"") if payer_col else "").strip()
            explicit=(row.get(tenant_col,"") if tenant_col else "").strip()
            if default_tenant_id:
                tenant_id=default_tenant_id
                match="manuell vorgegeben"
            else:
                tenant_id,match=match_tenant(tenants,payer,reference,explicit)
            if not tenant_id:
                skipped.append({"line":lineno,"reason":match,"payer":payer,"reference":reference,"amount":amount})
                continue
            ptype=default_type
            low=_norm(reference+" "+payer)
            if "nebenkosten" in low or "betriebskosten" in low:
                ptype="operating_advance"
            rows.append({
                "line":lineno,"tenant_id":tenant_id,"payment_date":date,"amount":round(amount,2),
                "payment_type":ptype,"reference":reference or payer,"payer":payer,"match":match,
                "fingerprint":payment_fingerprint(date,amount,payer,reference)
            })
        except Exception as exc:
            skipped.append({"line":lineno,"reason":str(exc)})
    return {"delimiter":delim,"headers":headers,"rows":rows,"skipped":skipped,
            "columns":{"date":date_col,"amount":amount_col,"reference":ref_col,"payer":payer_col,"tenant":tenant_col}}
