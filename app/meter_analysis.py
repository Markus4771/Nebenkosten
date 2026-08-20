from __future__ import annotations
from datetime import date, datetime


def _d(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()


def period_consumption(readings, period_start, period_end):
    """Return traceable meter consumption for a statement period.

    Prefer readings on/before each period boundary. If no reading exists before the
    start, use the first reading inside the period. The end reading must not be
    earlier than the start reading. Result includes IDs/dates for auditability.
    """
    rows=[dict(r) for r in readings]
    rows.sort(key=lambda r: (_d(r['reading_date']), r.get('id', 0)))
    if not rows:
        return None
    start=_d(period_start); end=_d(period_end)
    before_start=[r for r in rows if _d(r['reading_date']) <= start]
    inside=[r for r in rows if start <= _d(r['reading_date']) <= end]
    before_end=[r for r in rows if _d(r['reading_date']) <= end]
    start_row=before_start[-1] if before_start else (inside[0] if inside else None)
    end_row=before_end[-1] if before_end else None
    if not start_row or not end_row or _d(end_row['reading_date']) < _d(start_row['reading_date']):
        return None
    consumption=round(float(end_row['value'])-float(start_row['value']),3)
    return {
        'start_id': start_row.get('id'), 'end_id': end_row.get('id'),
        'start_date': str(start_row['reading_date']), 'end_date': str(end_row['reading_date']),
        'start_value': float(start_row['value']), 'end_value': float(end_row['value']),
        'consumption': consumption,
        'complete': _d(start_row['reading_date']) <= start and _d(end_row['reading_date']) >= end,
        'warning': 'Zählerstand ist gefallen; Zählerwechsel oder Eingabefehler prüfen.' if consumption < 0 else None,
    }


def yearly_consumption(readings):
    """Aggregate positive consumption deltas by year of the later reading."""
    rows=[dict(r) for r in readings]
    rows.sort(key=lambda r: (_d(r['reading_date']), r.get('id',0)))
    totals={}
    prev=None
    for row in rows:
        if prev is not None:
            delta=float(row['value'])-float(prev['value'])
            if delta >= 0:
                year=_d(row['reading_date']).year
                totals[year]=round(totals.get(year,0)+delta,3)
        prev=row
    return [{'year':y,'consumption':totals[y]} for y in sorted(totals)]


def chart_points(readings, width=760, height=220, padding=28):
    """Create SVG-ready points without a JavaScript chart dependency."""
    rows=[dict(r) for r in readings]
    rows.sort(key=lambda r: (_d(r['reading_date']), r.get('id',0)))
    if not rows:
        return {'points':'','min':0,'max':0,'width':width,'height':height}
    vals=[float(r['value']) for r in rows]
    lo=min(vals); hi=max(vals); span=hi-lo or 1.0
    usable_w=max(1,width-2*padding); usable_h=max(1,height-2*padding)
    pts=[]
    for i,v in enumerate(vals):
        x=padding+(usable_w*i/(len(vals)-1 if len(vals)>1 else 1))
        y=padding+usable_h-(v-lo)/span*usable_h
        pts.append(f'{x:.1f},{y:.1f}')
    return {'points':' '.join(pts),'min':lo,'max':hi,'width':width,'height':height}


def _norm_meter_type(value):
    s=str(value or '').lower().replace('ä','a').replace('ö','o').replace('ü','u')
    if 'kalt' in s and 'wasser' in s: return 'kaltwasser'
    if 'warm' in s and 'wasser' in s: return 'warmwasser'
    if 'wasser' in s: return 'wasser'
    if 'strom' in s: return 'strom'
    if 'gas' in s: return 'gas'
    if 'warme' in s or 'wärme' in str(value or '').lower(): return 'warmemenge'
    if 'heiz' in s: return 'heizkostenverteiler'
    return s.strip()


def compare_recognized_consumptions(recognized, meter_data, period_start=None, period_end=None):
    """Vergleicht von KI erkannte Verbrauchswerte mit eigenen Zählerständen."""
    if not recognized:
        return {'available':False,'items':[],'summary':'Keine Verbrauchswerte in der Hausverwaltungsabrechnung erkannt.'}
    items=[]
    for r in recognized:
        if not isinstance(r,dict) or r.get('value') in (None,''): continue
        try: ext=float(r['value'])
        except (TypeError,ValueError): continue
        typ=_norm_meter_type(r.get('type'))
        candidates=[]
        for md in meter_data or []:
            m=md.get('meter',{})
            mt=_norm_meter_type(m.get('meter_type') or m.get('name'))
            num=str(r.get('meter_number') or '').strip()
            if num and num==str(m.get('meter_number') or '').strip(): score=100
            elif typ and (typ==mt or typ in mt or mt in typ): score=60
            else: continue
            ps=r.get('period_start') or period_start; pe=r.get('period_end') or period_end
            if not ps or not pe: continue
            pc=period_consumption(md.get('readings',[]),ps,pe)
            if pc and pc['consumption'] >= 0: candidates.append((score,m,pc))
        if not candidates:
            items.append({'type':r.get('type'),'external':ext,'unit':r.get('unit',''),'status':'kein-zahler','difference':None,'percent':None})
            continue
        _,m,pc=sorted(candidates,key=lambda x:x[0],reverse=True)[0]
        own=float(pc['consumption']); diff=round(ext-own,3); pct=None if own==0 else round(diff/own*100,1)
        severity='plausibel'
        if pct is not None and abs(pct)>=20: severity='hoch'
        elif pct is not None and abs(pct)>=5: severity='auffallig'
        items.append({'type':r.get('type'),'external':ext,'own':own,'unit':r.get('unit') or m.get('unit',''),'difference':diff,'percent':pct,'status':severity,'meter_name':m.get('name'),'meter_number':m.get('meter_number'),'start_date':pc['start_date'],'end_date':pc['end_date']})
    return {'available':bool(items),'items':items,'summary':f'{len(items)} erkannte Verbrauchswerte mit eigenen Zählern verglichen.' if items else 'Keine vergleichbaren Verbrauchswerte erkannt.'}
