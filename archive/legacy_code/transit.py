"""Directed multimodal accessibility and additional route search."""
import csv, heapq, itertools, json, math, html
from main import distance

def shortest(graph, source):
    d={source:0.0}; parent={}; queue=[(0.0,source)]
    while queue:
        cost,u=heapq.heappop(queue)
        if cost!=d[u]: continue
        for v,w,label in graph.get(u,[]):
            alt=cost+w
            if alt<d.get(v,math.inf):
                d[v]=alt; parent[v]=(u,label,w); heapq.heappush(queue,(alt,v))
    return d,parent

def edge(g,a,b,w,label):
    g.setdefault(a,[]).append((b,w,label))

def run(es, walking, nodes, stops, pois, out, config):
    for key in ('walk_kmh','bus_kmh','headway_min','max_route_km'):
        if not isinstance(config[key],(float,int)) or not math.isfinite(config[key]) or config[key]<=0:raise ValueError('Positive finite parameter required: '+key)
    if config['dwell_min']<0 or not isinstance(config['endpoints'],int) or config['endpoints']<2:raise ValueError('Invalid dwell_min or endpoints')
    walk_speed=config['walk_kmh']*1000/60; bus_speed=config['bus_kmh']*1000/60
    wait=config['headway_min']/2; dwell=config['dwell_min']
    print('Building directed transit model...',flush=True)
    road={}; way_edges={}
    allowed={'primary','secondary','tertiary','unclassified','residential','living_street','service','trunk','primary_link','secondary_link','tertiary_link','trunk_link'}
    for (typ,ident),e in es.items():
        t=e.get('tags',{})
        if typ!='way' or t.get('highway') not in allowed: continue
        if any(t.get(k) in ('no','private') for k in ('access','vehicle','motor_vehicle')) and t.get('bus') not in ('yes','designated'): continue
        if t.get('bus')=='no': continue
        pairs=[]; oneway=t.get('oneway:bus',t.get('oneway','yes' if t.get('junction')=='roundabout' else 'no'))
        for a,b in itertools.pairwise(e['nodes']):
            if a not in nodes or b not in nodes: continue
            length=distance(nodes[a],nodes[b])
            if oneway!='-1': edge(road,a,b,length,'road');pairs.append((a,b,length))
            if oneway not in ('yes','1','true'): edge(road,b,a,length,'road');pairs.append((b,a,length))
        way_edges[ident]=pairs
    def snap(point,graph):
        n=min(graph,key=lambda n:distance(point,nodes[n]));return n,distance(point,nodes[n])
    local={s:p for s,p in stops.items() if 69.30<=p['lat']<=69.40 and 88.15<=p['lon']<=88.28}
    ws={s:snap(p,walking) for s,p in local.items()};rs={s:snap(p,road) for s,p in local.items()}
    local={s:p for s,p in local.items() if ws[s][1]<=100 and rs[s][1]<=100}
    graph={}
    for a,adj in walking.items():
        for b,w in adj.items(): edge(graph,'w'+str(a),'w'+str(b),w/walk_speed,'Пешком')
    for s in local:
        n,offset=ws[s];edge(graph,'s'+str(s),'w'+str(n),offset/walk_speed,'Пешком');edge(graph,'w'+str(n),'s'+str(s),offset/walk_speed,'Пешком')
    destinations=[]
    for ident,p,t in pois:
        n,offset=snap(p,walking)
        if offset<=100: destinations.append((ident,t.get('name',ident),'w'+str(n),offset/walk_speed))
    audit=[]; routes=[]
    for (typ,ident),e in es.items():
        if typ!='relation' or e.get('tags',{}).get('route')!='bus':continue
        members=e.get('members',[])
        seq=[m['ref'] for m in members if m['type']=='node' and m.get('role','').startswith('platform') and m['ref'] in local]
        if len(seq)<2: continue
        restricted={}
        for m in members:
            if m['type']=='way':
                for a,b,w in way_edges.get(m['ref'],[]):edge(restricted,a,b,w,'road')
        segments=[]
        for a,b in itertools.pairwise(seq):
            ds,_=shortest(restricted,rs[a][0]);length=ds.get(rs[b][0],math.inf)
            if math.isfinite(length) and length>0:segments.append((a,b,length))
            else:audit.append([ident,a,b,'No directed path in mapped route ways; segment omitted'])
        if segments:routes.append((str(ident),e['tags'].get('ref',str(ident)),segments))
    def add_route(target,rid,name,segments):
        used=set()
        for a,b,length in segments:
            edge(target,'r'+rid+':'+str(a),'r'+rid+':'+str(b),length/bus_speed+dwell,'Автобус '+name)
            used.update((a,b))
        for s in used:
            state='r'+rid+':'+str(s);edge(target,'s'+str(s),state,wait,'Посадка '+name+' — '+local[s].get('tags',{}).get('name',str(s)));edge(target,state,'s'+str(s),0,'Выход '+name+' — '+local[s].get('tags',{}).get('name',str(s)))
    for rid,name,segments in routes:add_route(graph,rid,name,segments)
    origins=sorted(local)
    if not origins or not destinations or not routes:raise ValueError('Insufficient connected origins, destinations or route directions')
    def evaluate(g, details=False):
        values=[];records=[]
        for s in origins:
            ds,parents=shortest(g,'s'+str(s))
            for ident,name,target,offset in destinations:
                value=ds.get(target,math.inf)+offset;values.append(value)
                if details:
                    steps=[];node=target
                    if math.isfinite(value):
                        while node in parents:
                            prev,label,cost=parents[node];steps.append((prev,node,label,cost));node=prev
                        steps.reverse()
                    records.append((s,ident,name,value,steps,offset))
        return values,records
    baseline,base_records=evaluate(graph,True)
    print('Generating candidate routes on real roads...',flush=True)
    # Evenly spread endpoints, deterministic farthest-point sampling.
    endpoints=[origins[0]]
    while len(endpoints)<min(config['endpoints'],len(origins)):
        endpoints.append(max((s for s in origins if s not in endpoints),key=lambda s:min(distance(local[s],local[t]) for t in endpoints)))
    candidates=[]
    for a,b in itertools.permutations(endpoints,2):
        ds,parents=shortest(road,rs[a][0]);end=rs[b][0];length=ds.get(end,math.inf)
        if not 1000<=length<=config['max_route_km']*1000:continue
        path=[end]
        while path[-1]!=rs[a][0]:path.append(parents[path[-1]][0])
        path.reverse();positions={n:i for i,n in enumerate(path)}
        sequence=sorted((s for s in origins if rs[s][0] in positions),key=lambda s:(positions[rs[s][0]],s))
        sequence=list(dict.fromkeys(sequence))
        segments=[(u,v,ds[rs[v][0]]-ds[rs[u][0]]) for u,v in itertools.pairwise(sequence) if ds[rs[v][0]]>ds[rs[u][0]]]
        if len(segments)<2:continue
        candidates.append((a,b,length,path,segments))
    # Evaluate all generated candidates, one added direction at a time.
    best_values=baseline;best=None;ranking=[]
    for idx,c in enumerate(candidates):
        if idx%10==0:print('Candidate',idx+1,'/',len(candidates),flush=True)
        trial={n:list(edges) for n,edges in graph.items()};add_route(trial,'new','Новый',c[4]);values,_=evaluate(trial)
        gain=sum(x-y for x,y in zip(baseline,values) if math.isfinite(x) and math.isfinite(y))
        newly=sum(not math.isfinite(x) and math.isfinite(y) for x,y in zip(baseline,values))
        ranking.append([idx,c[0],c[1],c[2],gain,newly])
        if best is None or (newly,gain)>(best[0],best[1]):best=(newly,gain,c,trial);best_values=values
    final_records=base_records
    if best:_,final_records=evaluate(best[3],True)
    with (out/'candidate_routes.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['candidate','from_stop','to_stop','length_m','total_model_minutes_saved','newly_reachable_pairs']);w.writerows(ranking)
    with (out/'route_audit.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['relation','from_stop','to_stop','issue']);w.writerows(audit)
    with (out/'journeys.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['origin_stop_osm','origin_name','destination_osm','destination_name','before_min','after_min','saved_min','boardings','instructions'])
        for old,new in zip(base_records,final_records):
            s,ident,name,value,steps,offset=new;before=old[3];compressed=[]
            for _,_,label,cost in steps:
                if compressed and compressed[-1][0]==label:compressed[-1][1]+=cost
                else:compressed.append([label,cost])
            if offset:compressed.append(['Пешком до объекта',offset])
            w.writerow([s,local[s].get('tags',{}).get('name',str(s)),ident,name,round(before,2) if math.isfinite(before) else '',round(value,2) if math.isfinite(value) else '',round(before-value,2) if math.isfinite(before) and math.isfinite(value) else '',sum(label.startswith('Посадка') for _,_,label,_ in steps),'; '.join(f'{label}: {cost:.1f} мин' for label,cost in compressed)])
    finite=[(a,b) for a,b in zip(baseline,best_values) if math.isfinite(a) and math.isfinite(b)]
    summary={'parameters_assumed_not_observed':config,'origins_actual_stops':len(origins),'destinations':len(destinations),'od_pairs':len(baseline),'route_directions':len(routes),'omitted_route_segments':len(audit),'candidates_evaluated':len(candidates),'before_mean_min_common_pairs':sum(a for a,b in finite)/len(finite),'after_mean_min_common_pairs':sum(b for a,b in finite)/len(finite),'improved_pairs':sum(b<a-1e-8 for a,b in finite),'unreachable_before':sum(not math.isfinite(x) for x in baseline),'unreachable_after':sum(not math.isfinite(x) for x in best_values),'comparison':'Existing mapped network versus same network plus one new directed route; additional operating resources required','optimality':'Best among generated candidates, not global network optimum','origins':'Actual bus stops, NOT residential population or measured demand'}
    features=[]
    if best:
        c=best[2];summary['new_route']={'from_name':local[c[0]].get('tags',{}).get('name',str(c[0])),'to_name':local[c[1]].get('tags',{}).get('name',str(c[1])),'stop_names':[local[t].get('tags',{}).get('name',str(t)) for t in [c[4][0][0]]+[v for u,v,l in c[4]]],'from_stop':c[0],'to_stop':c[1],'length_m':c[2],'stops':[c[4][0][0]]+[v for u,v,l in c[4]]}
        features=[{'type':'Feature','geometry':{'type':'LineString','coordinates':[[nodes[n]['lon'],nodes[n]['lat']] for n in c[3]]},'properties':summary['new_route']}]
    (out/'new_route.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
    (out/'journey_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    report='<meta charset="utf-8"><title>Норильск — поездки</title><style>body{font:17px system-ui;max-width:1000px;margin:40px auto}pre{white-space:pre-wrap}</style><h1>Поездки и новый вариант маршрута</h1><p>Сравнение исходной сети и добавления одного направления. Учитываются пешие пути, направление движения автобуса, ожидание при каждой посадке и пересадки. Все пары имеют одинаковый вес; это не пассажиропоток.</p><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre><p><a href="journeys.csv">Все поездки и инструкции</a> · <a href="candidate_routes.csv">Сравнение кандидатов</a> · <a href="new_route.geojson">Трасса нового маршрута</a> · <a href="route_audit.csv">Пропуски исходных трасс</a></p><p>Скорости, интервал и время остановки — сценарные параметры. Исходные трассы реконструированы по путям отношений OSM между остановками; отсутствующие направленные связи исключены. Новая трасса учитывает oneway и базовые запреты проезда, но не отношения запретов поворотов, ограничения габаритов, сезонные закрытия, возможность разворота и сторону посадки. Требуется инженерная проверка. Результат не является проектом для выпуска автобуса на линию.</p>'
    if best:
        path=best[2][3]
        def xy(n):return ((nodes[n]['lon']-88.15)/.13*900,(69.40-nodes[n]['lat'])/.10*800)
        shapes=[]
        for a,adj in walking.items():
            for b in adj:
                if a<b:
                    x,y=xy(a);u,v=xy(b);shapes.append(f'<path d="M{x},{y} L{u},{v}" stroke="#d4d9df"/>')
        coords=' '.join(f'{xy(n)[0]},{xy(n)[1]}' for n in path)
        shapes.append(f'<polyline points="{coords}" fill="none" stroke="#006cbe" stroke-width="4"/>')
        for i,t in enumerate(summary['new_route']['stops']):
            x,y=xy(rs[t][0]);name=html.escape(local[t].get('tags',{}).get('name',str(t)))
            shapes.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#dc2626"><title>{name}</title></circle><text x="{x+7}" y="{y}" font-size="14">{i+1}</text>')
        report+='<h2>Новая трасса на дорожном графе</h2><svg viewBox="0 0 900 800" style="width:100%">'+''.join(shapes)+'</svg><ol>'+''.join('<li>'+html.escape(n)+'</li>' for n in summary['new_route']['stop_names'])+'</ol>'
    (out/'journey_report.html').write_text(report,encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))
