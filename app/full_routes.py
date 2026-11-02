"""Full OSM route reconstruction. Gaps are reported, never filled by straight lines."""
import json,math,html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def distance(a,b):
    p,q=math.radians(a['lat']),math.radians(b['lat']);return 12742000*math.asin(min(1,math.sqrt(math.sin((p-q)/2)**2+math.cos(p)*math.cos(q)*math.sin(math.radians(a['lon']-b['lon'])/2)**2)))
def orient(ways,nodes):
    if not ways:return [],[]
    # Dynamic programming chooses way orientations, preserving membership order and loops.
    states=[(0,[])]
    for seq,role in ways:
        options=[seq] if role=='forward' else [list(reversed(seq))] if role=='backward' else [seq,list(reversed(seq))]
        updated=[]
        for option in options:
            best=min(((cost+(distance(nodes[path[-1][-1]],nodes[option[0]]) if path and path[-1][-1]!=option[0] else 0),path+[option]) for cost,path in states),key=lambda v:v[0]);updated.append(best)
        states=updated
    _,pieces=min(states,key=lambda v:v[0]);parts=[];gaps=[]
    for seq in pieces:
        if parts and parts[-1][-1]==seq[0]:parts[-1].extend(seq[1:])
        else:
            if parts:gaps.append({'from':parts[-1][-1],'to':seq[0],'distance_m':round(distance(nodes[parts[-1][-1]],nodes[seq[0]]),1)})
            parts.append(seq[:])
    return parts,gaps

