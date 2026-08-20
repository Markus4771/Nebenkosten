import json
import urllib.parse
import urllib.request
from typing import Any


def _request(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 90) -> dict[str, Any]:
    data=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    h={'Content-Type':'application/json'}
    if headers: h.update(headers)
    req=urllib.request.Request(url,data=data,headers=h,method='POST')
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> dict[str, Any]:
    req=urllib.request.Request(url,headers=headers or {},method='GET')
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _openrouter_headers(settings: dict[str, Any]) -> dict[str,str]:
    key=(settings.get('ai_api_key') or '').strip()
    if not key: raise ValueError('OpenRouter API-Key fehlt.')
    headers={'Authorization':'Bearer '+key}
    referer=(settings.get('ai_referer') or '').strip()
    title=(settings.get('ai_app_title') or '').strip()
    if referer: headers['HTTP-Referer']=referer
    if title: headers['X-OpenRouter-Title']=title
    return headers


def list_provider_models(settings: dict[str, Any]) -> list[dict[str, Any]]:
    provider=(settings.get('ai_provider') or 'none').lower()
    base=(settings.get('ai_base_url') or '').strip().rstrip('/')
    key=(settings.get('ai_api_key') or '').strip()
    if provider=='openrouter':
        if not base: base='https://openrouter.ai/api/v1'
        out=_get_json(base+'/models',_openrouter_headers(settings))
        models=[]
        for row in out.get('data',[]):
            if not isinstance(row,dict) or not row.get('id'): continue
            models.append({'id':str(row['id']),'name':str(row.get('name') or row['id']),'context_length':row.get('context_length')})
        return sorted(models,key=lambda x:(x['name'].lower(),x['id']))
    if provider=='ollama':
        if not base: base='http://127.0.0.1:11434'
        out=_get_json(base+'/api/tags')
        return [{'id':str(x.get('name')),'name':str(x.get('name')),'context_length':None} for x in out.get('models',[]) if x.get('name')]
    if provider=='gemini':
        if not key:
            raise ValueError('Gemini API-Key fehlt.')
        if not base:
            base='https://generativelanguage.googleapis.com/v1beta'
        out=_get_json(base+'/models', {'x-goog-api-key': key})
        models=[]
        for row in out.get('models',[]):
            if not isinstance(row,dict) or not row.get('name'):
                continue
            methods=row.get('supportedGenerationMethods') or []
            if methods and 'generateContent' not in methods:
                continue
            mid=str(row['name']).removeprefix('models/')
            models.append({'id':mid,'name':str(row.get('displayName') or mid),'context_length':row.get('inputTokenLimit')})
        return sorted(models,key=lambda x:(x['name'].lower(),x['id']))
    raise ValueError('Modellliste wird für diesen Provider nicht automatisch abgerufen.')


def test_provider(settings: dict[str, Any]) -> dict[str, Any]:
    provider=(settings.get('ai_provider') or 'none').lower()
    if provider=='none': raise ValueError('Kein KI-Provider konfiguriert.')
    if provider in {'openrouter','ollama','gemini'}:
        models=list_provider_models(settings)
        return {'ok':True,'provider':provider,'models':len(models),'message':f'Verbindung erfolgreich, {len(models)} Modelle gefunden.'}
    # Für Provider ohne Modell-Endpoint reicht eine kleine echte Analyseanfrage nicht aus Datenschutzgründen.
    return {'ok':True,'provider':provider,'models':None,'message':'Konfiguration gespeichert. Verbindung wird bei der nächsten Analyse geprüft.'}


def analyze_with_provider(text: str, settings: dict[str, Any]) -> dict[str, Any]:
    provider=(settings.get('ai_provider') or 'none').lower()
    model=(settings.get('ai_model') or '').strip()
    base=(settings.get('ai_base_url') or '').strip().rstrip('/')
    key=(settings.get('ai_api_key') or '').strip()
    if provider=='none':
        raise ValueError('Kein KI-Provider konfiguriert.')
    prompt=("Analysiere die folgende deutsche Nebenkostenabrechnung. Gib ausschließlich JSON zurück mit den Schlüsseln "
            "period_start, period_end, total_cost, tenant_total, advance_payments, balance, cost_items, consumptions, findings, recommendations. "
            "cost_items ist eine Liste aus title,total_amount,tenant_share,allocation_key. "
            "consumptions ist eine Liste aus type,value,unit,period_start,period_end,meter_number; type soll möglichst Kaltwasser, Warmwasser, Strom, Gas, Wärmemenge oder Heizkostenverteiler sein. "
            "findings und recommendations sind kurze Listen mit konkreten Prüfhilfen. Unbekannte Werte weglassen.\n\n"+text[:30000])
    if provider=='ollama':
        if not base: base='http://127.0.0.1:11434'
        if not model: model='gemma3'
        out=_request(base+'/api/chat',{'model':model,'messages':[{'role':'user','content':prompt}],'format':'json','stream':False})
        raw=out.get('message',{}).get('content','')
    elif provider=='openai':
        if not key: raise ValueError('OpenAI API-Key fehlt.')
        if not base: base='https://api.openai.com/v1'
        if not model: model='gpt-5-mini'
        out=_request(base+'/responses',{'model':model,'input':prompt}, {'Authorization':'Bearer '+key})
        raw=out.get('output_text','')
        if not raw:
            parts=[]
            for item in out.get('output',[]):
                for c in item.get('content',[]):
                    if c.get('type')=='output_text': parts.append(c.get('text',''))
            raw=''.join(parts)
    elif provider=='anthropic':
        if not key: raise ValueError('Anthropic API-Key fehlt.')
        if not base: base='https://api.anthropic.com/v1'
        if not model: model='claude-sonnet-4-5'
        out=_request(base+'/messages',{'model':model,'max_tokens':3000,'messages':[{'role':'user','content':prompt}]}, {'x-api-key':key,'anthropic-version':'2023-06-01'})
        raw=''.join(x.get('text','') for x in out.get('content',[]) if x.get('type')=='text')
    elif provider=='openrouter':
        if not base: base='https://openrouter.ai/api/v1'
        if not model: raise ValueError('Bitte ein OpenRouter-Modell auswählen.')
        payload={'model':model,'messages':[{'role':'user','content':prompt}],'temperature':0.1}
        out=_request(base+'/chat/completions',payload,_openrouter_headers(settings))
        choices=out.get('choices') or []
        if not choices: raise ValueError('OpenRouter hat keine Antwort geliefert.')
        raw=(choices[0].get('message') or {}).get('content','')
    elif provider=='gemini':
        if not key: raise ValueError('Gemini API-Key fehlt.')
        if not base: base='https://generativelanguage.googleapis.com/v1beta'
        if not model: raise ValueError('Bitte ein Gemini-Modell auswählen.')
        url=base+'/models/'+urllib.parse.quote(model, safe='-._')+':generateContent'
        payload={
            'contents':[{'parts':[{'text':prompt}]}],
            'generationConfig':{'responseMimeType':'application/json','temperature':0.1}
        }
        out=_request(url,payload,{'x-goog-api-key':key})
        candidates=out.get('candidates') or []
        if not candidates: raise ValueError('Gemini hat keine Antwort geliefert.')
        parts=((candidates[0].get('content') or {}).get('parts') or [])
        raw=''.join(str(x.get('text') or '') for x in parts if isinstance(x,dict))
    else:
        raise ValueError('Unbekannter KI-Provider.')
    raw=raw.strip().removeprefix('```json').removesuffix('```').strip()
    parsed=json.loads(raw)
    parsed['ai_provider']=provider
    parsed['ai_model']=model
    return parsed


