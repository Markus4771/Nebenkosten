from app.document_ai import merge_ai_analysis, recalculate_analysis

def test_manual_recalculation():
    x=recalculate_analysis({'tenant_total':100,'advance_payments':80,'balance':20,'cost_items':[{'title':'Wasser','tenant_share':100}]})
    assert x['analysis_version']=='1.8'
    assert all(c['ok'] for c in x['checks'])

def test_merge_ai_analysis():
    base={'cost_items':[]}
    ai={'ai_provider':'ollama','ai_model':'gemma3','tenant_total':42,'cost_items':[{'title':'Müll','tenant_share':42}]}
    x=merge_ai_analysis(base,ai)
    assert x['ai_analyzed'] is True
    assert x['cost_items'][0]['title']=='Müll'
