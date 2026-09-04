import json
import re
import shutil
from pathlib import Path
from typing import Any

AMOUNT_RE = re.compile(r"(?<!\d)(-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+\.\d{2})(?:\s*€)?")
DATE_RANGE_RE = re.compile(r"(\d{1,2}\.\d{1,2}\.\d{2,4})\s*(?:bis|[-–])\s*(\d{1,2}\.\d{1,2}\.\d{2,4})", re.I)
ALLOCATION_RE = re.compile(r"(?:Wohnfläche|m²|qm|Person(?:en)?|Verbrauch|Einheit(?:en)?|MEA|Miteigentumsanteil|Prozent|%)", re.I)

COST_KEYWORDS = {
    'Heizkosten': ['heizkosten', 'heizung'],
    'Warmwasser': ['warmwasser'],
    'Kaltwasser': ['kaltwasser'],
    'Wasser/Abwasser': ['wasser', 'abwasser'],
    'Müll': ['müll', 'abfall'],
    'Grundsteuer': ['grundsteuer'],
    'Hausreinigung': ['hausreinigung', 'gebäudereinigung'],
    'Versicherung': ['versicherung'],
    'Gartenpflege': ['gartenpflege'],
    'Allgemeinstrom': ['allgemeinstrom', 'beleuchtung', 'strom'],
    'Aufzug': ['aufzug'],
    'Schornsteinfeger': ['schornstein'],
    'Hausmeister': ['hausmeister'],
    'Straßenreinigung': ['straßenreinigung', 'strassenreinigung'],
}


def _money(value: str) -> float:
    value = value.strip().replace('€', '').replace(' ', '')
    if ',' in value:
        value = value.replace('.', '').replace(',', '.')
    return round(float(value), 2)


def extract_text(path: Path, content_type: str = '') -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        text = '\n'.join((page.extract_text() or '') for page in reader.pages).strip()
        if text:
            return text, 'PDF-Text'
        # Optionaler Fallback für reine Scan-PDFs, sofern pdftoppm+tesseract verfügbar sind.
        if shutil.which('pdftoppm') and shutil.which('tesseract'):
            import tempfile, subprocess
            import pytesseract
            from PIL import Image
            with tempfile.TemporaryDirectory() as tmp:
                prefix = str(Path(tmp) / 'page')
                subprocess.run(['pdftoppm', '-jpeg', '-r', '180', str(path), prefix], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                parts=[]
                for img in sorted(Path(tmp).glob('page-*.jpg')):
                    parts.append(pytesseract.image_to_string(Image.open(img), lang='deu'))
                return '\n'.join(parts).strip(), 'PDF-Scan + Tesseract OCR'
        return '', 'PDF ohne eingebetteten Text; OCR-Fallback nicht verfügbar'
    if suffix in {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}:
        if not shutil.which('tesseract'):
            return '', 'Tesseract ist nicht installiert'
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(path), lang='deu').strip(), 'Tesseract OCR'
    if suffix in {'.txt', '.csv'}:
        return path.read_text(encoding='utf-8', errors='replace'), 'Textdatei'
    raise ValueError('Nicht unterstütztes Dateiformat')


def _classify_cost(line: str) -> str | None:
    low=line.lower()
    # Spezifische Begriffe vor dem generischen "Wasser" prüfen.
    for title, words in COST_KEYWORDS.items():
        if any(word in low for word in words):
            return title
    return None


def _allocation_hint(line: str) -> str:
    m=ALLOCATION_RE.search(line)
    if not m:
        return ''
    value=m.group(0).lower()
    if 'fläche' in value or 'm²' in value or 'qm' in value: return 'Wohnfläche'
    if 'person' in value: return 'Personen'
    if 'verbrauch' in value: return 'Verbrauch'
    if 'einheit' in value: return 'Wohneinheiten'
    if 'mea' in value or 'miteigentum' in value: return 'Miteigentumsanteil'
    if '%' in value or 'prozent' in value: return 'Prozent'
    return m.group(0)


