import argparse, csv, hashlib, itertools, json, math, heapq
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parent

def distance(a,b):
    p,q=map(math.radians,(a['lat'],b['lat']))
    return 12742000*math.asin(min(1,math.sqrt(math.sin((p-q)/2)**2+math.cos(p)*math.cos(q)*math.sin(math.radians(a['lon']-b['lon'])/2)**2)))

def optimize(routes, k):
    keys=sorted(routes)
    if not 1<=k<=len(keys): raise ValueError('Invalid route count')
    count=math.comb(len(keys),k)
    if count>2000000: raise ValueError('Too many combinations; change --keep')
    return max(itertools.combinations(keys,k),key=lambda choice:len(set().union(*(routes[r]['cover'] for r in choice))))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--keep',type=int,default=5); ap.add_argument('--radius',type=float,default=500); ap.add_argument('--refresh',action='store_true'); args=ap.parse_args()
    if args.keep<1 or args.radius<=0: ap.error('Positive keep and radius required')
    folder=ROOT/'data'; folder.mkdir(exist_ok=True); path=folder/'osm.json'
    bbox='69.30,88.15,69.40,88.28'
    query='[out:json][timeout:120];(way[highway]('+bbox+');node[highway=bus_stop]('+bbox+');nwr[amenity~"^(school|kindergarten|hospital|clinic|college|university)$"]('+bbox+');relation[route=bus]('+bbox+'););out body center;>;out skel qt;'
    if not path.exists() or args.refresh:
        errors=[]
        for url in ['https://overpass-api.de/api/interpreter','https://overpass.kumi.systems/api/interpreter']:
            try:
                print('Downloading OSM:',url,flush=True)
                with urlopen(Request(url+'?'+urlencode({'data':query}),headers={'User-Agent':'NorilskResearch/1.0'}),timeout=45) as r: raw=r.read()
                data=json.loads(raw)
                if data.get('remark') or not data.get('elements'): raise ValueError(data.get('remark','Empty data'))
                path.write_bytes(raw)
                (folder/'source.json').write_text(json.dumps(dict(url=url,query=query,retrieved_utc=datetime.now(timezone.utc).isoformat(),sha256=hashlib.sha256(raw).hexdigest(),license='OSM contributors ODbL'),indent=2),encoding='utf-8'); break
            except Exception as e: errors.append(str(e))
        else: raise RuntimeError('Real data unavailable. No invented fallback. '+str(errors))
    data=json.loads(path.read_text(encoding='utf-8')); es={}
    for e in data['elements']:
        es.setdefault((e['type'],e['id']),{}).update(e)
    stops={i:e for (t,i),e in es.items() if t=='node' and e.get('tags',{}).get('highway')=='bus_stop'}
    pois=[]
    for (t,i),e in es.items():
        if e.get('tags',{}).get('amenity') in ['school','kindergarten','hospital','clinic','college','university']:
            p=e if t=='node' else e.get('center')
            if p and 69.30<=p['lat']<=69.40 and 88.15<=p['lon']<=88.28: pois.append((f'{t}/{i}',p,e['tags']))
    nodes={i:e for (t,i),e in es.items() if t=='node'}
    graph={}
    for (typ,ident),e in es.items():
        tags=e.get('tags',{})
        if typ!='way' or not tags.get('highway'): continue
        if tags.get('foot')=='no' or tags.get('access') in ('private','no') or tags['highway'] in ('motorway','motorway_link','construction','proposed'): continue
        for a,b in itertools.pairwise(e['nodes']):
            if a not in nodes or b not in nodes: continue
            length=distance(nodes[a],nodes[b]); graph.setdefault(a,{})[b]=length; graph.setdefault(b,{})[a]=length
    if not graph: raise ValueError('No walking graph. Run with --refresh to replace older cache.')
    def snap(point):
        n=min(graph,key=lambda n:distance(point,nodes[n])); return n,distance(point,nodes[n])
    ps=[snap(p) for _,p,_ in pois]; matrix={}; cover={}
    for stop,e in stops.items():
        source,offset=snap(e); lengths={source:0}; queue=[(0,source)]
        while queue:
            d,n=heapq.heappop(queue)
            if d!=lengths[n]: continue
            for nxt,cost in graph[n].items():
                value=d+cost
                if value<=args.radius and value<lengths.get(nxt,math.inf):
                    lengths[nxt]=value; heapq.heappush(queue,(value,nxt))
        cover[stop]=set()
        for j,(n,connector) in enumerate(ps):
            value=offset+lengths.get(n,math.inf)+connector
            if offset>100 or connector>100: value=math.inf
            matrix[stop,j]=value
            if value<=args.radius: cover[stop].add(j)
    routes={}
    for (t,i),e in es.items():
        if t!='relation' or e.get('tags',{}).get('route')!='bus': continue
        members={m['ref'] for m in e.get('members',[]) if m['type']=='node' and m['ref'] in stops}
        if members:
            key=e['tags'].get('ref',f'relation/{i}'); r=routes.setdefault(key,{'ids':[],'stops':set(),'cover':set()}); r['ids'].append(i); r['stops']|=members
            for s in members: r['cover']|=cover[s]
    if not routes or not pois: raise ValueError('Insufficient real route or object data')
    keys=sorted(routes); k=min(args.keep,len(keys)); count=math.comb(len(keys),k)
    if count>2000000: raise ValueError('Too many combinations; change --keep')
    def coverage(chosen): return set().union(*(routes[r]['cover'] for r in chosen))
    best=optimize(routes,k)
    frontier=[]; minimum=None
    baseline=coverage(keys)
    for budget in range(1,k+1):
        solution=optimize(routes,budget); reached=len(coverage(solution))
        frontier.append({'routes_count':budget,'covered_objects':reached,'routes':list(solution)})
        if reached==len(baseline) and minimum is None: minimum=list(solution)

    summary=dict(minimum_full_coverage_within_tested_budgets=minimum, frontier=frontier, objects=len(pois),stops=len(stops),mapped_route_groups=len(keys),keep=k,radius_m=args.radius,baseline_covered=len(coverage(keys)),selected_covered=len(coverage(best)),selected=best,combinations=count,graph_nodes=len(graph), metric='Walking graph coverage with straight connectors up to 100m; NOT passenger demand')
    out=ROOT/'output'; out.mkdir(exist_ok=True)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'matrix.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['stop_osm_id','object_osm_id','bounded_graph_distance_m','covered'])
        for s,e in stops.items():
            for j,(i,p,t) in enumerate(pois): w.writerow([s,i,round(matrix[s,j],2) if math.isfinite(matrix[s,j]) else '',int(j in cover[s])])
    with (out/'routes.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['route','relations','mapped_stops','covered_objects','selected'])
        for key,r in routes.items(): w.writerow([key,str(r['ids']),len(r['stops']),len(r['cover']),int(key in best)])
    features=[]
    for ident,point,tags in pois:
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[point['lon'],point['lat']]},'properties':{'osm':ident,**tags}})
    for ident,point in stops.items():
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[point['lon'],point['lat']]},'properties':{'osm':f'node/{ident}','kind':'bus_stop',**point.get('tags',{})}})
    (out/'map.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
    with (out/'objects.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['osm','name','category','baseline_covered','selected_covered'])
        for j,(ident,point,tags) in enumerate(pois): w.writerow([ident,tags.get('name',''),tags['amenity'],int(j in baseline),int(j in coverage(best))])
    import html
    (out/'report.html').write_text('<meta charset="utf-8"><title>Норильск: расчёт</title><style>body{font:18px system-ui;max-width:900px;margin:40px auto}pre{white-space:pre-wrap}</style><h1>Графовая доступность социальных объектов</h1><p>Точный максимум среди сочетаний найденных в OSM групп маршрутов при заданном числе групп. Это предварительная модель, не готовая рекомендация отменять маршруты.</p><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre><p>Все объекты имеют вес 1. Расстояния по пешеходному графу OSM; привязки к нему до 100 м по прямой без проверки препятствий. Пустое расстояние означает отсутствие пути в радиусе поиска либо отклонённую привязку. Пассажиропоток, расписание, пересадки и стоимость неизвестны. OSM может содержать неполные или устаревшие маршруты. Направления объединены по номеру. Полная сеть является базой сравнения: сокращение сети не может увеличить её покрытие.</p><p>© OpenStreetMap contributors, ODbL. Источник и дата снимка: data/source.json. Область: центральная часть Норильска, не весь НПР.</p>',encoding='utf-8')
    chosen=set().union(*(routes[r]['stops'] for r in best))
    def xy(p): return ((p['lon']-88.15)/.13*900,(69.40-p['lat'])/.10*850)
    svg=[]
    for a,adj in graph.items():
        for b in adj:
            if a<b:
                x,y=xy(nodes[a]);u,v=xy(nodes[b])
                svg.append(f'<path d="M{x:.1f},{y:.1f} L{u:.1f},{v:.1f}" stroke="#d0d6dc" fill="none"/>')
    for stop,point in stops.items():
        x,y=xy(point);color='#007f68' if stop in chosen else '#aaa'
        svg.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{color}"><title>{html.escape(point.get("tags",{}).get("name",str(stop)))}</title></circle>')
    for j,(ident,point,tags) in enumerate(pois):
        x,y=xy(point);color='#2563eb' if j in coverage(best) else '#dc2626'
        svg.append(f'<rect x="{x}" y="{y}" width="6" height="6" fill="{color}"><title>{html.escape(tags.get("name",ident))}</title></rect>')
    rows=''.join('<tr><td>'+str(r['routes_count'])+'</td><td>'+str(r['covered_objects'])+'</td><td>'+html.escape(', '.join(r['routes']))+'</td></tr>' for r in frontier)
    extra='<h2>Число маршрутов и сохранённое покрытие</h2><table><tr><th>Маршрутов</th><th>Объектов</th><th>Номера по OSM</th></tr>'+rows+'</table><h2>Карта расчёта</h2><p>Зелёные точки: остановки выбранных маршрутов; синие квадраты: доступные объекты; красные: недоступные. Серые линии: пешеходный граф. Наведите указатель для названия.</p><svg style="width:100%;border:1px solid #ddd" viewBox="0 0 900 850">'+''.join(svg)+'</svg>'
    report=out/'report.html';report.write_text(report.read_text(encoding='utf-8')+extra,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2)); print(out/'report.html')
    if (ROOT/'data/schedules/trips.json').exists():
        from schedule_report import build
        build()
        print('Timetables imported. Geographic stop matching and residential routing still require completion.')
        print(out/'schedule_report.html')
    else:
        from transit import run
        config=json.loads((ROOT/'config.json').read_text(encoding='utf-8-sig'))
        run(es,graph,nodes,stops,pois,out,config)
if __name__=='__main__':
    if (ROOT/'data/schedules/trips.json').exists():
        from optimize_timetable import main as optimize_schedule
        optimize_schedule()
        from optimize_geometry import main as optimize_paths
        optimize_paths()
        from present_results import main as present
        present()
        from acceptance_review import main as review_acceptance
        review_acceptance()
    else:
        main()
