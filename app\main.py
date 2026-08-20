import os, json, uuid, csv
from pathlib import Path
from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from .database import init_db, db
from .auth import hash_password, verify_password
from .calculation import calc_share
from .pdf import build_statement_pdf, build_tax_advisor_pdf
from .document_ai import extract_text, parse_statement, compare_statements, dumps, recalculate_analysis, merge_ai_analysis, build_analysis_report, build_history
from .ai_provider import analyze_with_provider, analyze_receipt_with_provider, list_provider_models, test_provider
from .meter_analysis import period_consumption, yearly_consumption, chart_points, compare_recognized_consumptions
from .tax_tools import suggest_tax_category, annual_rent_schedule
from .payment_csv import parse_bank_csv
from .payment_allocation import allocate_month, allocate_individual_payments
from .tax_package import tax_year_summary, build_tax_package
from .receipt_ai import suggest_receipt_metadata
from .receipt_matching import match_property, match_tax_entry
from .secret_store import hydrate as hydrate_settings, save as save_secrets
from .diagnostics import production_checks
from .paperless import test_connection as paperless_test, upload_document as paperless_upload, task_status as paperless_task_status, document_url as paperless_document_url, search_documents as paperless_search, get_document as paperless_get_document, download_document as paperless_download

app=FastAPI(title='Nebenkostenabrechnung',version='2.9.1')
app.add_middleware(SessionMiddleware, secret_key=os.getenv('NEBENKOSTEN_SESSION_SECRET','change-this-secret-in-production'), same_site='lax', https_only=False)
app.mount('/static', StaticFiles(directory='app/static'), name='static')
templates=Jinja2Templates(directory='app/templates')

@app.on_event('startup')
def startup(): init_db()

def current_user(request: Request):
    uid=request.session.get('user_id')
    if not uid: return None
    with db() as c: return c.execute('SELECT * FROM users WHERE id=? AND active=1',(uid,)).fetchone()

def require_user(request: Request):
    user=current_user(request)
    if not user: raise HTTPException(401)
    return user

def require_write(request: Request):
    user=require_user(request)
    role=(user['role'] or 'manager') if 'role' in user.keys() else 'manager'
    if role=='viewer' and not user['is_admin']:
        raise HTTPException(403,'Dieser Benutzer hat nur Leserechte.')
    return user

def ctx(request,**kw): return {'request':request,'current_user':current_user(request),**kw}

def owns_statement(c,sid,uid):
    return c.execute('''SELECT s.*,t.user_id,t.name tenant_name,t.apartment_area,t.building_area,t.persons,t.building_persons,t.units
                        FROM statements s JOIN tenants t ON t.id=s.tenant_id WHERE s.id=? AND t.user_id=?''',(sid,uid)).fetchone()

@app.exception_handler(401)
def unauthorized(request, exc): return RedirectResponse('/login',303)

@app.exception_handler(403)
def forbidden(request, exc):
    user=current_user(request)
    if not user: return RedirectResponse('/login',303)
    return templates.TemplateResponse('error.html',ctx(request,title='Zugriff nicht erlaubt',message=getattr(exc,'detail','Keine Berechtigung.')),status_code=403)

@app.get('/health')
def health():
    return {'ok':True,'service':'nebenkostenabrechnung','version':'2.9.1'}


@app.get('/login',response_class=HTMLResponse)
def login_get(request:Request): return templates.TemplateResponse('login.html',ctx(request,error=None))
@app.post('/login')
def login_post(request:Request,username:str=Form(...),password:str=Form(...)):
    with db() as c: user=c.execute('SELECT * FROM users WHERE username=? AND active=1',(username.strip(),)).fetchone()
    if not user or not verify_password(password,user['password_hash']):
        return templates.TemplateResponse('login.html',ctx(request,error='Benutzername oder Passwort ist falsch.'),status_code=400)
    request.session.clear(); request.session['user_id']=user['id']
    return RedirectResponse('/',303)
@app.post('/logout')
def logout(request:Request): request.session.clear(); return RedirectResponse('/login',303)

@app.get('/',response_class=HTMLResponse)
def dashboard(request:Request):
    user=require_user(request)
    from datetime import date
    today=date.today()
    ym=today.strftime('%Y-%m')
    with db() as c:
        tenants=c.execute('SELECT * FROM tenants WHERE user_id=? ORDER BY active DESC,name',(user['id'],)).fetchall()
        statements=c.execute("""SELECT s.*,t.name tenant_name,COALESCE(SUM(co.tenant_share),0) cost_total
          FROM statements s JOIN tenants t ON t.id=s.tenant_id LEFT JOIN costs co ON co.statement_id=s.id
          WHERE t.user_id=? GROUP BY s.id ORDER BY s.id DESC""",(user['id'],)).fetchall()

        missing_receipts=int(c.execute("""SELECT COUNT(*) FROM tax_entries e
            WHERE e.user_id=? AND e.entry_type='expense'
            AND NOT EXISTS(SELECT 1 FROM documents d WHERE d.user_id=e.user_id AND d.tax_entry_id=e.id)""",(user['id'],)).fetchone()[0] or 0)
        ai_pending=int(c.execute("""SELECT COUNT(*) FROM documents WHERE user_id=? AND receipt_ai_json IS NOT NULL
            AND receipt_ai_json NOT IN ('','{}') AND COALESCE(review_status,'neu')='neu'""",(user['id'],)).fetchone()[0] or 0)
        paperless_errors=int(c.execute("""SELECT COUNT(*) FROM documents WHERE user_id=? AND paperless_status LIKE 'Fehler:%'""",(user['id'],)).fetchone()[0] or 0)
        tax_review=int(c.execute("""SELECT COUNT(*) FROM tax_entries WHERE user_id=? AND tax_treatment='review'""",(user['id'],)).fetchone()[0] or 0)
        draft_statements=int(c.execute("""SELECT COUNT(*) FROM statements s JOIN tenants t ON t.id=s.tenant_id
            WHERE t.user_id=? AND s.status='Entwurf'""",(user['id'],)).fetchone()[0] or 0)

        arrears=[]
        for t in c.execute("""SELECT id,name,monthly_cold_rent,monthly_operating_advance,start_date,end_date FROM tenants
                              WHERE user_id=? AND active=1 ORDER BY name""",(user['id'],)).fetchall():
            expected=float(t['monthly_cold_rent'] or 0)+float(t['monthly_operating_advance'] or 0)
            if expected<=0: continue
            paid=float(c.execute("""SELECT COALESCE(SUM(amount),0) FROM rent_payments
                                    WHERE user_id=? AND tenant_id=? AND substr(payment_date,1,7)=?""",
                                 (user['id'],t['id'],ym)).fetchone()[0] or 0)
            diff=round(paid-expected,2)
            if diff < -1:
                arrears.append({'tenant_id':t['id'],'tenant_name':t['name'],'expected':expected,'paid':paid,'difference':diff})

    tasks={
        'missing_receipts':missing_receipts,'ai_pending':ai_pending,'paperless_errors':paperless_errors,
        'tax_review':tax_review,'draft_statements':draft_statements,'arrears':len(arrears),
        'total':missing_receipts+ai_pending+paperless_errors+tax_review+draft_statements+len(arrears),
    }
    return templates.TemplateResponse('dashboard.html',ctx(request,tenants=tenants,statements=statements,tasks=tasks,arrears=arrears,current_month=ym))


@app.get('/properties',response_class=HTMLResponse)
def properties_list(request:Request):
    user=require_user(request)
    with db() as c:
        properties=c.execute("""SELECT p.*,COUNT(DISTINCT a.id) apartment_count,COUNT(DISTINCT t.id) tenant_count
          FROM properties p LEFT JOIN apartments a ON a.property_id=p.id LEFT JOIN tenants t ON t.apartment_id=a.id
          WHERE p.user_id=? GROUP BY p.id ORDER BY p.active DESC,p.name""",(user['id'],)).fetchall()
    return templates.TemplateResponse('properties.html',ctx(request,properties=properties))

@app.post('/properties')
def property_add(request:Request,name:str=Form(...),address:str=Form(''),notes:str=Form('')):
    user=require_write(request)
    with db() as c: c.execute('INSERT INTO properties(user_id,name,address,notes) VALUES(?,?,?,?)',(user['id'],name,address,notes))
    return RedirectResponse('/properties',303)

@app.get('/property/{pid}',response_class=HTMLResponse)
def property_detail(pid:int,request:Request):
    user=require_user(request)
    with db() as c:
        prop=c.execute('SELECT * FROM properties WHERE id=? AND user_id=?',(pid,user['id'])).fetchone()
        if not prop: raise HTTPException(404)
        apartments=c.execute("""SELECT a.*,COUNT(t.id) tenant_count FROM apartments a LEFT JOIN tenants t ON t.apartment_id=a.id
          WHERE a.property_id=? GROUP BY a.id ORDER BY a.name""",(pid,)).fetchall()
    return templates.TemplateResponse('property_detail.html',ctx(request,prop=prop,apartments=apartments))

@app.post('/property/{pid}/apartments')
def apartment_add(pid:int,request:Request,name:str=Form(...),area:float=Form(0),building_area:float=Form(0),persons_total:float=Form(1),units_total:float=Form(1)):
    user=require_write(request)
    with db() as c:
        if not c.execute('SELECT id FROM properties WHERE id=? AND user_id=?',(pid,user['id'])).fetchone(): raise HTTPException(404)
        c.execute('INSERT INTO apartments(property_id,name,area,building_area,persons_total,units_total) VALUES(?,?,?,?,?,?)',(pid,name,area,building_area,persons_total,units_total))
    return RedirectResponse(f'/property/{pid}',303)

@app.get('/tenants',response_class=HTMLResponse)
def tenants_list(request:Request):
    user=require_user(request)
    with db() as c: tenants=c.execute('SELECT * FROM tenants WHERE user_id=? ORDER BY active DESC,name',(user['id'],)).fetchall()
    return templates.TemplateResponse('tenants.html',ctx(request,tenants=tenants))
@app.get('/tenant/new',response_class=HTMLResponse)
def tenant_new(request:Request):
    user=require_user(request)
    with db() as c: apartments=c.execute("""SELECT a.*,p.name property_name FROM apartments a JOIN properties p ON p.id=a.property_id WHERE p.user_id=? AND a.active=1 ORDER BY p.name,a.name""",(user['id'],)).fetchall()
    return templates.TemplateResponse('tenant_form.html',ctx(request,tenant=None,apartments=apartments))
@app.get('/tenant/{tid}/edit',response_class=HTMLResponse)
def tenant_edit(tid:int,request:Request):
    user=require_user(request)
    with db() as c: tenant=c.execute('SELECT * FROM tenants WHERE id=? AND user_id=?',(tid,user['id'])).fetchone()
    if not tenant: raise HTTPException(404)
    with db() as c: apartments=c.execute("""SELECT a.*,p.name property_name FROM apartments a JOIN properties p ON p.id=a.property_id WHERE p.user_id=? AND a.active=1 ORDER BY p.name,a.name""",(user['id'],)).fetchall()
    return templates.TemplateResponse('tenant_form.html',ctx(request,tenant=tenant,apartments=apartments))
