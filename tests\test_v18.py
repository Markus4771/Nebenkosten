import json
from app.ai_provider import _openrouter_headers
from app.document_ai import merge_ai_analysis
from app.meter_analysis import compare_recognized_consumptions


def test_openrouter_headers():
    h=_openrouter_headers({'ai_api_key':'secret','ai_referer':'https://example.test','ai_app_title':'Nebenkosten'})
    assert h['Authorization']=='Bearer secret'
    assert h['HTTP-Referer']=='https://example.test'
    assert h['X-OpenRouter-Title']=='Nebenkosten'


def test_merge_ai_consumptions():
    x=merge_ai_analysis({}, {'ai_provider':'openrouter','ai_model':'vendor/model','consumptions':[{'type':'Kaltwasser','value':'48.37','unit':'m³'}]})
    assert x['consumptions'][0]['value']==48.37
    assert x['analysis_version']=='1.8'


def test_compare_recognized_consumption():
    rec=[{'type':'Kaltwasser','value':48.0,'unit':'m³','period_start':'2025-01-01','period_end':'2025-12-31'}]
    meter_data=[{'meter':{'name':'Wasser Bad','meter_type':'Kaltwasser','unit':'m³','meter_number':'A1'},'readings':[{'id':1,'reading_date':'2025-01-01','value':100},{'id':2,'reading_date':'2025-12-31','value':150}]}]
    r=compare_recognized_consumptions(rec,meter_data,'2025-01-01','2025-12-31')
    assert r['available']
    assert r['items'][0]['own']==50.0
    assert r['items'][0]['status']=='plausibel'
