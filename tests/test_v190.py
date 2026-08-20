from app.pdf import build_tax_advisor_pdf

def test_tax_advisor_pdf():
    settings={'landlord_name':'Test Vermieter','landlord_address':'Musterweg 1'}
    props=[{'name':'Haus A','address':'Musterweg 1','statements':[{'tenant_name':'Mieter A','period_start':'2025-01-01','period_end':'2025-12-31','advance_payments':1200,'allocated_costs':1100,'balance':-100}], 'cost_categories':[{'title':'Wasser','total_cost':2000,'tenant_share':400}], 'tax_entries':[{'entry_date':'2025-03-01','entry_type':'income','category':'rent','description':'Miete','amount':9000,'tax_treatment':'review'},{'entry_date':'2025-04-01','entry_type':'expense','category':'repairs','description':'Heizung','amount':500,'tax_treatment':'potentially_deductible'}]}]
    out=build_tax_advisor_pdf(settings,2025,props)
    data=out.read()
    assert data.startswith(b'%PDF')
    assert len(data)>1000