def analyze_receipt_with_provider(text: str, settings: dict[str, Any]) -> dict[str, Any]:
    provider=(settings.get('ai_provider') or 'none').lower()
    model=(settings.get('ai_model') or '').strip()
    base=(settings.get('ai_base_url') or '').strip().rstrip('/')
    key=(settings.get('ai_api_key') or '').strip()
    if provider=='none':
        raise ValueError('Kein KI-Provider konfiguriert.')
    prompt=("Analysiere den folgenden Beleg oder die Rechnung für einen deutschen Vermieter. "
            "Gib ausschließlich JSON zurück mit den Schlüsseln supplier, document_date, invoice_number, amount, "
            "category, property_hint, description, confidence, notes. "
            "category muss möglichst einer dieser Werte sein: repairs, property_tax, insurance, interest, afa, "
            "management, nonalloc_operating, reserve_contribution, other_expense. "
            "confidence ist eine Zahl von 0 bis 1. Keine steuerliche Endbewertung vornehmen. "
            "Unbekannte Werte weglassen.\n\n"+text[:30000])
    if provider=='ollama':
        if not base: base='http://127.0.0.1:11434'
        if not model: model='gemma3'
        out=_request(base+'/api/chat',{'model':model,'messages':[{'role':'user','content':prompt}],'format':'json','stream':False})
        raw=out.get('message',{}).get('content','')
    elif provider=='openai':
        if not key: raise ValueError('OpenAI API-Key fehlt.')
        if not base: base='https://api.openai.com/v1'
        if not model: model='gpt-5-mini'
        out=_request(base+'/responses',{'model':model,'input':prompt},{'Authorization':'Bearer '+key})
        raw=out.get('output_text','')
        if not raw:
            parts=[]
            for item in out.get('output',[]):
                for c in item.get('content',[]):
                    if c.get('type')=='output_text': parts.append(c.get('text',''))
            raw=''.join(parts)
    elif provider=='anthropic':
        if not key: raise ValueError('Anthropic API-Key fehlt.')
        if not base: base='https://api.anthropic.com/v1'
        if not model: model='claude-sonnet-4-5'
        out=_request(base+'/messages',{'model':model,'max_tokens':1800,'messages':[{'role':'user','content':prompt}]},
                     {'x-api-key':key,'anthropic-version':'2023-06-01'})
        raw=''.join(x.get('text','') for x in out.get('content',[]) if x.get('type')=='text')
    elif provider=='openrouter':
        if not base: base='https://openrouter.ai/api/v1'
        if not model: raise ValueError('Bitte ein OpenRouter-Modell auswählen.')
        out=_request(base+'/chat/completions',{'model':model,'messages':[{'role':'user','content':prompt}],'temperature':0.1},
                     _openrouter_headers(settings))
        choices=out.get('choices') or []
        if not choices: raise ValueError('OpenRouter hat keine Antwort geliefert.')
        raw=(choices[0].get('message') or {}).get('content','')
    elif provider=='gemini':
        if not key: raise ValueError('Gemini API-Key fehlt.')
        if not base: base='https://generativelanguage.googleapis.com/v1beta'
        if not model: raise ValueError('Bitte ein Gemini-Modell auswählen.')
        url=base+'/models/'+urllib.parse.quote(model,safe='-._')+':generateContent'
        out=_request(url,{'contents':[{'parts':[{'text':prompt}]}],
                          'generationConfig':{'responseMimeType':'application/json','temperature':0.1}},
                     {'x-goog-api-key':key})
        candidates=out.get('candidates') or []
        if not candidates: raise ValueError('Gemini hat keine Antwort geliefert.')
        raw=''.join(str(x.get('text') or '') for x in ((candidates[0].get('content') or {}).get('parts') or []) if isinstance(x,dict))
    else:
        raise ValueError('Unbekannter KI-Provider.')
    parsed=json.loads(raw.strip().removeprefix('```json').removesuffix('```').strip())
    parsed['ai_provider']=provider
    parsed['ai_model']=model
    return parsed