def parse_statement(text: str) -> dict[str, Any]:
    normalized = ' '.join(text.split())
    result: dict[str, Any] = {
        'analysis_version': '1.8', 'confidence': {}, 'warnings': [],
        'cost_items': [], 'checks': [], 'anomalies': []
    }
    period = DATE_RANGE_RE.search(normalized)
    if period:
        result['period_start'], result['period_end'] = period.group(1), period.group(2)
        result['confidence']['period'] = 0.94
    else:
        result['warnings'].append('Abrechnungszeitraum nicht eindeutig erkannt.')

    patterns = {
        'advance_payments': r'(?:Vorauszahlungen|geleistete Vorauszahlung(?:en)?|Abschlagszahlungen)\D{0,40}(' + AMOUNT_RE.pattern + r')',
        'balance': r'(?:Nachzahlung|Guthaben|Abrechnungssaldo|Saldo)\D{0,40}(' + AMOUNT_RE.pattern + r')',
        'total_cost': r'(?:Gesamtkosten|Summe Kosten|Gesamtbetrag|Gesamtsumme)\D{0,40}(' + AMOUNT_RE.pattern + r')',
        'tenant_total': r'(?:Ihr Anteil|Mieteranteil|Ihre Kosten|Anteil Mieter)\D{0,40}(' + AMOUNT_RE.pattern + r')',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, normalized, re.I)
        if match:
            raw = next((g for g in reversed(match.groups()) if g), None)
            if raw:
                try:
                    result[key] = _money(raw)
                    result['confidence'][key] = 0.84
                except ValueError:
                    pass

    for line in _candidate_lines(text):
        title=_classify_cost(line)
        if not title:
            continue
        values=[_money(v) for v in AMOUNT_RE.findall(line)]
        if not values:
            continue
        item={'title': title, 'amount': values[-1], 'source': line[:300], 'confidence': 0.76}
        if len(values) >= 2:
            item['total_amount']=values[-2]
            item['tenant_share']=values[-1]
            item['confidence']=0.82
        else:
            item['tenant_share']=values[-1]
        allocation=_allocation_hint(line)
        if allocation:
            item['allocation_key']=allocation
        result['cost_items'].append(item)

    unique=[]; seen=set()
    for item in result['cost_items']:
        key=(item['title'], item.get('total_amount'), item.get('tenant_share'))
        if key not in seen:
            seen.add(key); unique.append(item)
    result['cost_items']=unique

    if result['cost_items']:
        shares=round(sum(float(x.get('tenant_share', x.get('amount', 0))) for x in result['cost_items']),2)
        result['recognized_tenant_cost_sum']=shares
        if 'tenant_total' in result:
            diff=round(shares-result['tenant_total'],2)
            ok=abs(diff) <= 0.05
            result['checks'].append({'name':'Summe Kostenpositionen gegen Mieteranteil','ok':ok,'difference':diff})
            if not ok:
                result['anomalies'].append(f'Die erkannten Kostenpositionen weichen um {abs(diff):.2f} € vom angegebenen Mieteranteil ab.')
        if 'advance_payments' in result and 'balance' in result:
            # Guthaben/Saldo kann im Dokument ohne Vorzeichen stehen; daher beide Varianten prüfen.
            expected=round(shares-result['advance_payments'],2)
            candidates=[round(result['balance'],2),round(-result['balance'],2)]
            diff=min(abs(expected-x) for x in candidates)
            ok=diff <= 0.05
            result['checks'].append({'name':'Saldo gegen erkannte Kosten und Vorauszahlungen','ok':ok,'difference':round(diff,2),'expected':expected})
            if not ok:
                result['anomalies'].append('Der erkannte Saldo lässt sich aus Kosten und Vorauszahlungen nicht eindeutig nachrechnen.')
    else:
        result['warnings'].append('Keine Kostenpositionen sicher erkannt.')

    result['text_length']=len(text)
    result['overall_confidence']=round(sum(result['confidence'].values())/len(result['confidence']),2) if result['confidence'] else 0
    return result