def main():
    es={}
    for e in json.loads((ROOT/'data/osm.json').read_text(encoding='utf-8'))['elements']:es.setdefault((e['type'],e['id']),{}).update(e)
    nodes={i:e for (t,i),e in es.items() if t=='node'};routes=[]
    for (typ,rid),r in es.items():
        if typ!='relation' or r.get('tags',{}).get('route')!='bus':continue
        ways=[];missing=[];stops=[];positions=[]
        for idx,m in enumerate(r['members']):
            if m['type']=='way' and not m.get('role','').startswith('platform'):
                w=es.get(('way',m['ref']),{});seq=w.get('nodes',[])
                if len(seq)>=2 and all(n in nodes for n in seq):ways.append((seq,m.get('role','')))
                else:missing.append(m['ref'])
            if m['type']=='node' and m.get('role','').startswith('stop'):
                positions.append(m['ref']);p=nodes.get(m['ref']);label=p.get('tags',{}).get('name') if p else None
                if idx+1<len(r['members']):
                    other=r['members'][idx+1]
                    if other['type']=='node' and other.get('role','').startswith('platform'):label=nodes.get(other['ref'],{}).get('tags',{}).get('name',label)
                if p:stops.append({'id':m['ref'],'name':label or 'Остановка OSM '+str(m['ref']),'lon':p['lon'],'lat':p['lat']})
        parts,gaps=orient(ways,nodes);flat=[n for part in parts for n in part];cursor=0;unmatched=[]
        for n in positions:
            try:cursor=flat.index(n,cursor)+1
            except ValueError:unmatched.append(n)
        length=sum(distance(nodes[a],nodes[b]) for part in parts for a,b in zip(part,part[1:]))
        reversals=sum(a==c for part in parts for a,b,c in zip(part,part[1:],part[2:]))
        routes.append({'id':rid,'ref':r['tags'].get('ref',str(rid)),'name':r['tags'].get('name',str(rid)),'parts':[[[nodes[n]['lon'],nodes[n]['lat']] for n in part] for part in parts],'stops':stops,'length_m':round(length,1),'gaps':gaps,'missing_ways':missing,'unmatched_stops':unmatched,'immediate_reversals':reversals,'status':'continuous_ordered_geometry' if not gaps and not missing and not unmatched else 'needs_source_repair','accepted_change':False})
    out=ROOT/'output';out.mkdir(exist_ok=True)
    (out/'full_routes.json').write_text(json.dumps(routes,ensure_ascii=False,indent=2),encoding='utf-8')
    features=[{'type':'Feature','properties':{k:v for k,v in r.items() if k not in ('parts','stops')},'geometry':{'type':'MultiLineString','coordinates':r['parts']}} for r in routes]
    (out/'full_routes.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False),encoding='utf-8')
    data=json.dumps(routes,ensure_ascii=False).replace('</',r'<\/')
    page=r'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Норильск — полные маршруты</title><style>body{font:17px system-ui;background:#f2f5f9;color:#19334b;margin:0}main{max-width:1300px;margin:auto;padding:24px}section{background:white;padding:20px;border-radius:12px;margin:18px 0}select,button,input{font:inherit;padding:8px}#map{width:100%;height:650px;background:#f8fafc;touch-action:none}table{border-collapse:collapse;width:100%}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}.warn{padding:15px;background:#fff0d6}#stats{white-space:pre-line}a{color:#086aad}</style><main><h1>Полные автобусные маршруты Норильска</h1><p>От конечной до конечной, в порядке элементов исходного маршрута OSM. Развороты и повторные проезды сохранены. Разрывы не соединяются вымышленной дорогой.</p><select id="route" onchange="show()"></select><button onclick="zoom(.7)">+</button><button onclick="zoom(1.4)">−</button><button onclick="show()">Весь маршрут</button><section><h2 id="title"></h2><div id="stats"></div><svg id="map"><defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#1267ac"/></marker></defs><g id="paths"></g></svg><p>Синяя линия — исходный полный маршрут; стрелочки показывают направление движения. Красные точки — остановки; названия при наведении. Колесо — масштаб, перетаскивание — перемещение. Подложка: геометрия улиц, входящих в маршрут; интернет не требуется. © OpenStreetMap contributors, ODbL.</p></section><section><h2>Остановки по порядку</h2><table><thead><tr><th>№</th><th>Остановка</th></tr></thead><tbody id="stops"></tbody></table></section><section><h2>Результат проверки</h2><p class="warn">Прежние фрагментарные сокращения отозваны. Непрерывность полной линии и порядок остановок проверяются автоматически. Допустимость всех манёвров пока не подтверждена: исходная выгрузка не содержит полный набор ограничений поворотов. Неподтверждённые изменения в расписание не вносятся.</p><p><a href="schedule_review.html">Расписание: исходное и отклонённый сдвиг</a> · <a href="full_routes.geojson">Полные маршруты GeoJSON</a></p></section></main><script>const routes=DATA;let current;const sel=document.getElementById('route'),svg=document.getElementById('map');for(let i=0;i<routes.length;i++){let o=document.createElement('option');o.value=i;o.textContent=routes[i].name;sel.appendChild(o)}function project(p){return [(p[0]-88)*111320*Math.cos(69.35*Math.PI/180),(69.5-p[1])*111320]}function element(tag,attrs){let e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(let k in attrs)e.setAttribute(k,attrs[k]);return e}function show(){current=routes[sel.value||0];document.getElementById('title').textContent=current.name;document.getElementById('stats').textContent='Длина отображённых участков: '+(current.length_m/1000).toFixed(2)+' км. Остановок: '+current.stops.length+'\nРазрывов: '+current.gaps.length+'. Отсутствующих линий: '+current.missing_ways.length+'. Остановок без подтверждённого порядка: '+current.unmatched_stops.length+'.';let g=document.getElementById('paths');g.replaceChildren();let pts=current.parts.flat().map(project);for(let part of current.parts){let pp=part.map(project);let line=element('polyline',{points:pp.map(p=>p.join(',')).join(' '),fill:'none',stroke:'#1267ac','stroke-width':4,'vector-effect':'non-scaling-stroke'});g.appendChild(line);for(let i=0;i+1<pp.length;i+=12)g.appendChild(element('line',{x1:pp[i][0],y1:pp[i][1],x2:pp[i+1][0],y2:pp[i+1][1],stroke:'#1267ac','stroke-width':3,'vector-effect':'non-scaling-stroke','marker-end':'url(#arrow)'}))}let tbody=document.getElementById('stops');tbody.replaceChildren();for(let [i,s] of current.stops.entries()){let p=project([s.lon,s.lat]),c=element('circle',{cx:p[0],cy:p[1],r:10,fill:'#c32f35'}),t=element('title',{});t.textContent=(i+1)+'. '+s.name;c.appendChild(t);g.appendChild(c);let tr=document.createElement('tr');for(let x of [i+1,s.name]){let td=document.createElement('td');td.textContent=x;tr.appendChild(td)}tbody.appendChild(tr)}if(pts.length){let xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);svg.setAttribute('viewBox',[Math.min(...xs)-100,Math.min(...ys)-100,Math.max(...xs)-Math.min(...xs)+200,Math.max(...ys)-Math.min(...ys)+200].join(' '))}}function zoom(f){let b=svg.getAttribute('viewBox').split(' ').map(Number);svg.setAttribute('viewBox',[b[0]+b[2]*(1-f)/2,b[1]+b[3]*(1-f)/2,b[2]*f,b[3]*f].join(' '))}svg.onwheel=e=>{e.preventDefault();zoom(e.deltaY>0?1.15:.87)};let drag=null;svg.onpointerdown=e=>{drag=[e.clientX,e.clientY,svg.getAttribute('viewBox').split(' ').map(Number)];svg.setPointerCapture(e.pointerId)};svg.onpointermove=e=>{if(!drag)return;let [x,y,b]=drag;svg.setAttribute('viewBox',[b[0]-(e.clientX-x)*b[2]/svg.clientWidth,b[1]-(e.clientY-y)*b[3]/svg.clientHeight,b[2],b[3]].join(' '))};svg.onpointerup=()=>drag=null;show();</script></html>'''.replace('DATA',data)
    page=page.replace('<meta charset="utf-8">','<meta charset="utf-8"><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"><style>#basemap{height:650px;width:100%}#basemap .leaflet-tile-pane{filter:grayscale(1) saturate(0) brightness(1.06) contrast(.85)}#tile-status{font-size:14px;color:#805200}</style>',1)
    page=page.replace('<svg id="map">','<p id="tile-status">Загрузка картографической подложки… Для неё нужен интернет.</p><div id="basemap" hidden></div><svg id="map">',1)
    page=page.replace('Подложка: геометрия улиц, входящих в маршрут; интернет не требуется.','Серая подложка OpenStreetMap: улицы и здания; для загрузки карты нужен интернет. При недоступности сервиса сохраняется схема маршрута.')
    enhancement=r"""<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
(function(){
 const status=document.getElementById('tile-status');
 if(typeof L==='undefined'){status.textContent='Картографическая библиотека недоступна. Показана схема маршрута; проверьте интернет и обновите страницу.';return;}
 const box=document.getElementById('basemap');box.hidden=false;svg.style.display='none';
 const base=L.map('basemap',{preferCanvas:true}).setView([69.35,88.2],13);
 const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(base);
 let failed=0;
 tiles.on('loading',()=>{failed=0;status.textContent='Загрузка карты…';});
 tiles.on('tileerror',()=>{failed++;status.textContent='Часть подложки не загрузилась. Маршрут и остановки остаются видны. Проверьте интернет.';});
 tiles.on('load',()=>{if(!failed)status.textContent='Подложка OpenStreetMap загружена.';});
 const layer=L.featureGroup().addTo(base),originalShow=show;
 base.createPane('directionArrows');base.getPane('directionArrows').style.zIndex=450;
 base.getPane('directionArrows').style.pointerEvents='none';
 const arrows=L.layerGroup().addTo(base);
 function drawArrows(){
  arrows.clearLayers();if(!current)return;
  let count=0;
  for(const part of current.parts){
   let remaining=50;
   for(let i=0;i+1<part.length;i++){
    const a=base.latLngToLayerPoint([part[i][1],part[i][0]]),b=base.latLngToLayerPoint([part[i+1][1],part[i+1][0]]);
    const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy);if(len<.01)continue;
    const ux=dx/len,uy=dy/len;
    while(remaining<=len && count<1500){
     const x=a.x+ux*remaining,y=a.y+uy*remaining;
     const points=[[x-ux*9-uy*5,y-uy*9+ux*5],[x,y],[x-ux*9+uy*5,y-uy*9-ux*5]].map(p=>base.layerPointToLatLng(p));
     L.polyline(points,{pane:'directionArrows',color:'#fff',weight:6,opacity:.95,interactive:false}).addTo(arrows);
     L.polyline(points,{pane:'directionArrows',color:'#06416e',weight:3,opacity:1,interactive:false}).addTo(arrows);
     count++;remaining+=100;
    }
    remaining-=len;
   }
  }
 }
 base.on('zoomend moveend',drawArrows);
 show=function(){originalShow();layer.clearLayers();
  for(const part of current.parts){if(part.length>1)L.polyline(part.map(p=>[p[1],p[0]]),{color:'#1267ac',weight:5,opacity:.9}).addTo(layer);}
  for(const [i,s] of current.stops.entries()){const label=document.createElement('span');label.textContent=(i+1)+'. '+s.name;L.circleMarker([s.lat,s.lon],{radius:5,color:'#fff',weight:1,fillColor:'#c32f35',fillOpacity:1}).bindTooltip(label).addTo(layer);}
  const bounds=layer.getBounds();if(bounds.isValid())base.fitBounds(bounds,{padding:[25,25],maxZoom:16});drawArrows();
 };
 zoom=function(f){if(f<1)base.zoomIn();else base.zoomOut();};
 show();base.invalidateSize();
})();
</script>"""
    page=page.replace('</html>',enhancement+'</html>')
    (out/'results.html').write_text(page,encoding='utf-8');print('Full route directions:',len(routes));print('Continuous with ordered stops:',sum(r['status']=='continuous_ordered_geometry' for r in routes));print(out/'results.html')
if __name__=='__main__':main()
