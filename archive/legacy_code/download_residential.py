import json,hashlib
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.parse import urlencode
from datetime import datetime,timezone
q='[out:json][timeout:60];nwr[building~"^(apartments|residential|house|dormitory)$"](69.30,88.15,69.40,88.28);out center tags;'
p=Path('data/residential.json')
if not p.exists():
    url='https://overpass.kumi.systems/api/interpreter?'+urlencode({'data':q})
    with urlopen(Request(url,headers={'User-Agent':'NorilskResearch/1.0'}),timeout=45) as r:raw=r.read()
    d=json.loads(raw)
    if d.get('remark') or not d.get('elements'):raise ValueError(d.get('remark','empty'))
    p.write_bytes(raw);Path('data/residential_source.json').write_text(json.dumps({'url':url,'query':q,'retrieved':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(raw).hexdigest()},indent=2),encoding='utf-8')
print(len(json.loads(p.read_text())['elements']))

