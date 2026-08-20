from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

def euro(v): return f"{float(v):,.2f} €".replace(',', 'X').replace('.', ',').replace('X','.')

def build_statement_pdf(settings,tenant,statement,costs):
    out=BytesIO(); doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm)
    s=getSampleStyleSheet(); story=[]
    story += [Paragraph('Nebenkostenabrechnung',s['Title']),Spacer(1,8)]
    story += [Paragraph(f"<b>Vermieter:</b> {settings['landlord_name'] or '-'}<br/>{settings['landlord_address'] or ''}",s['BodyText']),Spacer(1,6)]
    story += [Paragraph(f"<b>Mieter:</b> {tenant['name']}<br/>{tenant['address'] or ''}<br/><b>Mietobjekt:</b> {tenant['rental_object'] or '-'}",s['BodyText']),Spacer(1,8)]
    story += [Paragraph(f"Abrechnungszeitraum: {statement['period_start']} bis {statement['period_end']}",s['Heading2']),Spacer(1,6)]
    data=[['Kostenart','Gesamtkosten','Verteilung','Ihr Anteil']]
    labels={'area':'Wohnfläche','persons':'Personen','consumption':'Verbrauch','units':'Einheiten','percent':'Prozent','direct':'Direktbetrag'}
    total=0
    for c in costs:
        total+=c['tenant_share']; data.append([c['title'],euro(c['total_cost']),labels.get(c['allocation_key'],c['allocation_key']),euro(c['tenant_share'])])
    table=Table(data,colWidths=[65*mm,35*mm,35*mm,35*mm],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),0.4,colors.grey),('ALIGN',(1,1),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'TOP'),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5)]))
    story += [table,Spacer(1,10)]
    advance=float(statement['advance_payments']); balance=round(total-advance,2)
    result=[['Summe umlagefähige Kosten',euro(total)],['Geleistete Vorauszahlungen',euro(advance)],['Nachzahlung' if balance>=0 else 'Guthaben',euro(abs(balance))]]
    rt=Table(result,colWidths=[100*mm,50*mm]); rt.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.4,colors.grey),('ALIGN',(1,0),(1,-1),'RIGHT'),('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('BACKGROUND',(0,-1),(-1,-1),colors.whitesmoke)]))
    story += [rt,Spacer(1,10)]
    if statement['notes']: story += [Paragraph(f"<b>Hinweise:</b> {statement['notes']}",s['BodyText'])]
    if settings['iban']: story += [Spacer(1,8),Paragraph(f"Bankverbindung: {settings['iban']}",s['BodyText'])]
    doc.build(story); out.seek(0); return out


def build_tax_advisor_pdf(settings, year, properties):
    """Jahresübersicht für die steuerliche Bearbeitung. Keine Steuererklärung."""
    out=BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=15*mm,bottomMargin=15*mm)
    st=getSampleStyleSheet()
    story=[
        Paragraph(f'Vermietungsübersicht {year} – Unterlage für den Steuerberater',st['Title']),
        Spacer(1,6),
        Paragraph(f"<b>Vermieter:</b> {settings['landlord_name'] or '-'}<br/>{settings['landlord_address'] or ''}",st['BodyText']),
        Spacer(1,8),
        Paragraph('Diese Übersicht fasst die im Programm erfassten Daten zusammen. Sie ersetzt weder die Anlage V noch die steuerliche Prüfung.',st['BodyText']),
        Spacer(1,10)
    ]
    grand_statement_advance=0.0
    grand_allocated=0.0
    grand_income=0.0
    grand_expense=0.0
    treatment_labels={'review':'Prüfen','potentially_deductible':'potenziell abziehbar','not_deductible':'nicht abziehbar'}
    category_labels={
        'rent':'Kaltmiete / Mietzins','other_income':'Sonstige Mieteinnahmen','operating_advance':'Nebenkosten-Vorauszahlungen',
        'repairs':'Reparaturen / Erhaltungsaufwand','property_tax':'Grundsteuer / öffentliche Abgaben',
        'insurance':'Gebäude-/Haftpflichtversicherung','interest':'Darlehenszinsen','afa':'AfA / Abschreibung',
        'management':'Verwaltungskosten','nonalloc_operating':'Nicht umlagefähige Betriebskosten',
        'reserve_contribution':'Erhaltungsrücklage (Einzahlung)','other_expense':'Sonstige Aufwendungen'
    }
    for prop in properties:
        story += [Paragraph(f"Objekt: {prop['name']}",st['Heading2'])]
        if prop.get('address'):
            story += [Paragraph(prop['address'],st['BodyText'])]
        rows=[['Mieter','Zeitraum','Vorauszahlungen','umgelegte Kosten','Saldo']]
        for x in prop.get('statements',[]):
            rows.append([
                x['tenant_name'],f"{x['period_start']} – {x['period_end']}",
                euro(x['advance_payments']),euro(x['allocated_costs']),euro(x['balance'])
            ])
            grand_statement_advance += x['advance_payments']
            grand_allocated += x['allocated_costs']
        if len(rows)>1:
            t=Table(rows,colWidths=[42*mm,43*mm,34*mm,34*mm,28*mm],repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),0.35,colors.grey),
                ('FONTSIZE',(0,0),(-1,-1),8),('ALIGN',(2,1),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'TOP')
            ]))
            story += [t,Spacer(1,7)]
        cats=prop.get('cost_categories',[])
        if cats:
            cr=[['Nebenkostenart','Gesamtkosten','Mieteranteil']]
            for c in cats:
                cr.append([c['title'],euro(c['total_cost']),euro(c['tenant_share'])])
            t=Table(cr,colWidths=[85*mm,45*mm,45*mm],repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),('GRID',(0,0),(-1,-1),0.3,colors.grey),
                ('FONTSIZE',(0,0),(-1,-1),8),('ALIGN',(1,1),(-1,-1),'RIGHT')
            ]))
            story += [t,Spacer(1,7)]
        entries=prop.get('tax_entries',[])
        if entries:
            er=[['Datum','Typ','Kategorie / Beschreibung','Betrag','Einordnung']]
            prop_income=prop_expense=0.0
            for e in entries:
                typ='Einnahme' if e['entry_type']=='income' else 'Aufwand'
                if e['entry_type']=='income':
                    prop_income+=float(e['amount'] or 0)
                    grand_income+=float(e['amount'] or 0)
                else:
                    prop_expense+=float(e['amount'] or 0)
                    grand_expense+=float(e['amount'] or 0)
                label=category_labels.get(e['category'],e['category'])
                if e.get('description'):
                    label += ' – '+e['description']
                er.append([e.get('entry_date') or '',typ,label,euro(e['amount']),treatment_labels.get(e.get('tax_treatment'),'Prüfen')])
            t=Table(er,colWidths=[22*mm,21*mm,78*mm,28*mm,33*mm],repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),0.3,colors.grey),
                ('FONTSIZE',(0,0),(-1,-1),7.5),('ALIGN',(3,1),(3,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'TOP')
            ]))
            story += [Paragraph('Steuerliche Jahresdaten',st['Heading3']),t,
                      Paragraph(f"Einnahmen erfasst: {euro(prop_income)} · Aufwendungen erfasst: {euro(prop_expense)}",st['BodyText']),Spacer(1,10)]
        else:
            story += [Paragraph('Keine zusätzlichen steuerlichen Jahresdaten für dieses Objekt erfasst.',st['BodyText']),Spacer(1,8)]
    summary=[
        ['Gesamtübersicht','Betrag'],
        ['Nebenkosten-Vorauszahlungen aus Abrechnungen',euro(grand_statement_advance)],
        ['auf Mieter entfallende Nebenkosten',euro(grand_allocated)],
        ['separat erfasste Einnahmen',euro(grand_income)],
        ['separat erfasste Aufwendungen',euro(grand_expense)],
    ]
    t=Table(summary,colWidths=[115*mm,55*mm])
    t.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.4,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.lightgrey),
        ('ALIGN',(1,1),(-1,-1),'RIGHT'),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold')
    ]))
    story += [t,Spacer(1,8)]
    story += [
        Paragraph('<b>Wichtiger Prüfhilfe-Hinweis:</b> Einzahlungen in eine Erhaltungsrücklage sind hier nur als eigener Prüfposten ausgewiesen. Das Programm behandelt sie nicht automatisch als Werbungskosten.',st['BodyText']),
        Spacer(1,6),
        Paragraph('<b>Weitere Unterlagen:</b> Mietverträge, Zahlungsnachweise, Hausverwaltungsabrechnungen, Rechnungen zu Reparaturen/Erhaltungsmaßnahmen, Darlehensunterlagen, AfA-/Anschaffungsunterlagen und sonstige Belege bereithalten.',st['BodyText'])
    ]
    doc.build(story)
    out.seek(0)
    return out
