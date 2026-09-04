from __future__ import annotations
import re
from .tax_tools import suggest_tax_category

def suggest_receipt_metadata(text:str,filename:str=""):
    text=text or ""
    title=filename.rsplit(".",1)[0].replace("_"," ").replace("-"," ").strip() or "Beleg"
    amount=None
    candidates=[]
    amount_text=re.sub(r"\b[0-3]?\d[./][01]?\d[./](?:20)?\d{2}\b"," ",text)
    for m in re.finditer(r"(?<!\d)(\d{1,3}(?:\.\d{3})*,\d{2}|\d+[.,]\d{2})\s*(?:€|EUR)?",amount_text,re.I):
        raw=m.group(1).replace(".","").replace(",",".")
        try:candidates.append(float(raw))
        except:pass
    if candidates: amount=max(candidates)
    date=None
    m=re.search(r"\b([0-3]?\d[./][01]?\d[./](?:20)?\d{2})\b",text)
    if m: date=m.group(1)
    category=suggest_tax_category(title+" "+text[:4000])
    return {"title":title,"amount":amount,"date":date,"category":category}
