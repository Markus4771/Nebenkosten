from __future__ import annotations
import json, urllib.request, urllib.error, urllib.parse, mimetypes, uuid, re
from pathlib import Path

def _base(settings):
    return (settings.get("paperless_url") or "").strip().rstrip("/")

def _headers(settings):
    token=(settings.get("paperless_token") or "").strip()
    if not token:
        raise ValueError("Paperless API-Token fehlt.")
    return {"Authorization":f"Token {token}","Accept":"application/json; version=10"}

def test_connection(settings, timeout=20):
    base=_base(settings)
    if not base:
        return {"ok":False,"error":"Paperless-URL fehlt."}
    req=urllib.request.Request(base+"/api/documents/?page_size=1",headers=_headers(settings))
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resp:
            return {"ok":True,"status":resp.status,"api_version":resp.headers.get("X-Api-Version"),"server_version":resp.headers.get("X-Version")}
    except Exception as exc:
        return {"ok":False,"error":str(exc)}

def upload_document(settings,path:Path,title:str="",tags=None,document_type=None,correspondent=None,timeout=60):
    base=_base(settings)
    if not base:
        raise ValueError("Paperless-URL fehlt.")
    boundary="----nebenkosten-"+uuid.uuid4().hex
    data=bytearray()
    def field(name,value):
        if value in (None,""): return
        data.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    field("title",title)
    if document_type: field("document_type",document_type)
    if correspondent: field("correspondent",correspondent)
    for tag in (tags or []): field("tags",tag)
    mime=mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{path.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode())
    data.extend(path.read_bytes()); data.extend(f"\r\n--{boundary}--\r\n".encode())
    headers=_headers(settings); headers["Content-Type"]=f"multipart/form-data; boundary={boundary}"
    req=urllib.request.Request(base+"/api/documents/post_document/",data=bytes(data),headers=headers,method="POST")
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        raw=resp.read().decode("utf-8","replace").strip()
        try: return {"ok":True,"task_id":json.loads(raw)}
        except Exception: return {"ok":True,"task_id":raw}

def document_url(settings,document_id):
    base=_base(settings)
    return f"{base}/documents/{document_id}/details" if base and document_id else ""


def task_status(settings,task_id,timeout=20):
    if not task_id:
        return {"ok":False,"error":"Keine Task-ID"}
    base=_base(settings)
    url=base+"/api/tasks/?task_id="+urllib.parse.quote(str(task_id))
    req=urllib.request.Request(url,headers=_headers(settings))
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        obj=json.loads(resp.read().decode("utf-8","replace"))
    results=obj.get("results",obj if isinstance(obj,list) else [])
    if not results:
        return {"ok":False,"error":"Task nicht gefunden"}
    task=results[0]
    doc_id=task.get("related_document") or task.get("document_id") or task.get("result")
    if isinstance(doc_id,dict): doc_id=doc_id.get("id")
    return {"ok":True,"status":task.get("status") or task.get("task_status") or "",
            "document_id":doc_id,"task":task}


def search_documents(settings,query:str,page_size:int=20,timeout=30):
    base=_base(settings)
    if not base:
        raise ValueError("Paperless-URL fehlt.")
    q=urllib.parse.urlencode({"query":query or "","page_size":max(1,min(int(page_size),100))})
    req=urllib.request.Request(base+"/api/documents/?"+q,headers=_headers(settings))
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        obj=json.loads(resp.read().decode("utf-8","replace"))
    rows=[]
    for x in obj.get("results",[]):
        hit=x.get("__search_hit__") or {}
        rows.append({
            "id":x.get("id"),"title":x.get("title") or f"Dokument {x.get('id')}",
            "created":x.get("created"),"added":x.get("added"),
            "correspondent":x.get("correspondent"),"document_type":x.get("document_type"),
            "score":hit.get("score"),"highlights":hit.get("highlights") or "",
        })
    return {"count":obj.get("count",len(rows)),"results":rows}

def get_document(settings,document_id:int,timeout=30):
    base=_base(settings)
    req=urllib.request.Request(base+f"/api/documents/{int(document_id)}/",headers=_headers(settings))
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8","replace"))

def download_document(settings,document_id:int,timeout=60):
    base=_base(settings)
    req=urllib.request.Request(base+f"/api/documents/{int(document_id)}/download/",headers=_headers(settings))
    with urllib.request.urlopen(req,timeout=timeout) as resp:
        data=resp.read()
        ctype=resp.headers.get("Content-Type") or "application/octet-stream"
        cd=resp.headers.get("Content-Disposition") or ""
    name=f"paperless-{int(document_id)}"
    m=re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)',cd,re.I)
    if m:
        name=urllib.parse.unquote(m.group(1).strip('"'))
    return {"data":data,"content_type":ctype,"filename":Path(name).name}