@app.post('/tenant/save')
def tenant_save(request:Request,tenant_id:int=Form(0),apartment_id:int=Form(...),name:str=Form(...),address:str=Form(''),rental_object:str=Form(''),apartment_area:float=Form(0),building_area:float=Form(0),persons:float=Form(1),building_persons:float=Form(1),units:float=Form(1),start_date:str=Form(''),end_date:str=Form(''),monthly_cold_rent:float=Form(0),monthly_operating_advance:float=Form(0),active:int=Form(1)):
    user=require_write(request)
    values=(apartment_id,name,address,rental_object,apartment_area,building_area,persons,building_persons,units,start_date,end_date,monthly_cold_rent,monthly_operating_advance,active)
    with db() as c:
        if tenant_id:
            cur=c.execute('''UPDATE tenants SET apartment_id=?,name=?,address=?,rental_object=?,apartment_area=?,building_area=?,persons=?,building_persons=?,units=?,start_date=?,end_date=?,monthly_cold_rent=?,monthly_operating_advance=?,active=? WHERE id=? AND user_id=?''',values+(tenant_id,user['id']))
            if cur.rowcount==0: raise HTTPException(404)
        else:
            c.execute('''INSERT INTO tenants(user_id,apartment_id,name,address,rental_object,apartment_area,building_area,persons,building_persons,units,start_date,end_date,monthly_cold_rent,monthly_operating_advance,active) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(user['id'],)+values)
    return RedirectResponse('/tenants',303)

@app.get('/statement/new',response_class=HTMLResponse)
def statement_new(request:Request):
    user=require_user(request)
    with db() as c: tenants=c.execute('SELECT * FROM tenants WHERE user_id=? AND active=1 ORDER BY name',(user['id'],)).fetchall()
    return templates.TemplateResponse('statement_form.html',ctx(request,tenants=tenants))
@app.post('/statement/save')
def statement_save(request:Request,tenant_id:int=Form(...),period_start:str=Form(...),period_end:str=Form(...),advance_payments:float=Form(0),notes:str=Form('')):
    user=require_write(request)
    with db() as c:
        tenant=c.execute('SELECT id FROM tenants WHERE id=? AND user_id=?',(tenant_id,user['id'])).fetchone()
        if not tenant: raise HTTPException(404)
        cur=c.execute('INSERT INTO statements(tenant_id,period_start,period_end,advance_payments,notes) VALUES(?,?,?,?,?)',(tenant_id,period_start,period_end,advance_payments,notes)); sid=cur.lastrowid
    return RedirectResponse(f'/statement/{sid}',303)
@app.get('/statement/{sid}',response_class=HTMLResponse)
def statement_detail(sid:int,request:Request):
    user=require_user(request)
    with db() as c:
        st=owns_statement(c,sid,user['id'])
        if not st: raise HTTPException(404)
        costs=c.execute('SELECT * FROM costs WHERE statement_id=? ORDER BY id',(sid,)).fetchall()
        meters=c.execute('SELECT * FROM meters WHERE user_id=? AND tenant_id=? AND active=1 ORDER BY name',(user['id'],st['tenant_id'])).fetchall()
        meter_options=[]
        for m in meters:
            rr=c.execute('SELECT * FROM meter_readings WHERE meter_id=? ORDER BY reading_date,id',(m['id'],)).fetchall()
            pc=period_consumption(rr,st['period_start'],st['period_end'])
            meter_options.append({'meter':dict(m),'period':pc})
    total=sum(x['tenant_share'] for x in costs); balance=round(total-st['advance_payments'],2)
    return templates.TemplateResponse('statement_detail.html',ctx(request,st=st,costs=costs,total=total,balance=balance,meter_options=meter_options))
@app.post('/statement/{sid}/cost')
def cost_add(sid:int,request:Request,title:str=Form(...),total_cost:float=Form(...),allocation_key:str=Form(...),tenant_value:float=Form(0),total_value:float=Form(0),direct_amount:float=Form(0),document_no:str=Form(''),notes:str=Form('')):
    user=require_write(request); share=calc_share(total_cost,allocation_key,tenant_value,total_value,direct_amount)
    with db() as c:
        if not owns_statement(c,sid,user['id']): raise HTTPException(404)
        c.execute('INSERT INTO costs(statement_id,title,total_cost,allocation_key,tenant_value,total_value,direct_amount,tenant_share,document_no,notes) VALUES(?,?,?,?,?,?,?,?,?,?)',(sid,title,total_cost,allocation_key,tenant_value,total_value,direct_amount,share,document_no,notes))
    return RedirectResponse(f'/statement/{sid}',303)
@app.post('/statement/{sid}/meter-cost')
def meter_cost_add(sid:int,request:Request,meter_id:int=Form(...),title:str=Form(...),total_cost:float=Form(...),total_value:float=Form(...),document_no:str=Form(''),notes:str=Form('')):
    user=require_write(request)
    with db() as c:
        st=owns_statement(c,sid,user['id'])
        if not st: raise HTTPException(404)
        meter=c.execute('SELECT * FROM meters WHERE id=? AND user_id=? AND tenant_id=?',(meter_id,user['id'],st['tenant_id'])).fetchone()
        if not meter: raise HTTPException(404)
        readings=c.execute('SELECT * FROM meter_readings WHERE meter_id=? ORDER BY reading_date,id',(meter_id,)).fetchall()
        pc=period_consumption(readings,st['period_start'],st['period_end'])
        if not pc: raise HTTPException(400,'Für den Abrechnungszeitraum fehlen geeignete Zählerstände.')
        if pc['consumption'] < 0: raise HTTPException(400,'Negativer Verbrauch erkannt. Zählerstände/Zählerwechsel prüfen.')
        share=calc_share(total_cost,'consumption',pc['consumption'],total_value,0)
        note=(notes+' ' if notes else '')+f"Zähler {meter['name']}: {pc['start_value']} {meter['unit']} am {pc['start_date']} bis {pc['end_value']} {meter['unit']} am {pc['end_date']} = {pc['consumption']} {meter['unit']}"
        c.execute('''INSERT INTO costs(statement_id,title,total_cost,allocation_key,tenant_value,total_value,direct_amount,tenant_share,document_no,notes,meter_id,meter_reading_start_id,meter_reading_end_id,meter_consumption,meter_unit) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(sid,title,total_cost,'consumption',pc['consumption'],total_value,0,share,document_no,note,meter_id,pc['start_id'],pc['end_id'],pc['consumption'],meter['unit']))
    return RedirectResponse(f'/statement/{sid}',303)

@app.post('/cost/{cid}/delete')
def cost_delete(cid:int,request:Request):
    user=require_write(request)
    with db() as c:
        row=c.execute('''SELECT co.statement_id FROM costs co JOIN statements s ON s.id=co.statement_id JOIN tenants t ON t.id=s.tenant_id WHERE co.id=? AND t.user_id=?''',(cid,user['id'])).fetchone()
        if not row: raise HTTPException(404)
        c.execute('DELETE FROM costs WHERE id=?',(cid,)); sid=row['statement_id']
    return RedirectResponse(f'/statement/{sid}',303)