def compare_statements(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return {'available': False, 'items': [], 'summary': 'Keine frühere Abrechnung für diesen Mieter vorhanden.'}
    prev={x.get('title'):float(x.get('tenant_share',x.get('amount',0)) or 0) for x in previous.get('cost_items',[])}
    cur={x.get('title'):float(x.get('tenant_share',x.get('amount',0)) or 0) for x in current.get('cost_items',[])}
    items=[]
    for title in sorted(set(prev)|set(cur)):
        old=round(prev.get(title,0),2); new=round(cur.get(title,0),2); diff=round(new-old,2)
        pct=None if old==0 else round(diff/old*100,1)
        severity='normal'
        if pct is not None and abs(pct)>=50: severity='hoch'
        elif pct is not None and abs(pct)>=20: severity='auffällig'
        elif old==0 and new>0: severity='neu'
        items.append({'title':title,'previous':old,'current':new,'difference':diff,'percent':pct,'severity':severity})
    return {'available': True, 'items': items, 'summary': f'{len(items)} Kostenarten verglichen.'}



def _candidate_lines(text: str) -> list[str]:
    """Rekonstruiert einfache mehrzeilige Tabellen aus OCR-/PDF-Text."""
    lines=[re.sub(r'\s+',' ',x).strip() for x in text.splitlines() if x.strip()]
    out=list(lines)
    for i,line in enumerate(lines):
        # Viele Hausverwaltungs-PDFs trennen Bezeichnung und Beträge in zwei Zeilen.
        if _classify_cost(line) and not AMOUNT_RE.search(line):
            for j in range(i+1,min(i+4,len(lines))):
                if AMOUNT_RE.search(lines[j]):
                    out.append(line+' '+lines[j]); break
        # OCR kann die Kostenart in der vorherigen Zeile und den Umlageschlüssel dazwischen liefern.
        if AMOUNT_RE.search(line) and i>0 and not _classify_cost(line):
            prefix=' '.join(lines[max(0,i-2):i])
            if _classify_cost(prefix): out.append(prefix+' '+line)
    return out


def build_analysis_report(data: dict[str, Any], comparison: dict[str, Any] | None = None) -> dict[str, Any]:
    findings=[]; recommendations=[]; score=100
    for check in data.get('checks',[]):
        if not check.get('ok'):
            score-=20; findings.append({'severity':'hoch','text':check.get('name','Rechnerische Prüfung fehlgeschlagen')})
    for text in data.get('anomalies',[]):
        score-=10; findings.append({'severity':'auffällig','text':text})
    for text in data.get('warnings',[]):
        score-=5; findings.append({'severity':'hinweis','text':text})
    if comparison and comparison.get('available'):
        for item in comparison.get('items',[]):
            if item.get('severity') in {'hoch','auffällig','neu'}:
                pct=item.get('percent')
                detail=f"{item['title']}: {item['difference']:+.2f} €"+(f" ({pct:+.1f} %)" if pct is not None else ' (neu)')
                findings.append({'severity':item['severity'],'text':detail})
    if any(x['severity']=='hoch' for x in findings): recommendations.append('Auffällige Positionen anhand der Originalabrechnung und Belege prüfen.')
    if data.get('tenant_total') is None: recommendations.append('Mieteranteil manuell prüfen oder per KI nacherkennen lassen.')
    if not data.get('cost_items'): recommendations.append('Kostenpositionen manuell erfassen oder OCR/KI erneut ausführen.')
    if not recommendations: recommendations.append('Keine wesentlichen rechnerischen Auffälligkeiten erkannt; Originalbelege trotzdem stichprobenartig prüfen.')
    return {'score':max(0,score),'findings':findings,'recommendations':recommendations,'status':'prüfen' if score<80 else 'plausibel'}


def build_history(current: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    rows=[]; titles=set()
    for d in documents:
        parsed=d.get('parsed',{})
        items={x.get('title'):float(x.get('tenant_share',x.get('amount',0)) or 0) for x in parsed.get('cost_items',[]) if x.get('title')}
        titles.update(items)
        rows.append({'id':d.get('id'),'name':d.get('name'),'period_start':parsed.get('period_start',''),'period_end':parsed.get('period_end',''),
                     'tenant_total':parsed.get('tenant_total',parsed.get('recognized_tenant_cost_sum')),'advance_payments':parsed.get('advance_payments'),'balance':parsed.get('balance'),'items':items})
    rows.sort(key=lambda x:(x.get('period_start') or '',x.get('id') or 0))
    return {'available':len(rows)>1,'rows':rows,'titles':sorted(titles)}

def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def recalculate_analysis(data: dict[str, Any]) -> dict[str, Any]:
    data=dict(data)
    data['analysis_version']='1.8'
    data.setdefault('warnings',[]); data.setdefault('confidence',{}); data.setdefault('cost_items',[])
    data['checks']=[]; data['anomalies']=[]
    if data['cost_items']:
        shares=round(sum(float(x.get('tenant_share',x.get('amount',0)) or 0) for x in data['cost_items']),2)
        data['recognized_tenant_cost_sum']=shares
        if data.get('tenant_total') is not None:
            diff=round(shares-float(data['tenant_total']),2); ok=abs(diff)<=0.05
            data['checks'].append({'name':'Summe Kostenpositionen gegen Mieteranteil','ok':ok,'difference':diff})
            if not ok: data['anomalies'].append(f'Die Kostenpositionen weichen um {abs(diff):.2f} € vom Mieteranteil ab.')
        if data.get('advance_payments') is not None and data.get('balance') is not None:
            expected=round(shares-float(data['advance_payments']),2)
            diff=min(abs(expected-float(data['balance'])),abs(expected+float(data['balance'])))
            ok=diff<=0.05
            data['checks'].append({'name':'Saldo gegen Kosten und Vorauszahlungen','ok':ok,'difference':round(diff,2),'expected':expected})
            if not ok: data['anomalies'].append('Der Saldo lässt sich aus Kosten und Vorauszahlungen nicht eindeutig nachrechnen.')
    return data


def merge_ai_analysis(base: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
    merged=dict(base)
    for key in ('period_start','period_end','total_cost','tenant_total','advance_payments','balance'):
        if ai.get(key) not in (None,''): merged[key]=ai[key]
    if ai.get('cost_items'):
        clean=[]
        for item in ai['cost_items']:
            if not isinstance(item,dict) or not item.get('title'): continue
            row={'title':str(item['title'])[:120],'confidence':0.9,'source':'KI-Provider'}
            for k in ('total_amount','tenant_share','amount'):
                if item.get(k) not in (None,''):
                    try: row[k]=round(float(item[k]),2)
                    except (ValueError,TypeError): pass
            if item.get('allocation_key'): row['allocation_key']=str(item['allocation_key'])[:80]
            clean.append(row)
        if clean: merged['cost_items']=clean
    if isinstance(ai.get('consumptions'),list):
        clean_consumptions=[]
        for item in ai['consumptions'][:50]:
            if not isinstance(item,dict) or item.get('value') in (None,''): continue
            try: value=round(float(item['value']),3)
            except (TypeError,ValueError): continue
            row={'type':str(item.get('type') or 'Verbrauch')[:80],'value':value,'unit':str(item.get('unit') or '')[:20]}
            for k in ('period_start','period_end','meter_number'):
                if item.get(k): row[k]=str(item[k])[:80]
            clean_consumptions.append(row)
        if clean_consumptions: merged['consumptions']=clean_consumptions
    for key in ('findings','recommendations'):
        if isinstance(ai.get(key),list): merged['ai_'+key]=[str(x)[:500] for x in ai[key]][:20]
    merged['ai_provider']=ai.get('ai_provider'); merged['ai_model']=ai.get('ai_model')
    merged['ai_analyzed']=True
    return recalculate_analysis(merged)
