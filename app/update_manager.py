import json, os, re, subprocess, urllib.request
from pathlib import Path
from . import __version__

CURRENT_VERSION=__version__; DEFAULT_REPO='Markus4771/Nebenkosten'; STAGING_DIR=Path(os.getenv('NEBENKOSTEN_UPDATE_DIR','/var/lib/nebenkostenabrechnung/updates'))
def version_key(v): return tuple(int(x) for x in re.findall(r'\d+',v)[:3] or [0])
def headers(token=None):
    h={'Accept':'application/vnd.github+json','User-Agent':f'Nebenkostenabrechnung/{CURRENT_VERSION}'}
    if token: h['Authorization']=f'Bearer {token}'
    return h
def check_github_release(repo=DEFAULT_REPO,token=None):
    req=urllib.request.Request(f'https://api.github.com/repos/{repo}/releases/latest',headers=headers(token))
    with urllib.request.urlopen(req,timeout=8) as r: data=json.load(r)
    tag=str(data.get('tag_name') or '').lstrip('v')
    return {'current':CURRENT_VERSION,'latest':tag,'update_available':bool(tag and version_key(tag)>version_key(CURRENT_VERSION)),'name':data.get('name'),'html_url':data.get('html_url'),'assets':[{'name':a.get('name'),'url':a.get('url'),'browser_url':a.get('browser_download_url')} for a in data.get('assets',[])]}
def stage_latest_deb(token=None):
    rel=check_github_release(token=token)
    if not rel['update_available']: raise ValueError('Kein neueres Release verfügbar.')
    asset=next((a for a in rel['assets'] if (a['name'] or '').endswith('_all.deb')),None)
    if not asset: raise ValueError('Kein Debian-Paket im Release.')
    STAGING_DIR.mkdir(parents=True,exist_ok=True); target=STAGING_DIR/Path(asset['name']).name
    req=urllib.request.Request(asset['url'] or asset['browser_url'],headers={**headers(token),'Accept':'application/octet-stream'})
    with urllib.request.urlopen(req,timeout=60) as r, target.open('wb') as out:
        while chunk:=r.read(1024*1024): out.write(chunk)
    return target,rel
def install_staged_deb(path):
    path=Path(path).resolve()
    if STAGING_DIR.resolve() not in path.parents or not re.fullmatch(r'nebenkostenabrechnung_[0-9][0-9.~-]*_all\.deb',path.name): raise ValueError('Ungültiges Updatepaket.')
    r=subprocess.run(['/usr/bin/sudo','/usr/local/sbin/nebenkosten-install-update',str(path)],capture_output=True,text=True,timeout=180)
    if r.returncode: raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout
