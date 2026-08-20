from __future__ import annotations
import csv, io, zipfile, re
from collections import defaultdict

def tax_year_summary(conn,user_id:int,year:int,categories:dict):
    props=[dict(x) for x in conn.execute("SELECT * FROM properties WHERE user_id=? ORDER BY name",(user_id,)).fetchall()]
    result=[]; issues=[]
    for p in props:
        entries=[dict(x) for x in conn.execute("""SELECT * FROM tax_entries WHERE user_id=? AND property_id=? AND tax_year=? ORDER BY entry_date,id""",
                                               (user_id,p["id"],year)).fetchall()]
        tenants=[dict(x) for x in conn.execute("""SELECT t.* FROM tenants t JOIN apartments a ON a.id=t.apartment_id
                                                  WHERE t.user_id=? AND a.property_id=?""",(user_id,p["id"])).fetchall()]
        payments=[dict(x) for x in conn.execute("""SELECT rp.*,t.name tenant_name FROM rent_payments rp
                         JOIN tenants t ON t.id=rp.tenant_id JOIN apartments a ON a.id=t.apartment_id
                         WHERE rp.user_id=? AND a.property_id=? AND substr(rp.payment_date,1,4)=?""",(user_id,p["id"],str(year))).fetchall()]
        income=sum(float(e["amount"] or 0) for e in entries if e["entry_type"]=="income")
        expense=sum(float(e["amount"] or 0) for e in entries if e["entry_type"]=="expense")
        review=sum(1 for e in entries if e.get("tax_treatment")=="review")
        reserve=sum(float(e["amount"] or 0) for e in entries if e["category"]=="reserve_contribution")
        if review: issues.append(f"{p['name']}: {review} steuerliche Prüfposten")
        if reserve: issues.append(f"{p['name']}: Erhaltungsrücklage {reserve:.2f} EUR prüfen")
        if tenants and not payments: issues.append(f"{p['name']}: keine Mietzahlungen für {year} erfasst")
        if not entries: issues.append(f"{p['name']}: keine Steuerbuchungen für {year} erfasst")
        result.append({"property":p,"entries":entries,"payments":payments,"income":income,"expense":expense,
                       "review_count":review,"reserve":reserve,"tenant_count":len(tenants)})
    return {"year":year,"properties":result,"issues":issues,
            "income":sum(x["income"] for x in result),"expense":sum(x["expense"] for x in result)}

def csv_bytes(rows,headers):
    out=io.StringIO(); w=csv.writer(out,delimiter=";"); w.writerow(headers); w.writerows(rows)
    return ("\ufeff"+out.getvalue()).encode("utf-8")

def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]+","_",name).strip("_") or "Objekt"

def build_tax_package(settings,year,summary,overview_pdf,property_pdfs,categories,receipt_files=None):
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"Steuerberater-Uebersicht-{year}.pdf",overview_pdf.getvalue())
        income=[]; expenses=[]
        for x in summary["properties"]:
            pname=x["property"]["name"]
            for e in x["entries"]:
                row=[year,pname,e.get("entry_date") or "",categories.get(e["category"],e["category"]),e.get("description") or "",
                     f"{float(e['amount'] or 0):.2f}".replace(".",","),e.get("tax_treatment") or "",e.get("notes") or ""]
                (income if e["entry_type"]=="income" else expenses).append(row)
            pdf=property_pdfs.get(x["property"]["id"])
            if pdf: z.writestr(f"Anlage-V-Vorbereitung-{safe_name(pname)}-{year}.pdf",pdf.getvalue())
        headers=["Jahr","Objekt","Datum","Kategorie","Beschreibung","Betrag","Einordnung","Notiz"]
        z.writestr(f"Einnahmen-{year}.csv",csv_bytes(income,headers))
        z.writestr(f"Ausgaben-{year}.csv",csv_bytes(expenses,headers))
        checklist="STEUERJAHR-PRUEFLISTE\n\n"+("\n".join("- "+x for x in summary["issues"]) if summary["issues"] else "Keine automatischen Warnungen.")
        z.writestr(f"Pruefliste-{year}.txt",checklist.encode("utf-8"))
        for rec in (receipt_files or []):
            z.writestr(rec["archive_name"],rec["data"])
    out.seek(0); return out