@app.get('/statement/{sid}/pdf')
def statement_pdf(sid:int,request:Request):
    user=require_user(request)
    with db() as c:
        st=owns_statement(c,sid,user['id'])
        if not st: raise HTTPException(404)
        tenant=c.execute('SELECT * FROM tenants WHERE id=? AND user_id=?',(st['tenant_id'],user['id'])).fetchone()
        settings=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
        costs=c.execute('SELECT * FROM costs WHERE statement_id=? ORDER BY id',(sid,)).fetchall()
    return StreamingResponse(build_statement_pdf(settings,tenant,st,costs),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="Nebenkostenabrechnung_{sid}.pdf"'})




def _recalculate_payment_month(c,user_id:int,tenant_id:int,year_month:str):
    tenant=c.execute("SELECT monthly_cold_rent,monthly_operating_advance FROM tenants WHERE id=? AND user_id=?",(tenant_id,user_id)).fetchone()
    if not tenant:
        return None
    rows=[dict(x) for x in c.execute("""SELECT * FROM rent_payments WHERE user_id=? AND tenant_id=? AND substr(payment_date,1,7)=? ORDER BY payment_date,id""",
                                     (user_id,tenant_id,year_month)).fetchall()]
    allocated=allocate_individual_payments(rows,tenant['monthly_cold_rent'],tenant['monthly_operating_advance'])
    for row in allocated:
        c.execute("""UPDATE rent_payments SET rent_part=?,operating_part=?,other_part=?,allocation_month=? WHERE id=?""",
                  (row['rent_part'],row['operating_part'],row['other_part'],year_month,row['id']))
    return allocate_month(rows,tenant['monthly_cold_rent'],tenant['monthly_operating_advance'])

@app.get('/payments',response_class=HTMLResponse)
def payments_get(request:Request,year:int=0):
    user=require_user(request)
    from datetime import date
    if not year: year=date.today().year
    with db() as c:
        tenants=c.execute('SELECT id,name,monthly_cold_rent,monthly_operating_advance,start_date,end_date FROM tenants WHERE user_id=? AND active=1 ORDER BY name',(user['id'],)).fetchall()
        payments=c.execute("""SELECT p.*,t.name tenant_name FROM rent_payments p JOIN tenants t ON t.id=p.tenant_id
                              WHERE p.user_id=? AND substr(p.payment_date,1,4)=? ORDER BY p.payment_date DESC,p.id DESC""",(user['id'],str(year))).fetchall()
        schedules=[]
        monthly=[]
        for t in tenants:
            plan=annual_rent_schedule(t['monthly_cold_rent'],t['start_date'],t['end_date'],year)
            expected_rent=sum(x['amount'] for x in plan)
            active_months={x['month'] for x in plan}
            expected_operating=round(len(active_months)*float(t['monthly_operating_advance'] or 0),2)
            tenant_paid=float(c.execute("""SELECT COALESCE(SUM(amount),0) FROM rent_payments WHERE user_id=? AND tenant_id=? AND substr(payment_date,1,4)=?""",
                                        (user['id'],t['id'],str(year))).fetchone()[0] or 0)
            schedules.append({'tenant':t,'expected':round(expected_rent+expected_operating,2),'expected_rent':expected_rent,
                              'expected_operating':expected_operating,'paid':tenant_paid,
                              'difference':round(tenant_paid-expected_rent-expected_operating,2)})
            for month in sorted(active_months):
                ym=f"{year}-{month:02d}"
                summary=_recalculate_payment_month(c,user['id'],t['id'],ym)
                if summary:
                    monthly.append({'tenant':t,'month':ym,**summary})
        payments=c.execute("""SELECT p.*,t.name tenant_name FROM rent_payments p JOIN tenants t ON t.id=p.tenant_id
                              WHERE p.user_id=? AND substr(p.payment_date,1,4)=? ORDER BY p.payment_date DESC,p.id DESC""",(user['id'],str(year))).fetchall()
    return templates.TemplateResponse('payments.html',ctx(request,year=year,tenants=tenants,payments=payments,schedules=schedules,monthly=monthly))

@app.post('/payments')
def payment_add(request:Request,tenant_id:int=Form(...),payment_date:str=Form(...),amount:float=Form(...),
                payment_type:str=Form('rent'),reference:str=Form(''),notes:str=Form('')):
    user=require_write(request)
    if payment_type not in {'rent','operating_advance','other'}: raise HTTPException(400)
    with db() as c:
        t=c.execute('SELECT id FROM tenants WHERE id=? AND user_id=?',(tenant_id,user['id'])).fetchone()
        if not t: raise HTTPException(404)
        c.execute('INSERT INTO rent_payments(user_id,tenant_id,payment_date,amount,payment_type,reference,notes) VALUES(?,?,?,?,?,?,?)',
                  (user['id'],tenant_id,payment_date,amount,payment_type,reference,notes))
        _recalculate_payment_month(c,user['id'],tenant_id,payment_date[:7])
    return RedirectResponse('/payments?year='+payment_date[:4],303)



@app.post('/payments/preview-csv',response_class=HTMLResponse)
async def payments_preview_csv(request:Request,csv_file:UploadFile=File(...),default_tenant_id:int=Form(0),default_type:str=Form('rent')):
    user=require_write(request)
    data=await csv_file.read()
    if len(data)>10*1024*1024: raise HTTPException(413,'CSV-Datei ist zu groß (max. 10 MB).')
    with db() as c:
        tenants=[dict(x) for x in c.execute('SELECT id,name FROM tenants WHERE user_id=? AND active=1 ORDER BY name',(user['id'],)).fetchall()]
    try: result=parse_bank_csv(data,tenants,default_tenant_id,default_type)
    except ValueError as exc: raise HTTPException(400,str(exc))
    CSV_PREVIEW_DIR.mkdir(parents=True,exist_ok=True)
    preview_id=uuid.uuid4().hex
    payload={'user_id':int(user['id']),'rows':result['rows'],'skipped':result['skipped']}
    (CSV_PREVIEW_DIR/f'{preview_id}.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    return templates.TemplateResponse('payments_csv_preview.html',ctx(request,preview_id=preview_id,rows=result['rows'],skipped=result['skipped'],tenants=tenants))

@app.post('/payments/confirm-csv')
async def payments_confirm_csv(request:Request,preview_id:str=Form(...)):
    user=require_write(request)
    if not preview_id or any(ch not in '0123456789abcdef' for ch in preview_id.lower()) or len(preview_id)!=32:
        raise HTTPException(400)
    path=CSV_PREVIEW_DIR/f'{preview_id}.json'
    if not path.is_file(): raise HTTPException(404,'CSV-Vorschau ist nicht mehr vorhanden.')
    payload=json.loads(path.read_text(encoding='utf-8'))
    if int(payload.get('user_id') or 0)!=int(user['id']): raise HTTPException(403)
    form=await request.form()
    imported=duplicates=0; years=[]; recalc=set()
    with db() as c:
        valid_tenants={int(x[0]) for x in c.execute('SELECT id FROM tenants WHERE user_id=?',(user['id'],)).fetchall()}
        for idx,row in enumerate(payload.get('rows') or []):
            if form.get(f'include_{idx}')!='1': continue
            try: tenant_id=int(form.get(f'tenant_{idx}') or row['tenant_id'])
            except Exception: continue
            if tenant_id not in valid_tenants: continue
            ptype=str(form.get(f'type_{idx}') or row['payment_type'])
            if ptype not in {'rent','operating_advance','other'}: ptype='rent'
            try:
                c.execute("""INSERT INTO rent_payments(user_id,tenant_id,payment_date,amount,payment_type,reference,notes,import_hash)
                             VALUES(?,?,?,?,?,?,?,?)""",
                          (user['id'],tenant_id,row['payment_date'],row['amount'],ptype,row['reference'],
                           f"CSV-Import nach Vorschau; ursprüngliche Zuordnung: {row.get('match','')}",row['fingerprint']))
                imported+=1; years.append(row['payment_date'][:4]); recalc.add((tenant_id,row['payment_date'][:7]))
            except Exception as exc:
                if 'UNIQUE constraint failed' in str(exc): duplicates+=1
                else: raise
        for tenant_id,ym in recalc: _recalculate_payment_month(c,user['id'],tenant_id,ym)
    path.unlink(missing_ok=True)
    from urllib.parse import urlencode
    qs=urlencode({'year':max(years) if years else 0,'csv_imported':imported,'csv_skipped':0,'csv_duplicates':duplicates})
    return RedirectResponse('/payments?'+qs,303)

@app.post('/payments/import-csv')
async def payments_import_csv(request:Request,csv_file:UploadFile=File(...),default_tenant_id:int=Form(0),default_type:str=Form('rent')):
    user=require_write(request)
    if default_type not in {'rent','operating_advance','other'}:
        raise HTTPException(400)
    data=await csv_file.read()
    if len(data)>10*1024*1024:
        raise HTTPException(413,'CSV-Datei ist zu groß (max. 10 MB).')
    with db() as c:
        tenants=[dict(x) for x in c.execute('SELECT id,name FROM tenants WHERE user_id=? AND active=1 ORDER BY name',(user['id'],)).fetchall()]
        if default_tenant_id and not any(int(t['id'])==default_tenant_id for t in tenants):
            raise HTTPException(404)
        try:
            result=parse_bank_csv(data,tenants,default_tenant_id,default_type)
        except ValueError as exc:
            raise HTTPException(400,str(exc))
        imported=0
        duplicates=0
        years=[]
        recalc_months=set()
        for row in result['rows']:
            try:
                c.execute(
                    "INSERT INTO rent_payments(user_id,tenant_id,payment_date,amount,payment_type,reference,notes,import_hash) VALUES(?,?,?,?,?,?,?,?)",
                    (user['id'],row['tenant_id'],row['payment_date'],row['amount'],row['payment_type'],row['reference'],
                     f"CSV-Import; Zuordnung: {row['match']}",row['fingerprint'])
                )
                imported+=1
                years.append(row['payment_date'][:4])
                recalc_months.add((row['tenant_id'],row['payment_date'][:7]))
            except Exception as exc:
                if 'UNIQUE constraint failed' in str(exc):
                    duplicates+=1
                else:
                    raise
        for tenant_id,ym in recalc_months:
            _recalculate_payment_month(c,user['id'],tenant_id,ym)
    year=max(years) if years else ''
    from urllib.parse import urlencode
    qs=urlencode({'year':year or 0,'csv_imported':imported,'csv_skipped':len(result['skipped']),'csv_duplicates':duplicates})
    return RedirectResponse('/payments?'+qs,303)

@app.post('/payments/{pid}/tax')
def payment_to_tax(pid:int,request:Request):
    user=require_write(request)
    with db() as c:
        row=c.execute("""SELECT p.*,t.apartment_id,a.property_id,t.name tenant_name FROM rent_payments p
                         JOIN tenants t ON t.id=p.tenant_id LEFT JOIN apartments a ON a.id=t.apartment_id
                         WHERE p.id=? AND p.user_id=?""",(pid,user['id'])).fetchone()
        if not row or not row['property_id']: raise HTTPException(404)
        if row['tax_entry_id']: return RedirectResponse('/payments?year='+row['payment_date'][:4],303)
        cat='rent' if row['payment_type']=='rent' else ('operating_advance' if row['payment_type']=='operating_advance' else 'other_income')
        cur=c.execute("""INSERT INTO tax_entries(user_id,property_id,tax_year,entry_date,entry_type,category,description,amount,tax_treatment,notes,source_type,source_id)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (user['id'],row['property_id'],int(row['payment_date'][:4]),row['payment_date'],'income',cat,
                       f"{row['tenant_name']} – {row['reference'] or row['payment_type']}",abs(float(row['amount'])),
                       'review',row['notes'] or '','rent_payment',pid))
        c.execute('UPDATE rent_payments SET tax_entry_id=? WHERE id=?',(cur.lastrowid,pid))
    return RedirectResponse('/payments?year='+row['payment_date'][:4],303)

@app.post('/tax-advisor/import-costs')
def tax_import_costs(request:Request,year:int=Form(...),property_id:int=Form(...)):
    user=require_write(request)
    with db() as c:
        prop=c.execute('SELECT id FROM properties WHERE id=? AND user_id=?',(property_id,user['id'])).fetchone()
        if not prop: raise HTTPException(404)
        rows=c.execute("""SELECT co.id,co.title,co.total_cost,co.notes,s.period_end FROM costs co
                          JOIN statements s ON s.id=co.statement_id JOIN tenants t ON t.id=s.tenant_id
                          JOIN apartments a ON a.id=t.apartment_id
                          WHERE t.user_id=? AND a.property_id=? AND substr(s.period_end,1,4)=?""",
                       (user['id'],property_id,str(year))).fetchall()
        for x in rows:
            exists=c.execute("SELECT id FROM tax_entries WHERE user_id=? AND source_type='cost' AND source_id=?",(user['id'],x['id'])).fetchone()
            if exists: continue
            cat=suggest_tax_category(x['title'],x['notes'] or '')
            treatment='review' if cat=='reserve_contribution' else 'potentially_deductible'
            c.execute("""INSERT INTO tax_entries(user_id,property_id,tax_year,entry_date,entry_type,category,description,amount,tax_treatment,notes,source_type,source_id)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (user['id'],property_id,year,x['period_end'],'expense',cat,x['title'],abs(float(x['total_cost'] or 0)),
                       treatment,x['notes'] or '','cost',x['id']))
    return RedirectResponse(f'/tax-advisor?year={year}&property_id={property_id}',303)

TAX_CATEGORIES={
    'rent':'Kaltmiete / Mietzins',
    'other_income':'Sonstige Mieteinnahmen',
    'operating_advance':'Nebenkosten-Vorauszahlungen',
    'repairs':'Reparaturen / Erhaltungsaufwand',
    'property_tax':'Grundsteuer / öffentliche Abgaben',
    'insurance':'Gebäude-/Haftpflichtversicherung',
    'interest':'Darlehenszinsen',
    'afa':'AfA / Abschreibung',
    'management':'Verwaltungskosten',
    'nonalloc_operating':'Nicht umlagefähige Betriebskosten',
    'reserve_contribution':'Erhaltungsrücklage (Einzahlung)',
    'other_expense':'Sonstige Aufwendungen',
}

@app.get('/tax-advisor',response_class=HTMLResponse)
def tax_advisor_get(request:Request,year:int=0,property_id:int=0):
    user=require_user(request)
    from datetime import date
    if not year:
        year=date.today().year-1
    with db() as c:
        years={int(r[0]) for r in c.execute(
            "SELECT DISTINCT substr(s.period_end,1,4) y FROM statements s JOIN tenants t ON t.id=s.tenant_id WHERE t.user_id=? AND y<>''",
            (user['id'],)
        ).fetchall() if str(r[0]).isdigit()}
        years.update(int(r[0]) for r in c.execute(
            'SELECT DISTINCT tax_year FROM tax_entries WHERE user_id=?',(user['id'],)
        ).fetchall())
        props=c.execute('SELECT * FROM properties WHERE user_id=? ORDER BY name',(user['id'],)).fetchall()
        q="SELECT e.*,p.name property_name FROM tax_entries e JOIN properties p ON p.id=e.property_id WHERE e.user_id=? AND e.tax_year=?"
        args=[user['id'],year]
        if property_id:
            q+=' AND e.property_id=?'
            args.append(property_id)
        q+=' ORDER BY e.entry_date,e.id'
        entries=c.execute(q,args).fetchall()
        summary=tax_year_summary(c,user['id'],year,TAX_CATEGORIES)
        missing_receipts=[]
        exp_rows=c.execute("""SELECT e.id,e.property_id,e.description,e.amount,p.name property_name
                              FROM tax_entries e JOIN properties p ON p.id=e.property_id
                              WHERE e.user_id=? AND e.tax_year=? AND e.entry_type='expense'
                              ORDER BY p.name,e.entry_date,e.id""",(user['id'],year)).fetchall()
        for er in exp_rows:
            has_doc=c.execute('SELECT 1 FROM documents WHERE user_id=? AND tax_entry_id=? LIMIT 1',(user['id'],er['id'])).fetchone()
            if not has_doc:
                missing_receipts.append({'id':er['id'],'property_name':er['property_name'],'description':er['description'] or 'Aufwand','amount':float(er['amount'] or 0)})
        summary['missing_receipts']=missing_receipts
        if missing_receipts:
            summary['issues'].append(f"{len(missing_receipts)} steuerliche Aufwendungen ohne zugeordneten Beleg")
        closure=c.execute('SELECT * FROM tax_year_closures WHERE user_id=? AND tax_year=?',(user['id'],year)).fetchone()
    return templates.TemplateResponse(
        'tax_advisor.html',
        ctx(request,year=year,years=sorted(years,reverse=True),properties=props,
            property_id=property_id,entries=entries,categories=TAX_CATEGORIES,summary=summary,closure=closure)
    )

@app.post('/tax-advisor/entry')
def tax_entry_add(request:Request,property_id:int=Form(...),tax_year:int=Form(...),entry_date:str=Form(''),
                  entry_type:str=Form(...),category:str=Form(...),description:str=Form(''),amount:float=Form(...),
                  tax_treatment:str=Form('review'),notes:str=Form('')):
    user=require_write(request)
    if entry_type not in {'income','expense'} or category not in TAX_CATEGORIES or tax_treatment not in {'review','potentially_deductible','not_deductible'}:
        raise HTTPException(400)
    if category=='reserve_contribution':
        tax_treatment='review'
    with db() as c:
        prop=c.execute('SELECT id FROM properties WHERE id=? AND user_id=?',(property_id,user['id'])).fetchone()
        if not prop:
            raise HTTPException(404)
        c.execute(
            'INSERT INTO tax_entries(user_id,property_id,tax_year,entry_date,entry_type,category,description,amount,tax_treatment,notes) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (user['id'],property_id,tax_year,entry_date,entry_type,category,description,abs(amount),tax_treatment,notes)
        )
    return RedirectResponse(f'/tax-advisor?year={tax_year}&property_id={property_id}',303)

@app.post('/tax-advisor/entry/{eid}/delete')
def tax_entry_delete(eid:int,request:Request):
    user=require_write(request)
    with db() as c:
        row=c.execute('SELECT tax_year,property_id FROM tax_entries WHERE id=? AND user_id=?',(eid,user['id'])).fetchone()
        if not row:
            raise HTTPException(404)
        c.execute('DELETE FROM tax_entries WHERE id=?',(eid,))
    return RedirectResponse(f"/tax-advisor?year={row['tax_year']}&property_id={row['property_id']}",303)

def _tax_pdf_data(c,user_id:int,year:int):
    settings=c.execute('SELECT * FROM settings WHERE user_id=?',(user_id,)).fetchone()
    props=[dict(x) for x in c.execute('SELECT * FROM properties WHERE user_id=? ORDER BY name',(user_id,)).fetchall()]
    result=[]
    for prop in props:
        rows=c.execute(
            "SELECT s.*,t.name tenant_name FROM statements s JOIN tenants t ON t.id=s.tenant_id JOIN apartments a ON a.id=t.apartment_id WHERE a.property_id=? AND t.user_id=? AND substr(s.period_end,1,4)=? ORDER BY t.name,s.period_end",
            (prop['id'],user_id,str(year))
        ).fetchall()
        statements=[]
        cats={}
        for st in rows:
            costs=c.execute('SELECT title,total_cost,tenant_share FROM costs WHERE statement_id=?',(st['id'],)).fetchall()
            allocated=sum(float(x['tenant_share'] or 0) for x in costs)
            statements.append({
                'tenant_name':st['tenant_name'],
                'period_start':st['period_start'],
                'period_end':st['period_end'],
                'advance_payments':float(st['advance_payments'] or 0),
                'allocated_costs':allocated,
                'balance':allocated-float(st['advance_payments'] or 0)
            })
            for x in costs:
                d=cats.setdefault(x['title'],{'title':x['title'],'total_cost':0.0,'tenant_share':0.0})
                d['total_cost']+=float(x['total_cost'] or 0)
                d['tenant_share']+=float(x['tenant_share'] or 0)
        entries=[dict(x) for x in c.execute(
            'SELECT * FROM tax_entries WHERE user_id=? AND property_id=? AND tax_year=? ORDER BY entry_date,id',
            (user_id,prop['id'],year)
        ).fetchall()]
        if statements or entries:
            prop['statements']=statements
            prop['cost_categories']=list(cats.values())
            prop['tax_entries']=entries
            result.append(prop)
    return settings,result

@app.get('/tax-advisor/{year}/pdf')
def tax_advisor_pdf(year:int,request:Request):
    user=require_user(request)
    if year<2000 or year>2100:
        raise HTTPException(400,'Ungültiges Steuerjahr')
    with db() as c:
        settings,result=_tax_pdf_data(c,user['id'],year)
    return StreamingResponse(
        build_tax_advisor_pdf(settings,year,result),
        media_type='application/pdf',
        headers={'Content-Disposition':f'inline; filename="Steuerberater_Vermietung_{year}.pdf"'}
    )


@app.get('/tax-advisor/{year}/property/{property_id}/pdf')
def tax_advisor_property_pdf(year:int,property_id:int,request:Request):
    user=require_user(request)
    with db() as c:
        settings,result=_tax_pdf_data(c,user['id'],year)
    result=[p for p in result if p['id']==property_id]
    if not result: raise HTTPException(404)
    return StreamingResponse(build_tax_advisor_pdf(settings,year,result),media_type='application/pdf',
        headers={'Content-Disposition':f'inline; filename="AnlageV_Vorbereitung_{year}_Objekt_{property_id}.pdf"'})

@app.get('/tax-advisor/{year}/csv')
def tax_advisor_csv(year:int,request:Request):
    user=require_user(request)
    import io
    out=io.StringIO()
    w=csv.writer(out,delimiter=';')
    w.writerow(['Jahr','Objekt','Datum','Typ','Kategorie','Beschreibung','Betrag','Steuerliche Einordnung','Notiz'])
    with db() as c:
        rows=c.execute(
            'SELECT e.*,p.name property_name FROM tax_entries e JOIN properties p ON p.id=e.property_id WHERE e.user_id=? AND e.tax_year=? ORDER BY p.name,e.entry_date,e.id',
            (user['id'],year)
        ).fetchall()
        for x in rows:
            w.writerow([
                year,x['property_name'],x['entry_date'] or '',x['entry_type'],
                TAX_CATEGORIES.get(x['category'],x['category']),x['description'] or '',
                f"{float(x['amount']):.2f}".replace('.',','),x['tax_treatment'],x['notes'] or ''
            ])
    return Response(
        '\ufeff'+out.getvalue(),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition':f'attachment; filename="Steuerberater_Vermietung_{year}.csv"'}
    )


@app.post('/tax-advisor/{year}/import-payments')
def tax_import_payments(year:int,request:Request):
    user=require_write(request)
    with db() as c:
        rows=c.execute("""SELECT rp.*,t.name tenant_name,a.property_id FROM rent_payments rp
                          JOIN tenants t ON t.id=rp.tenant_id JOIN apartments a ON a.id=t.apartment_id
                          WHERE rp.user_id=? AND substr(rp.payment_date,1,4)=?""",(user['id'],str(year))).fetchall()
        for r in rows:
            parts=[('rent',float(r['rent_part'] or 0),'Kaltmiete'),
                   ('operating_advance',float(r['operating_part'] or 0),'Nebenkostenvorauszahlung'),
                   ('other_income',float(r['other_part'] or 0),'Sonstige Zahlung')]
            for cat,amount,label in parts:
                if amount<=0: continue
                source_id=int(r['id'])*10+{'rent':1,'operating_advance':2,'other_income':3}[cat]
                if c.execute("SELECT id FROM tax_entries WHERE user_id=? AND source_type='payment_split' AND source_id=?",(user['id'],source_id)).fetchone():
                    continue
                c.execute("""INSERT INTO tax_entries(user_id,property_id,tax_year,entry_date,entry_type,category,description,amount,tax_treatment,notes,source_type,source_id)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (user['id'],r['property_id'],year,r['payment_date'],'income',cat,
                           f"{r['tenant_name']} – {label}",amount,'review',r['reference'] or '','payment_split',source_id))
    return RedirectResponse(f'/tax-advisor?year={year}',303)

@app.post('/tax-advisor/{year}/close')
def tax_year_close(year:int,request:Request,notes:str=Form('')):
    user=require_write(request)
    from datetime import datetime
    with db() as c:
        c.execute("""INSERT INTO tax_year_closures(user_id,tax_year,status,notes,closed_at) VALUES(?,?,?,?,?)
                     ON CONFLICT(user_id,tax_year) DO UPDATE SET status=excluded.status,notes=excluded.notes,closed_at=excluded.closed_at""",
                  (user['id'],year,'abgeschlossen',notes,datetime.now().isoformat(timespec='seconds')))
    return RedirectResponse(f'/tax-advisor?year={year}',303)

@app.post('/tax-advisor/{year}/reopen')
def tax_year_reopen(year:int,request:Request):
    user=require_write(request)
    with db() as c:
        c.execute("UPDATE tax_year_closures SET status='offen',closed_at=NULL WHERE user_id=? AND tax_year=?",(user['id'],year))
    return RedirectResponse(f'/tax-advisor?year={year}',303)

@app.get('/tax-advisor/{year}/package')
def tax_year_package(year:int,request:Request):
    user=require_user(request)
    with db() as c:
        settings,result=_tax_pdf_data(c,user['id'],year)
        summary=tax_year_summary(c,user['id'],year,TAX_CATEGORIES)
    overview=build_tax_advisor_pdf(settings,year,result)
    prop_pdfs={}
    for prop in result:
        prop_pdfs[prop['id']]=build_tax_advisor_pdf(settings,year,[prop])
    receipt_files=[]
    with db() as c:
        docs=c.execute("""SELECT d.*,p.name property_name,e.description entry_description
                          FROM documents d LEFT JOIN properties p ON p.id=d.property_id
                          LEFT JOIN tax_entries e ON e.id=d.tax_entry_id
                          WHERE d.user_id=? AND d.tax_year=? ORDER BY p.name,d.id""",(user['id'],year)).fetchall()
        settings_row=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
        settings_dict=hydrate_settings(settings_row)
        for d in docs:
            prop_name=(d['property_name'] or 'Ohne-Objekt').replace('/','_').replace('\\','_')
            if d['stored_name']:
                path=(DOCUMENT_DIR/d['stored_name']).resolve()
                if DOCUMENT_DIR.resolve() in path.parents and path.is_file():
                    fname=Path(d['filename'] or d['stored_name']).name
                    receipt_files.append({'archive_name':f"Belege/{prop_name}/{d['id']:04d}-{fname}",'data':path.read_bytes()})
                    continue
            if d['paperless_document_id']:
                try:
                    downloaded=paperless_download(settings_dict,int(d['paperless_document_id']))
                    fname=Path(downloaded['filename'] or d['filename'] or f"paperless-{d['paperless_document_id']}").name
                    receipt_files.append({'archive_name':f"Belege/{prop_name}/{d['id']:04d}-{fname}",'data':downloaded['data']})
                except Exception:
                    # Das Paket bleibt erzeugbar; fehlende externe Belege stehen weiterhin in der Prüfliste.
                    pass
    package=build_tax_package(settings,year,summary,overview,prop_pdfs,TAX_CATEGORIES,receipt_files)
    return StreamingResponse(package,media_type='application/zip',
        headers={'Content-Disposition':f'attachment; filename="Steuerberater-Paket-{year}.zip"'})

@app.get('/settings',response_class=HTMLResponse)
def settings_get(request:Request):
    user=require_user(request)
    with db() as c:
        c.execute('INSERT OR IGNORE INTO settings(user_id,landlord_name,landlord_address,landlord_email,landlord_phone,iban) VALUES(?,?,?,?,?,?)',(user['id'],'','','','',''))
        settings=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
    return templates.TemplateResponse('settings.html',ctx(request,settings=settings))
@app.post('/settings')
def settings_save(request:Request,landlord_name:str=Form(''),landlord_address:str=Form(''),landlord_email:str=Form(''),landlord_phone:str=Form(''),iban:str=Form(''),ai_provider:str=Form('none'),ai_model:str=Form(''),ai_base_url:str=Form(''),ai_api_key:str=Form(''),ai_referer:str=Form(''),ai_app_title:str=Form('Nebenkostenabrechnung'),smtp_host:str=Form(''),smtp_port:int=Form(587),smtp_user:str=Form(''),smtp_password:str=Form(''),smtp_from:str=Form(''),smtp_security:str=Form('starttls')):
    user=require_write(request)
    if ai_provider not in {'none','ollama','openai','anthropic','openrouter','gemini'}: raise HTTPException(400)
    with db() as c:
        c.execute('INSERT OR IGNORE INTO settings(user_id) VALUES(?)',(user['id'],))
        if ai_api_key or smtp_password:
            save_secrets(user['id'],ai_api_key=ai_api_key,smtp_password=smtp_password)
        c.execute('UPDATE settings SET landlord_name=?,landlord_address=?,landlord_email=?,landlord_phone=?,iban=?,ai_provider=?,ai_model=?,ai_base_url=?,ai_referer=?,ai_app_title=?,smtp_host=?,smtp_port=?,smtp_user=?,smtp_from=?,smtp_security=? WHERE user_id=?',
                  (landlord_name,landlord_address,landlord_email,landlord_phone,iban,ai_provider,ai_model,ai_base_url,ai_referer,ai_app_title,smtp_host,smtp_port,smtp_user,smtp_from,smtp_security,user['id']))
        if ai_api_key: c.execute("UPDATE settings SET ai_api_key='__secret_store__' WHERE user_id=?",(user['id'],))
        if smtp_password: c.execute("UPDATE settings SET smtp_password='__secret_store__' WHERE user_id=?",(user['id'],))
    return RedirectResponse('/settings',303)

@app.get('/settings/ai-models')
def settings_ai_models(request:Request):
    user=require_user(request)
    with db() as c: settings=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
    try: return {'ok':True,'models':list_provider_models(hydrate_settings(settings))}
    except Exception as exc: return {'ok':False,'error':str(exc),'models':[]}

@app.get('/settings/ai-test')
def settings_ai_test(request:Request):
    user=require_user(request)
    with db() as c: settings=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
    try: return test_provider(hydrate_settings(settings))
    except Exception as exc: return {'ok':False,'error':str(exc)}


@app.post('/settings/paperless')
def settings_paperless_save(request:Request,paperless_enabled:int=Form(0),paperless_url:str=Form(''),
                            paperless_token:str=Form(''),paperless_auto_upload:int=Form(0),
                            paperless_default_tags:str=Form('Nebenkosten,Vermietung')):
    user=require_write(request)
    with db() as c:
        c.execute('INSERT OR IGNORE INTO settings(user_id) VALUES(?)',(user['id'],))
        if paperless_token:
            save_secrets(user['id'],paperless_token=paperless_token)
        c.execute("""UPDATE settings SET paperless_enabled=?,paperless_url=?,paperless_auto_upload=?,paperless_default_tags=? WHERE user_id=?""",
                  (1 if paperless_enabled else 0,paperless_url.strip().rstrip('/'),
                   1 if paperless_auto_upload else 0,paperless_default_tags,user['id']))
        if paperless_token: c.execute("UPDATE settings SET paperless_token='__secret_store__' WHERE user_id=?",(user['id'],))
    return RedirectResponse('/settings',303)

@app.get('/settings/paperless-test')
def settings_paperless_test(request:Request):
    user=require_user(request)
    with db() as c:
        row=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
    try:
        return paperless_test(dict(row) if row else {})
    except Exception as exc:
        return {'ok':False,'error':str(exc)}

@app.get('/users',response_class=HTMLResponse)
def users_get(request:Request):
    user=require_user(request)
    if not user['is_admin']: raise HTTPException(403)
    with db() as c: users=c.execute('SELECT id,username,display_name,role,is_admin,active,created_at FROM users ORDER BY username').fetchall()
    return templates.TemplateResponse('users.html',ctx(request,users=users,error=None))
@app.post('/users')
def users_add(request:Request,username:str=Form(...),display_name:str=Form(...),password:str=Form(...),is_admin:int=Form(0),role:str=Form('manager')):
    user=require_write(request)
    if not user['is_admin']: raise HTTPException(403)
    if role not in {'manager','viewer'}: raise HTTPException(400,'Ungültige Rolle')
    if len(password)<8:
        with db() as c: users=c.execute('SELECT id,username,display_name,role,is_admin,active,created_at FROM users ORDER BY username').fetchall()
        return templates.TemplateResponse('users.html',ctx(request,users=users,error='Das Passwort muss mindestens 8 Zeichen haben.'),status_code=400)
    try:
        with db() as c:
            cur=c.execute('INSERT INTO users(username,display_name,password_hash,role,is_admin) VALUES(?,?,?,?,?)',(username.strip(),display_name.strip(),hash_password(password),role,is_admin))
            c.execute('INSERT INTO settings(user_id,landlord_name,landlord_address,landlord_email,landlord_phone,iban) VALUES(?,?,?,?,?,?)',(cur.lastrowid,'','','','',''))
    except Exception:
        with db() as c: users=c.execute('SELECT id,username,display_name,role,is_admin,active,created_at FROM users ORDER BY username').fetchall()
        return templates.TemplateResponse('users.html',ctx(request,users=users,error='Der Benutzername ist bereits vorhanden.'),status_code=400)
    return RedirectResponse('/users',303)
@app.post('/users/{uid}/toggle')
def user_toggle(uid:int,request:Request):
    user=require_write(request)
    if not user['is_admin'] or uid==user['id']: raise HTTPException(403)
    with db() as c: c.execute('UPDATE users SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?',(uid,))
    return RedirectResponse('/users',303)


@app.post('/users/{uid}/role')
def user_role_update(uid:int,request:Request,role:str=Form(...)):
    user=require_write(request)
    if not user['is_admin'] or uid==user['id']: raise HTTPException(403)
    if role not in {'manager','viewer'}: raise HTTPException(400)
    with db() as c:
        cur=c.execute('UPDATE users SET role=?,is_admin=0 WHERE id=?',(role,uid))
        if cur.rowcount==0: raise HTTPException(404)
    return RedirectResponse('/users',303)

UPLOAD_DIR=Path(os.getenv('NEBENKOSTEN_UPLOAD_DIR','/var/lib/nebenkostenabrechnung/uploads'))
ALLOWED_UPLOADS={'.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp','.webp','.txt','.csv'}

@app.get('/received-statements',response_class=HTMLResponse)
def received_statements(request:Request):
    user=require_user(request)
    with db() as c:
        docs=c.execute("""SELECT r.*,t.name tenant_name FROM received_statements r LEFT JOIN tenants t ON t.id=r.tenant_id
          WHERE r.user_id=? ORDER BY r.id DESC""",(user['id'],)).fetchall()
        tenants=c.execute('SELECT id,name FROM tenants WHERE user_id=? ORDER BY name',(user['id'],)).fetchall()
    return templates.TemplateResponse('received_statements.html',ctx(request,docs=docs,tenants=tenants,error=None))

@app.post('/received-statements/upload')
async def received_statement_upload(request:Request,document:UploadFile=File(...),tenant_id:int=Form(0)):
    user=require_write(request)
    original=Path(document.filename or 'dokument').name
    suffix=Path(original).suffix.lower()
    if suffix not in ALLOWED_UPLOADS:
        raise HTTPException(400,'Nicht unterstütztes Dateiformat')
    UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
    stored=f"{user['id']}_{uuid.uuid4().hex}{suffix}"
    target=UPLOAD_DIR/stored
    total=0
    with target.open('wb') as out:
        while chunk:=await document.read(1024*1024):
            total += len(chunk)
            if total > 25*1024*1024:
                target.unlink(missing_ok=True)
                raise HTTPException(413,'Datei ist größer als 25 MB')
            out.write(chunk)
    try:
        text,method=extract_text(target,document.content_type or '')
        parsed=parse_statement(text) if text else {'warnings':[method],'confidence':{},'overall_confidence':0,'cost_items':[]}
    except Exception as exc:
        text=''
        method='Fehler'
        parsed={'warnings':[f'Einlesen fehlgeschlagen: {exc}'],'confidence':{},'overall_confidence':0,'cost_items':[]}
    with db() as c:
        valid_tid=None
        if tenant_id:
            valid_tid=c.execute('SELECT id FROM tenants WHERE id=? AND user_id=?',(tenant_id,user['id'])).fetchone()
        cur=c.execute("""INSERT INTO received_statements(user_id,tenant_id,original_name,stored_name,content_type,extraction_method,extracted_text,parsed_json)
          VALUES(?,?,?,?,?,?,?,?)""",(user['id'],tenant_id if valid_tid else None,original,stored,document.content_type or '',method,text,dumps(parsed)))
    return RedirectResponse(f'/received-statements/{cur.lastrowid}',303)

@app.get('/received-statements/{rid}',response_class=HTMLResponse)
def received_statement_detail(rid:int,request:Request):
    user=require_user(request)
    with db() as c:
        doc=c.execute("""SELECT r.*,t.name tenant_name FROM received_statements r LEFT JOIN tenants t ON t.id=r.tenant_id
          WHERE r.id=? AND r.user_id=?""",(rid,user['id'])).fetchone()
        if not doc: raise HTTPException(404)
        tenants=c.execute('SELECT id,name FROM tenants WHERE user_id=? ORDER BY name',(user['id'],)).fetchall()
        all_docs=[]
        if doc['tenant_id']:
            all_docs=c.execute("""SELECT * FROM received_statements WHERE user_id=? AND tenant_id=? AND status<>'Abgelehnt' ORDER BY id""",(user['id'],doc['tenant_id'])).fetchall()
            meter_rows=c.execute('SELECT * FROM meters WHERE user_id=? AND tenant_id=? AND active=1 ORDER BY id',(user['id'],doc['tenant_id'])).fetchall()
            meter_data=[]
            for m in meter_rows:
                rs=c.execute('SELECT * FROM meter_readings WHERE meter_id=? ORDER BY reading_date,id',(m['id'],)).fetchall()
                meter_data.append({'meter':dict(m),'readings':[dict(x) for x in rs]})
        else:
            meter_data=[]
    parsed=json.loads(doc['parsed_json'] or '{}')
    comparison={'available':False,'items':[],'summary':'Für einen Vorjahresvergleich muss das Dokument einem Mieter zugeordnet sein.'}
    previous_rows=[x for x in all_docs if x['id']!=rid]
    if previous_rows:
        # Bevorzugt die zeitlich unmittelbar vorherige Abrechnung; Fallback auf letzte gespeicherte.
        current_start=str(parsed.get('period_start',''))
        candidates=[]
        for row in previous_rows:
            pjson=json.loads(row['parsed_json'] or '{}')
            candidates.append((str(pjson.get('period_start','')),row,pjson))
        older=[x for x in candidates if not current_start or x[0] < current_start]
        chosen=(sorted(older,key=lambda x:x[0])[-1] if older else candidates[-1])
        comparison=compare_statements(parsed,chosen[2]); comparison['previous_id']=chosen[1]['id']; comparison['previous_name']=chosen[1]['original_name']
    history_docs=[]
    for row in all_docs:
        history_docs.append({'id':row['id'],'name':row['original_name'],'parsed':json.loads(row['parsed_json'] or '{}')})
    history=build_history(parsed,history_docs) if history_docs else {'available':False,'rows':[],'titles':[]}
    report=build_analysis_report(parsed,comparison)
    consumption_check=compare_recognized_consumptions(parsed.get('consumptions',[]),meter_data,parsed.get('period_start'),parsed.get('period_end'))
    return templates.TemplateResponse('received_statement_detail.html',ctx(request,doc=doc,parsed=parsed,tenants=tenants,comparison=comparison,history=history,report=report,consumption_check=consumption_check))

@app.post('/received-statements/{rid}/review')
def received_statement_review(rid:int,request:Request,tenant_id:int=Form(0),status:str=Form('Zu prüfen'),notes:str=Form('')):
    user=require_write(request)
    if status not in {'Zu prüfen','Geprüft','Übernommen','Abgelehnt'}: raise HTTPException(400)
    with db() as c:
        if tenant_id and not c.execute('SELECT id FROM tenants WHERE id=? AND user_id=?',(tenant_id,user['id'])).fetchone():
            raise HTTPException(400)
        cur=c.execute('UPDATE received_statements SET tenant_id=?,status=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',(tenant_id or None,status,notes,rid,user['id']))
        if cur.rowcount==0: raise HTTPException(404)
    return RedirectResponse(f'/received-statements/{rid}',303)

@app.post('/received-statements/{rid}/reanalyze')
def received_statement_reanalyze(rid:int,request:Request):
    user=require_write(request)
    with db() as c:
        doc=c.execute('SELECT * FROM received_statements WHERE id=? AND user_id=?',(rid,user['id'])).fetchone()
        if not doc: raise HTTPException(404)
    parsed=parse_statement(doc['extracted_text'] or '') if doc['extracted_text'] else {'analysis_version':'1.2','warnings':['Kein erkannter Text vorhanden.'],'confidence':{},'overall_confidence':0,'cost_items':[],'checks':[],'anomalies':[]}
    with db() as c:
        c.execute('UPDATE received_statements SET parsed_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',(dumps(parsed),rid,user['id']))
    return RedirectResponse(f'/received-statements/{rid}',303)

@app.post('/received-statements/{rid}/edit-analysis')
async def received_statement_edit_analysis(rid:int,request:Request):
    user=require_write(request); form=await request.form()
    with db() as c:
        doc=c.execute('SELECT * FROM received_statements WHERE id=? AND user_id=?',(rid,user['id'])).fetchone()
        if not doc: raise HTTPException(404)
    parsed=json.loads(doc['parsed_json'] or '{}')
    for key in ('period_start','period_end'):
        value=str(form.get(key,'')).strip()
        if value: parsed[key]=value
        else: parsed.pop(key,None)
    for key in ('total_cost','tenant_total','advance_payments','balance'):
        value=str(form.get(key,'')).strip().replace(',','.')
        if value:
            try: parsed[key]=round(float(value),2)
            except ValueError: raise HTTPException(400,f'Ungültiger Betrag: {key}')
        else: parsed.pop(key,None)
    items=[]
    try: count=int(form.get('item_count','0'))
    except ValueError: count=0
    for i in range(max(0,min(count,100))):
        if str(form.get(f'item_delete_{i}',''))=='1': continue
        title=str(form.get(f'item_title_{i}','')).strip()
        if not title: continue
        row={'title':title[:120],'source':'manuell korrigiert','confidence':1.0}
        for key in ('total_amount','tenant_share'):
            value=str(form.get(f'item_{key}_{i}','')).strip().replace(',','.')
            if value:
                try: row[key]=round(float(value),2)
                except ValueError: raise HTTPException(400,'Ungültiger Betrag in Kostenposition')
        allocation=str(form.get(f'item_allocation_key_{i}','')).strip()
        if allocation: row['allocation_key']=allocation[:80]
        items.append(row)
    parsed['cost_items']=items; parsed['manually_corrected']=True
    parsed=recalculate_analysis(parsed)
    with db() as c: c.execute('UPDATE received_statements SET parsed_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',(dumps(parsed),rid,user['id']))
    return RedirectResponse(f'/received-statements/{rid}',303)

@app.post('/received-statements/{rid}/ai-analyze')
def received_statement_ai_analyze(rid:int,request:Request):
    user=require_write(request)
    with db() as c:
        doc=c.execute('SELECT * FROM received_statements WHERE id=? AND user_id=?',(rid,user['id'])).fetchone()
        settings=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
        if not doc: raise HTTPException(404)
    try:
        ai=analyze_with_provider(doc['extracted_text'] or '',hydrate_settings(settings))
        parsed=merge_ai_analysis(json.loads(doc['parsed_json'] or '{}'),ai)
        parsed.setdefault('warnings',[]).append('KI-Analyse wurde ausgeführt; Werte bitte vor Übernahme prüfen.')
    except Exception as exc:
        parsed=json.loads(doc['parsed_json'] or '{}'); parsed.setdefault('warnings',[]).append(f'KI-Analyse fehlgeschlagen: {exc}')
    with db() as c: c.execute('UPDATE received_statements SET parsed_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',(dumps(parsed),rid,user['id']))
    return RedirectResponse(f'/received-statements/{rid}',303)

@app.get('/received-statements/{rid}/file')
def received_statement_file(rid:int,request:Request):
    user=require_user(request)
    with db() as c: doc=c.execute('SELECT * FROM received_statements WHERE id=? AND user_id=?',(rid,user['id'])).fetchone()
    if not doc: raise HTTPException(404)
    path=UPLOAD_DIR/doc['stored_name']
    if not path.exists(): raise HTTPException(404)
    return FileResponse(path,media_type=doc['content_type'] or 'application/octet-stream',filename=doc['original_name'])

# ---- Version 1.5: Dokumentenverwaltung, Backup/Wiederherstellung und Updateprüfung ----
DOCUMENT_DIR=Path(os.getenv('NEBENKOSTEN_DOCUMENT_DIR','/var/lib/nebenkostenabrechnung/documents'))
CSV_PREVIEW_DIR=Path(os.getenv('NEBENKOSTEN_CSV_PREVIEW_DIR','/var/lib/nebenkostenabrechnung/csv-previews'))
MAX_DOCUMENT_SIZE=25*1024*1024

@app.get('/documents',response_class=HTMLResponse)
def documents_list(request:Request,tax_year:int=0,property_id:int=0):
    user=require_user(request)
    from datetime import date
    if not tax_year:
        tax_year=date.today().year
    with db() as c:
        docs=[dict(x) for x in c.execute("""SELECT d.*,t.name tenant_name,p.name property_name,e.description tax_entry_description,e.amount tax_entry_amount
                          FROM documents d
                          LEFT JOIN tenants t ON t.id=d.tenant_id
                          LEFT JOIN properties p ON p.id=d.property_id
                          LEFT JOIN tax_entries e ON e.id=d.tax_entry_id
                          WHERE d.user_id=? ORDER BY d.id DESC""",(user['id'],)).fetchall()]
        for d in docs:
            try: d['receipt_ai']=json.loads(d.get('receipt_ai_json') or '{}')
            except Exception: d['receipt_ai']={}
        tenants=c.execute('SELECT id,name FROM tenants WHERE user_id=? ORDER BY name',(user['id'],)).fetchall()
        properties=c.execute('SELECT id,name FROM properties WHERE user_id=? ORDER BY name',(user['id'],)).fetchall()
        settings_row=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
        paperless_base_url=(settings_row['paperless_url'] if settings_row and settings_row['paperless_url'] else '').rstrip('/')
        tax_entries=c.execute("""SELECT e.id,e.property_id,e.tax_year,e.entry_date,e.entry_type,e.category,e.description,e.amount,p.name property_name
                                 FROM tax_entries e JOIN properties p ON p.id=e.property_id
                                 WHERE e.user_id=? AND e.tax_year=? ORDER BY p.name,e.entry_date,e.id""",(user['id'],tax_year)).fetchall()
    return templates.TemplateResponse('documents.html',ctx(request,docs=docs,tenants=tenants,properties=properties,tax_entries=tax_entries,tax_year=tax_year,property_id=property_id,paperless_base_url=paperless_base_url))

@app.post('/documents/upload')
async def document_upload(request:Request,title:str=Form(...),category:str=Form('Sonstiges'),tenant_id:int=Form(0),
                          property_id:int=Form(0),tax_year:int=Form(0),tax_entry_id:int=Form(0),
                          send_paperless:int=Form(0),run_ai:int=Form(0),notes:str=Form(''),document:UploadFile=File(...)):
    user=require_write(request)
    original=Path(document.filename or 'dokument').name
    content=await document.read(MAX_DOCUMENT_SIZE+1)
    if len(content)>MAX_DOCUMENT_SIZE:
        raise HTTPException(413,'Datei ist größer als 25 MB.')
    with db() as c:
        valid_tenant=None
        if tenant_id:
            valid_tenant=c.execute('SELECT id FROM tenants WHERE id=? AND user_id=?',(tenant_id,user['id'])).fetchone()
            if not valid_tenant: raise HTTPException(404)
        if property_id and not c.execute('SELECT id FROM properties WHERE id=? AND user_id=?',(property_id,user['id'])).fetchone():
            raise HTTPException(404)
        if tax_entry_id:
            valid_entry=c.execute('SELECT id,property_id,tax_year FROM tax_entries WHERE id=? AND user_id=?',(tax_entry_id,user['id'])).fetchone()
            if not valid_entry: raise HTTPException(404)
            property_id=int(valid_entry['property_id']); tax_year=int(valid_entry['tax_year'])
        settings_row=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
        settings_dict=hydrate_settings(settings_row)
    DOCUMENT_DIR.mkdir(parents=True,exist_ok=True)
    stored=f'{user["id"]}-{uuid.uuid4().hex}{Path(original).suffix.lower()}'
    target=DOCUMENT_DIR/stored
    target.write_bytes(content)

    # Beleganalyse erzeugt ausschließlich Vorschläge; Zuordnungen werden erst nach Bestätigung übernommen.
    ai_suggestion={}
    text=''
    try:
        text,_method=extract_text(target,document.content_type or '')
        ai_suggestion=suggest_receipt_metadata(text,original)
        if run_ai and settings_dict.get('ai_provider') and settings_dict.get('ai_provider')!='none' and text:
            try:
                provider_result=analyze_receipt_with_provider(text,settings_dict)
                ai_suggestion={**ai_suggestion,**{k:v for k,v in provider_result.items() if v not in (None,'',[])},'analysis_mode':'ki'}
            except Exception as exc:
                ai_suggestion['ai_error']=str(exc)
                ai_suggestion['analysis_mode']='lokal'
        else:
            ai_suggestion['analysis_mode']='lokal'
        with db() as c:
            props=[dict(x) for x in c.execute('SELECT id,name,address FROM properties WHERE user_id=?',(user['id'],)).fetchall()]
            matched_prop=match_property(props,ai_suggestion,text)
            if matched_prop:
                ai_suggestion['suggested_property_id']=matched_prop['id']
                ai_suggestion['suggested_property_name']=matched_prop['name']
                year=tax_year
                if not year:
                    raw_date=str(ai_suggestion.get('document_date') or ai_suggestion.get('date') or '')
                    ym=re.search(r'(20\d{2})',raw_date)
                    if ym: year=int(ym.group(1))
                entries=[dict(x) for x in c.execute("""SELECT id,property_id,tax_year,category,description,amount FROM tax_entries
                                                       WHERE user_id=? AND property_id=? AND (?=0 OR tax_year=?)""",
                                                    (user['id'],matched_prop['id'],year,year)).fetchall()]
                matched_entry=match_tax_entry(entries,ai_suggestion)
                if matched_entry:
                    ai_suggestion['suggested_tax_entry_id']=matched_entry['id']
                    ai_suggestion['suggested_tax_entry_description']=matched_entry.get('description') or matched_entry.get('category')
                    ai_suggestion['suggested_tax_year']=matched_entry['tax_year']
    except Exception as exc:
        ai_suggestion={'error':str(exc),'analysis_mode':'Fehler'}

    paperless_task=None
    paperless_status=''
    if settings_dict.get('paperless_enabled') and (send_paperless or settings_dict.get('paperless_auto_upload')):
        try:
            tags=[x.strip() for x in (settings_dict.get('paperless_default_tags') or '').split(',') if x.strip()]
            uploaded=paperless_upload(settings_dict,target,title=title.strip(),tags=tags)
            paperless_task=str(uploaded.get('task_id') or '')
            paperless_status='eingereiht'
        except Exception as exc:
            paperless_status='Fehler: '+str(exc)[:240]

    with db() as c:
        c.execute("""INSERT INTO documents(user_id,tenant_id,title,category,filename,stored_name,content_type,notes,property_id,tax_year,tax_entry_id,
                                            paperless_task_id,paperless_status,receipt_ai_json)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (user['id'],tenant_id or None,title.strip(),category,original,stored,document.content_type or '',notes,
                   property_id or None,tax_year or None,tax_entry_id or None,paperless_task,paperless_status,
                   json.dumps(ai_suggestion,ensure_ascii=False)))
    return RedirectResponse(f'/documents?tax_year={tax_year or ""}',303)

@app.get('/documents/{did}/download')
def document_download(did:int,request:Request):
    user=require_user(request)
    with db() as c: row=c.execute('SELECT * FROM documents WHERE id=? AND user_id=?',(did,user['id'])).fetchone()
    if not row: raise HTTPException(404)
    if row['stored_name']:
        path=(DOCUMENT_DIR/(row['stored_name'] or '')).resolve()
        if DOCUMENT_DIR.resolve() in path.parents and path.is_file():
            return FileResponse(path,filename=row['filename'] or row['title'],media_type=row['content_type'] or 'application/octet-stream')
    if row['paperless_document_id']:
        with db() as c: settings_row=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
        try:
            downloaded=paperless_download(hydrate_settings(settings_row),int(row['paperless_document_id']))
            return Response(downloaded['data'],media_type=downloaded['content_type'],
                            headers={'Content-Disposition':f'attachment; filename="{Path(downloaded["filename"]).name}"'})
        except Exception as exc:
            raise HTTPException(502,f'Paperless-Download fehlgeschlagen: {exc}')
    raise HTTPException(404)

@app.post('/documents/{did}/tax-link')
def document_tax_link(did:int,request:Request,property_id:int=Form(0),tax_year:int=Form(0),tax_entry_id:int=Form(0)):
    user=require_write(request)
    with db() as c:
        doc=c.execute('SELECT id FROM documents WHERE id=? AND user_id=?',(did,user['id'])).fetchone()
        if not doc: raise HTTPException(404)
        if property_id and not c.execute('SELECT id FROM properties WHERE id=? AND user_id=?',(property_id,user['id'])).fetchone():
            raise HTTPException(404)
        if tax_entry_id:
            row=c.execute('SELECT property_id,tax_year FROM tax_entries WHERE id=? AND user_id=?',(tax_entry_id,user['id'])).fetchone()
            if not row: raise HTTPException(404)
            property_id=int(row['property_id']); tax_year=int(row['tax_year'])
        c.execute('UPDATE documents SET property_id=?,tax_year=?,tax_entry_id=? WHERE id=? AND user_id=?',
                  (property_id or None,tax_year or None,tax_entry_id or None,did,user['id']))
    return RedirectResponse(f'/documents?tax_year={tax_year or 0}',303)

@app.post('/documents/{did}/paperless-sync')
def document_paperless_sync(did:int,request:Request):
    user=require_write(request)
    with db() as c:
        doc=c.execute('SELECT * FROM documents WHERE id=? AND user_id=?',(did,user['id'])).fetchone()
        settings_row=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
    if not doc: raise HTTPException(404)
    settings_dict=hydrate_settings(settings_row)
    status=''
    document_id=doc['paperless_document_id']
    try:
        if doc['paperless_task_id']:
            info=paperless_task_status(settings_dict,doc['paperless_task_id'])
            status=str(info.get('status') or ('ok' if info.get('ok') else info.get('error') or ''))
            if info.get('document_id'):
                try: document_id=int(info['document_id'])
                except Exception: pass
        elif doc['stored_name']:
            path=(DOCUMENT_DIR/doc['stored_name']).resolve()
            if DOCUMENT_DIR.resolve() not in path.parents or not path.is_file(): raise HTTPException(404)
            tags=[x.strip() for x in (settings_dict.get('paperless_default_tags') or '').split(',') if x.strip()]
            up=paperless_upload(settings_dict,path,title=doc['title'] or '',tags=tags)
            task=str(up.get('task_id') or '')
            with db() as c:
                c.execute('UPDATE documents SET paperless_task_id=?,paperless_status=? WHERE id=? AND user_id=?',
                          (task,'eingereiht',did,user['id']))
            return RedirectResponse('/documents',303)
    except Exception as exc:
        status='Fehler: '+str(exc)[:240]
    with db() as c:
        c.execute('UPDATE documents SET paperless_document_id=?,paperless_status=? WHERE id=? AND user_id=?',
                  (document_id,status,did,user['id']))
    return RedirectResponse('/documents',303)

@app.post('/documents/{did}/apply-ai')
def document_apply_ai(did:int,request:Request):
    user=require_write(request)
    with db() as c:
        doc=c.execute('SELECT * FROM documents WHERE id=? AND user_id=?',(did,user['id'])).fetchone()
        if not doc: raise HTTPException(404)
        try: suggestion=json.loads(doc['receipt_ai_json'] or '{}')
        except Exception: suggestion={}
        pid=int(suggestion.get('suggested_property_id') or 0)
        eid=int(suggestion.get('suggested_tax_entry_id') or 0)
        year=int(suggestion.get('suggested_tax_year') or doc['tax_year'] or 0)
        if eid:
            er=c.execute('SELECT property_id,tax_year FROM tax_entries WHERE id=? AND user_id=?',(eid,user['id'])).fetchone()
            if not er: raise HTTPException(404)
            pid=int(er['property_id']); year=int(er['tax_year'])
        elif pid and not c.execute('SELECT id FROM properties WHERE id=? AND user_id=?',(pid,user['id'])).fetchone():
            raise HTTPException(404)
        c.execute('UPDATE documents SET property_id=?,tax_year=?,tax_entry_id=?,review_status=? WHERE id=? AND user_id=?',
                  (pid or None,year or None,eid or None,'zugeordnet',did,user['id']))
    return RedirectResponse(f'/documents?tax_year={year or 0}',303)

@app.get('/documents/paperless-search',response_class=HTMLResponse)
def documents_paperless_search(request:Request,q:str='',tax_year:int=0,property_id:int=0):
    user=require_user(request)
    with db() as c:
        settings_row=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
        properties=c.execute('SELECT id,name FROM properties WHERE user_id=? ORDER BY name',(user['id'],)).fetchall()
        tax_entries=c.execute("""SELECT e.id,e.property_id,e.tax_year,e.description,e.amount,p.name property_name
                                 FROM tax_entries e JOIN properties p ON p.id=e.property_id
                                 WHERE e.user_id=? AND (?=0 OR e.tax_year=?) ORDER BY p.name,e.entry_date,e.id""",
                              (user['id'],tax_year,tax_year)).fetchall()
    results=[]; error=None
    if q.strip():
        try: results=paperless_search(hydrate_settings(settings_row),q.strip(),30).get('results',[])
        except Exception as exc: error=str(exc)
    return templates.TemplateResponse('paperless_search.html',ctx(request,q=q,results=results,error=error,
        properties=properties,tax_entries=tax_entries,tax_year=tax_year,property_id=property_id))

@app.post('/documents/paperless-link')
def documents_paperless_link(request:Request,paperless_document_id:int=Form(...),property_id:int=Form(0),
                             tax_year:int=Form(0),tax_entry_id:int=Form(0)):
    user=require_write(request)
    with db() as c:
        settings_row=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
        if property_id and not c.execute('SELECT id FROM properties WHERE id=? AND user_id=?',(property_id,user['id'])).fetchone():
            raise HTTPException(404)
        if tax_entry_id:
            er=c.execute('SELECT property_id,tax_year FROM tax_entries WHERE id=? AND user_id=?',(tax_entry_id,user['id'])).fetchone()
            if not er: raise HTTPException(404)
            property_id=int(er['property_id']); tax_year=int(er['tax_year'])
        existing=c.execute('SELECT id FROM documents WHERE user_id=? AND paperless_document_id=?',(user['id'],paperless_document_id)).fetchone()
        if existing:
            c.execute('UPDATE documents SET property_id=?,tax_year=?,tax_entry_id=? WHERE id=?',
                      (property_id or None,tax_year or None,tax_entry_id or None,existing['id']))
            return RedirectResponse(f'/documents?tax_year={tax_year or 0}',303)
    try:
        meta=paperless_get_document(hydrate_settings(settings_row),paperless_document_id)
    except Exception as exc:
        raise HTTPException(502,f'Paperless-Dokument konnte nicht gelesen werden: {exc}')
    title=str(meta.get('title') or f'Paperless Dokument {paperless_document_id}')
    created=str(meta.get('created') or '')
    original=str(meta.get('original_file_name') or meta.get('archived_file_name') or f'paperless-{paperless_document_id}')
    with db() as c:
        c.execute("""INSERT INTO documents(user_id,title,category,filename,stored_name,content_type,notes,property_id,tax_year,tax_entry_id,
                                            paperless_document_id,paperless_status)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (user['id'],title,'Beleg',Path(original).name,None,'','Aus bestehendem Paperless-Archiv verknüpft',
                   property_id or None,tax_year or None,tax_entry_id or None,paperless_document_id,'verknüpft'))
    return RedirectResponse(f'/documents?tax_year={tax_year or 0}',303)

@app.post('/documents/{did}/review-status')
def document_review_status(did:int,request:Request,status:str=Form(...)):
    user=require_write(request)
    if status not in {'neu','geprüft','zugeordnet','erledigt'}: raise HTTPException(400)
    with db() as c:
        cur=c.execute('UPDATE documents SET review_status=? WHERE id=? AND user_id=?',(status,did,user['id']))
        if cur.rowcount==0: raise HTTPException(404)
    return RedirectResponse('/documents',303)

@app.post('/documents/{did}/delete')
def document_delete(did:int,request:Request):
    user=require_write(request)
    with db() as c:
        row=c.execute('SELECT * FROM documents WHERE id=? AND user_id=?',(did,user['id'])).fetchone()
        if not row: raise HTTPException(404)
        c.execute('DELETE FROM documents WHERE id=? AND user_id=?',(did,user['id']))
    if row['stored_name']:
        path=DOCUMENT_DIR/row['stored_name']
        try: path.unlink(missing_ok=True)
        except Exception: pass
    return RedirectResponse('/documents',303)


def _backup_rows():
    from .backup import list_backups
    rows=[]
    for p in list_backups():
        size=p.stat().st_size
        rows.append({'name':p.name,'size':f'{size/1024/1024:.2f} MB' if size>=1024*1024 else f'{size/1024:.1f} KB'})
    return rows

@app.get('/system/diagnostics',response_class=HTMLResponse)
def system_diagnostics(request:Request):
    user=require_user(request)
    if not user['is_admin']: raise HTTPException(403)
    from .backup import BACKUP_DIR, UPLOAD_DIR as B_UPLOAD_DIR, DOCUMENT_DIR as B_DOCUMENT_DIR, SECRET_DIR, list_backups, validate_backup
    from . import database
    with db() as c:
        settings_row=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone()
    settings=hydrate_settings(settings_row)
    checks,summary=production_checks(database.DB_PATH,B_UPLOAD_DIR,B_DOCUMENT_DIR,BACKUP_DIR,SECRET_DIR,settings)
    session_default=os.getenv('NEBENKOSTEN_SESSION_SECRET','change-this-secret-in-production')=='change-this-secret-in-production'
    checks.append({'key':'session_secret','label':'Session-Secret','ok':not session_default,
                   'detail':'Standardwert ist noch aktiv' if session_default else 'individuell gesetzt',
                   'level':'error' if session_default else 'ok'})
    backups=list_backups()
    latest=None
    if backups:
        ok,msg=validate_backup(backups[0])
        latest={'name':backups[0].name,'ok':ok,'detail':msg or 'Backup ist strukturell und per SQLite-Integritätsprüfung gültig.'}
        if not ok: summary['error']+=1; summary['ready']=False
    summary['ok']=sum(1 for c in checks if c['level']=='ok')
    summary['warn']=sum(1 for c in checks if c['level']=='warn')
    summary['error']=sum(1 for c in checks if c['level']=='error')+(0 if not latest or latest['ok'] else 1)
    summary['ready']=summary['error']==0
    return templates.TemplateResponse('diagnostics.html',ctx(request,checks=checks,summary=summary,latest_backup=latest))

@app.get('/system',response_class=HTMLResponse)
def system_page(request:Request):
    require_user(request)
    return templates.TemplateResponse('system.html',ctx(request,backups=_backup_rows(),version='2.9.1',message=None,error=None,update=None))

@app.post('/system/backup',response_class=HTMLResponse)
def system_backup(request:Request):
    require_write(request)
    from .backup import create_backup
    path=create_backup()
    return templates.TemplateResponse('system.html',ctx(request,backups=_backup_rows(),version='2.9.1',message=f'Backup {path.name} wurde erstellt.',error=None,update=None))

@app.get('/system/backups/{name}')
def system_backup_download(name:str,request:Request):
    require_user(request)
    from .backup import BACKUP_DIR, _safe_name
    safe=_safe_name(Path(name).name)
    path=(BACKUP_DIR/safe).resolve()
    if BACKUP_DIR.resolve() not in path.parents or not path.is_file(): raise HTTPException(404)
    return FileResponse(path,filename=path.name,media_type='application/zip')

@app.post('/system/restore/{name}',response_class=HTMLResponse)
def system_restore(name:str,request:Request):
    user=require_write(request)
    if not user['is_admin']: raise HTTPException(403)
    from .backup import BACKUP_DIR, _safe_name, restore_backup
    path=BACKUP_DIR/_safe_name(Path(name).name)
    if not path.is_file(): raise HTTPException(404)
    try:
        safety=restore_backup(path)
        msg=f'Backup {path.name} wurde wiederhergestellt. Sicherheitsbackup: {safety.name}'
        err=None
    except Exception as e:
        msg=None; err=f'Wiederherstellung fehlgeschlagen: {e}'
    return templates.TemplateResponse('system.html',ctx(request,backups=_backup_rows(),version='2.9.1',message=msg,error=err,update=None))

@app.post('/system/restore-upload',response_class=HTMLResponse)
async def system_restore_upload(request:Request,backup:UploadFile=File(...)):
    user=require_write(request)
    if not user['is_admin']: raise HTTPException(403)
    from .backup import BACKUP_DIR, restore_backup
    data=await backup.read(250*1024*1024+1)
    if len(data)>250*1024*1024: raise HTTPException(413,'Backup ist zu groß.')
    BACKUP_DIR.mkdir(parents=True,exist_ok=True)
    path=BACKUP_DIR/f'upload-{uuid.uuid4().hex}.zip'; path.write_bytes(data)
    try:
        safety=restore_backup(path); msg=f'Backup wurde wiederhergestellt. Sicherheitsbackup: {safety.name}'; err=None
    except Exception as e:
        msg=None; err=f'Backup ungültig oder Wiederherstellung fehlgeschlagen: {e}'
    finally:
        try: path.unlink(missing_ok=True)
        except Exception: pass
    return templates.TemplateResponse('system.html',ctx(request,backups=_backup_rows(),version='2.9.1',message=msg,error=err,update=None))

@app.post('/system/check-update',response_class=HTMLResponse)
def system_check_update(request:Request):
    user=require_write(request)
    from .update_manager import check_github_release
    token=os.getenv('NEBENKOSTEN_GITHUB_TOKEN')
    try:
        update=check_github_release(token=token); err=None
    except Exception as e:
        update=None; err='GitHub-Release konnte nicht geprüft werden. Bei privatem Repository kann NEBENKOSTEN_GITHUB_TOKEN erforderlich sein.'
    return templates.TemplateResponse('system.html',ctx(request,backups=_backup_rows(),version='2.9.1',message=None,error=err,update=update))

# ---- Version 1.6: Zähler, E-Mail, SMB-Backup und Web-Update ----
@app.get('/meters',response_class=HTMLResponse)
def meters_page(request:Request):
    user=require_user(request)
    with db() as c:
        meters=c.execute("""SELECT m.*,t.name tenant_name,(SELECT value FROM meter_readings r WHERE r.meter_id=m.id ORDER BY reading_date DESC,id DESC LIMIT 1) last_value,(SELECT reading_date FROM meter_readings r WHERE r.meter_id=m.id ORDER BY reading_date DESC,id DESC LIMIT 1) last_date FROM meters m LEFT JOIN tenants t ON t.id=m.tenant_id WHERE m.user_id=? ORDER BY m.active DESC,m.name""",(user['id'],)).fetchall()
        tenants=c.execute('SELECT id,name FROM tenants WHERE user_id=? AND active=1 ORDER BY name',(user['id'],)).fetchall()
    return templates.TemplateResponse('meters.html',ctx(request,meters=meters,tenants=tenants))

@app.post('/meters')
def meter_add(request:Request,name:str=Form(...),meter_type:str=Form('Sonstiges'),meter_number:str=Form(''),unit:str=Form(''),tenant_id:int=Form(0),notes:str=Form('')):
    user=require_write(request)
    with db() as c:
        if tenant_id and not c.execute('SELECT id FROM tenants WHERE id=? AND user_id=?',(tenant_id,user['id'])).fetchone(): raise HTTPException(404)
        c.execute('INSERT INTO meters(user_id,tenant_id,name,meter_type,meter_number,unit,notes) VALUES(?,?,?,?,?,?,?)',(user['id'],tenant_id or None,name,meter_type,meter_number,unit,notes))
    return RedirectResponse('/meters',303)

@app.get('/meters/{mid}',response_class=HTMLResponse)
def meter_detail(mid:int,request:Request):
    user=require_user(request)
    with db() as c:
        meter=c.execute('SELECT m.*,t.name tenant_name FROM meters m LEFT JOIN tenants t ON t.id=m.tenant_id WHERE m.id=? AND m.user_id=?',(mid,user['id'])).fetchone()
        if not meter: raise HTTPException(404)
        readings=c.execute('SELECT * FROM meter_readings WHERE meter_id=? ORDER BY reading_date ASC,id ASC',(mid,)).fetchall()
    rows=[]; prev=None
    for r in readings:
        d=dict(r); d['consumption']=None if prev is None else round(r['value']-prev,3); prev=r['value']; rows.append(d)
    history=yearly_consumption(readings)
    chart=chart_points(readings)
    rows.reverse()
    return templates.TemplateResponse('meter_detail.html',ctx(request,meter=meter,readings=rows,history=history,chart=chart))

@app.post('/meters/{mid}/reading')
def meter_reading_add(mid:int,request:Request,reading_date:str=Form(...),value:float=Form(...),notes:str=Form('')):
    user=require_write(request)
    with db() as c:
        if not c.execute('SELECT id FROM meters WHERE id=? AND user_id=?',(mid,user['id'])).fetchone(): raise HTTPException(404)
        c.execute('INSERT INTO meter_readings(meter_id,reading_date,value,notes) VALUES(?,?,?,?)',(mid,reading_date,value,notes))
    return RedirectResponse(f'/meters/{mid}',303)

@app.post('/meters/{mid}/delete')
def meter_delete(mid:int,request:Request):
    user=require_write(request)
    with db() as c:
        if not c.execute('SELECT id FROM meters WHERE id=? AND user_id=?',(mid,user['id'])).fetchone(): raise HTTPException(404)
        c.execute('DELETE FROM meters WHERE id=?',(mid,))
    return RedirectResponse('/meters',303)

@app.post('/statement/{sid}/email')
def statement_email(sid:int,request:Request,recipient:str=Form(...),subject:str=Form('Nebenkostenabrechnung'),message:str=Form('Anbei erhalten Sie Ihre Nebenkostenabrechnung.')):
    user=require_write(request)
    with db() as c:
        st=owns_statement(c,sid,user['id'])
        if not st: raise HTTPException(404)
        tenant=c.execute('SELECT * FROM tenants WHERE id=? AND user_id=?',(st['tenant_id'],user['id'])).fetchone(); settings=c.execute('SELECT * FROM settings WHERE user_id=?',(user['id'],)).fetchone(); costs=c.execute('SELECT * FROM costs WHERE statement_id=? ORDER BY id',(sid,)).fetchall()
    from .email_service import send_email
    pdf=build_statement_pdf(settings,tenant,st,costs).getvalue(); send_email(hydrate_settings(settings),recipient,subject,message,pdf,f'Nebenkostenabrechnung_{sid}.pdf')
    return RedirectResponse(f'/statement/{sid}',303)

@app.post('/system/backup-smb',response_class=HTMLResponse)
def system_backup_smb(request:Request):
    require_write(request)
    from .backup import create_backup,copy_backup_to_smb
    try:
        path=create_backup('nas'); remote=copy_backup_to_smb(path); msg=f'Backup wurde nach {remote} übertragen.'; err=None
    except Exception as exc: msg=None; err=f'NAS-Backup fehlgeschlagen: {exc}'
    return templates.TemplateResponse('system.html',ctx(request,backups=_backup_rows(),version='2.9.1',message=msg,error=err,update=None))

@app.post('/system/install-update',response_class=HTMLResponse)
def system_install_update(request:Request):
    user=require_write(request)
    if not user['is_admin']: raise HTTPException(403)
    from .update_manager import stage_latest_deb,install_staged_deb
    try:
        path,rel=stage_latest_deb(os.getenv('NEBENKOSTEN_GITHUB_TOKEN')); install_staged_deb(path); msg=f'Update auf {rel["latest"]} wurde angestoßen.'; err=None
    except Exception as exc: msg=None; err=f'Update fehlgeschlagen: {exc}'
    return templates.TemplateResponse('system.html',ctx(request,backups=_backup_rows(),version='2.9.1',message=msg,error=err,update=None))
