"""Search shorter road paths between consecutive mapped bus stop positions."""
import json,csv,html,hashlib
from pathlib import Path
from main import distance
from transit import shortest,edge
ROOT=Path(__file__).resolve().parent

def main():
    es={}
    for e in json.loads((ROOT/'data/osm.json').read_text(encoding='utf-8'))['elements']:es.setdefault((e['type'],e['id']),{}).update(e)
    nodes={i:e for (typ,i),e in es.items() if typ=='node'}
    def local(n):return 69.30<=nodes[n]['lat']<=69.40 and 88.15<=nodes[n]['lon']<=88.28
    road={};way_edges={};allowed={'primary','secondary','tertiary','unclassified','residential','living_street','service','primary_link','secondary_link','tertiary_link'}
    for (typ,i),e in es.items():
        t=e.get('tags',{})
        if typ!='way' or t.get('highway') not in allowed:continue
        if t.get('bus')=='no':continue
        if any(t.get(k) in ('private','no') for k in ('access','vehicle','motor_vehicle')) and t.get('bus') not in ('yes','designated'):continue
        if t.get('service') in ('parking_aisle','driveway'):continue
        one=t.get('oneway:bus',t.get('oneway','yes' if t.get('junction')=='roundabout' else 'no'))
        pairs=[]
        for a,b in zip(e['nodes'],e['nodes'][1:]):
            if a not in nodes or b not in nodes or not local(a) or not local(b):continue
            d=distance(nodes[a],nodes[b])
            if one!='-1':pairs.append((a,b,d))
            if one not in ('yes','true','1'):pairs.append((b,a,d))
        for a,b,d in pairs:edge(road,a,b,d,str(i))
        way_edges[i]=pairs
    def path(parents,a,b):
        seq=[b]
        while seq[-1]!=a:seq.append(parents[seq[-1]][0])
        return list(reversed(seq))
    rows=[];failures=[];geometry=[];cache={}
    for (typ,rid),r in es.items():
        if typ!='relation' or r.get('tags',{}).get('route')!='bus':continue
        stop_names={}
        for idx,m in enumerate(r['members'][:-1]):
            nxt=r['members'][idx+1]
            if m['type']=='node' and m.get('role','').startswith('stop') and nxt['type']=='node' and nxt.get('role','').startswith('platform'):
                platform=nodes.get(nxt['ref'],{});label=platform.get('tags',{}).get('name')
                if label:stop_names[m['ref']]=label
        seq=[m['ref'] for m in r['members'] if m['type']=='node' and m.get('role','').startswith('stop')]
        restricted={}
        for m in r['members']:
            if m['type']=='way':
                for a,b,d in way_edges.get(m['ref'],[]):edge(restricted,a,b,d,str(m['ref']))
        for a,b in zip(seq,seq[1:]):
            if a==b or a not in nodes or b not in nodes or not local(a) or not local(b):continue
            if a not in restricted or a not in road:failures.append([rid,a,b,'Stop position not connected to mapped road']);continue
            ds,ps=shortest(restricted,a)
            if b not in ds:failures.append([rid,a,b,'No directed path on mapped route ways']);continue
            if a not in cache:cache[a]=shortest(road,a)
            dn,pn=cache[a]
            if b not in dn:continue
            old,new=ds[b],dn[b];saved=old-new
            item=dict(route=r['tags'].get('ref',str(rid)),relation=rid,from_node=a,to_node=b,from_name=stop_names.get(a,nodes[a].get('tags',{}).get('name',str(a))),to_name=stop_names.get(b,nodes[b].get('tags',{}).get('name',str(b))),before_m=round(old,2),after_m=round(new,2),saved_m=round(saved,2),saved_percent=round(saved/old*100,2) if old else 0)
            rows.append(item)
            if saved>50:
                before_path=path(ps,a,b);after_path=path(pn,a,b)
                # Keep every stop position on the whole relation: no silently bypassed mapped stop.
                bypassed=[n for n in seq if n in before_path[1:-1] and n not in after_path]
                if bypassed:item['review']='bypasses_other_mapped_stop';continue
                item['review']='requires_turn_and_bus_feasibility_review'
                geometry.append((item,before_path,after_path))
    rows.sort(key=lambda r:r['saved_m'],reverse=True);geometry.sort(key=lambda r:r[0]['saved_m'],reverse=True)
    out=ROOT/'output'
    with (out/'route_geometry_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['route','relation','from_node','to_node','from_name','to_name','before_m','after_m','saved_m','saved_percent','review'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    with (out/'route_geometry_issues.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['relation','from_node','to_node','issue']);w.writerows(failures)
    features=[]
    for item,before,after in geometry:
        for label,seq in [('before',before),('candidate',after)]:features.append({'type':'Feature','geometry':{'type':'LineString','coordinates':[[nodes[n]['lon'],nodes[n]['lat']] for n in seq]},'properties':{**item,'variant':label}})
    (out/'route_variants.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
    summary={'tested_directed_segments':len(rows),'unresolved_segments':len(failures),'shorter_candidates_over_50m':len(geometry),'best':geometry[0][0] if geometry else None,'baseline':'Shortest directed path within ways belonging to OSM route relation, not GPS-observed bus trajectory','candidate':'Shortest directed road path; stop endpoints retained; no turn-restriction relation or vehicle clearance verification','source_sha256':hashlib.sha256((ROOT/'data/osm.json').read_bytes()).hexdigest()}
    (out/'route_geometry_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    report='<meta charset="utf-8"><title>Норильск — варианты трасс</title><style>body{font:17px system-ui;max-width:1100px;margin:40px auto}td,th{padding:8px;border-bottom:1px solid #ddd}svg{width:100%;background:#f7f9fb}</style><h1>Можно ли сократить путь между остановками?</h1><p>Проверяем последовательные остановочные позиции существующих маршрутов. Пассажиропоток и скорость движения не подставляются. Сравниваем длину дороги.</p>'
    report+=f'<p>Рассчитано участков: {len(rows)}. Не восстановлено: {len(failures)}. Кандидатов с сокращением более 50 м: {len(geometry)}.</p><table><tr><th>Маршрут</th><th>Участок</th><th>Было, м</th><th>Вариант, м</th><th>Разница, м</th></tr>'
    for item,_,_ in geometry[:15]:report+='<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [item['route'],item['from_name']+' → '+item['to_name'],item['before_m'],item['after_m'],item['saved_m']])+'</tr>'
    report+='</table>'
    if geometry:
        item,before,after=next((v for v in geometry if 'Административно' in v[0]['from_name']),geometry[0]);allnodes=before+after;lo=min(nodes[n]['lon'] for n in allnodes);hi=max(nodes[n]['lon'] for n in allnodes);south=min(nodes[n]['lat'] for n in allnodes);north=max(nodes[n]['lat'] for n in allnodes)
        def xy(n):return (30+(nodes[n]['lon']-lo)/max(hi-lo,.001)*840,30+(north-nodes[n]['lat'])/max(north-south,.001)*540)
        shapes=[]
        for a,edges in road.items():
            if not lo-.002<=nodes[a]['lon']<=hi+.002 or not south-.001<=nodes[a]['lat']<=north+.001:continue
            for b,_,_ in edges:
                x,y=xy(a);u,v=xy(b);shapes.append(f'<path d="M{x},{y} L{u},{v}" stroke="#d7dce1"/>')
        for seq,color,width in [(before,'#df7b28',6),(after,'#146cb5',3)]:
            pts=' '.join(f'{xy(n)[0]},{xy(n)[1]}' for n in seq);shapes.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"/>')
        report+='<h2>Пример в городской застройке: АДЦ → улица Красноярская</h2><p>Оранжевый — путь по линиям исходного отношения OSM; синий — кандидат. Схема растянута по размерам области, не предназначена для измерений.</p><svg viewBox="0 0 900 600">'+''.join(shapes)+'</svg>'
    report+='<p><a href="route_geometry_comparison.csv">Все расчёты</a> · <a href="route_variants.geojson">Трассы для карты</a> · <a href="route_geometry_issues.csv">Невосстановленные участки</a></p><h2>Что доказано, а что требует проверки</h2><p>Найден более короткий путь в графе, с учётом направлений улиц и базовых запретов проезда. Это ещё не разрешённая новая трасса автобуса. Не проверены запреты конкретных поворотов, развороты, габариты и пригодность дороги. Исходный путь восстановлен по картографическим данным OSM, а не по фактическому треку автобуса. Расписания не содержат геометрии проезда. Сокращение метров нельзя автоматически считать экономией времени или денег. Не следует суммировать участки из разных направлений как экономию одного рейса.</p><p>© OpenStreetMap contributors, ODbL. Исходный снимок и запрос сохранены в data/osm.json и data/source.json.</p>'
    (out/'route_geometry_report.html').write_text(report,encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
