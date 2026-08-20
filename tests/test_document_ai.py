from app.document_ai import parse_statement, compare_statements, build_analysis_report, build_history

def test_parse_statement_basics():
    data=parse_statement("Abrechnungszeitraum 01.01.2025 bis 31.12.2025\nVorauszahlungen 1.200,00 €\nNachzahlung 245,50 €\nHeizkosten 800,00 €")
    assert data["period_start"]=="01.01.2025"
    assert data["advance_payments"]==1200.0
    assert data["balance"]==245.5
    assert data["cost_items"]

def test_cost_line_total_and_tenant_share():
    data=parse_statement("Heizkosten Wohnfläche 2.400,00 € 620,00 €")
    item=data['cost_items'][0]
    assert item['total_amount']==2400.0
    assert item['tenant_share']==620.0
    assert item['allocation_key']=='Wohnfläche'

def test_compare_flags_large_change():
    previous={'cost_items':[{'title':'Heizkosten','tenant_share':500.0}]}
    current={'cost_items':[{'title':'Heizkosten','tenant_share':800.0}]}
    result=compare_statements(current,previous)
    assert result['available']
    assert result['items'][0]['percent']==60.0
    assert result['items'][0]['severity']=='hoch'


def test_multiline_table_reconstruction():
    data=parse_statement("Heizkosten Wohnfläche\n2.400,00 € 620,00 €\nMüll Personen\n400,00 € 110,00 €")
    by_title={x['title']:x for x in data['cost_items']}
    assert by_title['Heizkosten']['tenant_share']==620.0
    assert by_title['Müll']['tenant_share']==110.0

def test_analysis_report_and_history():
    current={'tenant_total':100,'advance_payments':80,'balance':20,'cost_items':[{'title':'Heizkosten','tenant_share':100}], 'checks':[], 'warnings':[], 'anomalies':[]}
    comparison=compare_statements(current,{'cost_items':[{'title':'Heizkosten','tenant_share':50}]})
    report=build_analysis_report(current,comparison)
    assert any('Heizkosten' in x['text'] for x in report['findings'])
    history=build_history(current,[{'id':1,'name':'2024','parsed':{'period_start':'01.01.2024','cost_items':[{'title':'Heizkosten','tenant_share':50}]}},{'id':2,'name':'2025','parsed':{'period_start':'01.01.2025','cost_items':[{'title':'Heizkosten','tenant_share':100}]}}])
    assert history['available'] is True
    assert history['titles']==['Heizkosten']
