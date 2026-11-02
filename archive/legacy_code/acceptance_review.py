"""Acceptance audit and human-readable scenario review; never implies missing evidence exists."""
import bisect,csv,html,json,statistics
from pathlib import Path
from timetable_router import name
ROOT=Path(__file__).resolve().parent

def main():
    out=ROOT/'output';s=json.loads((out/'optimization_summary.json').read_text(encoding='utf-8'));trips=json.loads((ROOT/'data/schedules/trips.json').read_text(encoding='utf-8'))
    selected=[t for t in trips if t['route']==s['selected_route'] and t['calendar'] in ('daily',s['config']['day'])]
    shift=s['shift_min'];groups={}
    for t in selected:
        signature=tuple(name(e['stop']) for e in t['events'])
        groups.setdefault(signature,[]).append(t)
    rows=[]
    # Fixed passenger ready times: one minute before each original departure.
    # A diagnostic on the SAME direction/service, not a prediction of passenger demand or global best journeys.
    for signature,ts in groups.items():
        for idx in range(len(signature)-1):
            dep=sorted(e['events'][idx]['departure'] for e in ts if e['events'][idx]['departure'] is not None)
            proposed=[v+shift for v in dep]
            for value in dep:
                ready=value-1;j=bisect.bisect_left(proposed,ready)
                after=proposed[j]-ready if j<len(proposed) else None
                rows.append({'route':s['selected_route'],'stop':ts[0]['events'][idx]['stop'],'ready_min':ready,'before_wait_min':1,'after_wait_min':after,'extra_wait_min':after-1 if after is not None else None})
    worse=[r for r in rows if r['extra_wait_min'] is not None and r['extra_wait_min']>1e-8];lost=sum(r['after_wait_min'] is None for r in rows)
    result={'candidate_route':s['selected_route'],'candidate_shift_min':shift,'status':'REJECTED_NO_WORSENING' if worse or lost or s['worsened'] else 'NOT_VALIDATED','accepted_change':False,'direct_service_checks':len(rows),'direct_service_worsened':len(worse),'direct_service_no_later_departure':lost,'mean_extra_wait_worsened':statistics.mean(r['extra_wait_min'] for r in worse) if worse else 0,'hub_transfer_worsened':s['worsened'],'diagnostic_scope':'Fixed ready times at every served stop on selected direction; same service only. Does not evaluate alternative routes or forecast passengers. Counterexamples to unconditional no-worsening claim.','missing_evidence':['platform matching and measured/graph walking transfers','all-network fixed-origin earliest-arrival comparison','boarding/alighting counts by stop and time','vehicle blocks, capacity, driver duties','required first and last departures','turn restrictions and bus route feasibility','travel times for candidate road geometry'],'adopted_schedule':'Original supplied timetable; no optimized operational schedule approved'}
    (out/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'direct_service_before_after.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['route']);w.writeheader();w.writerows(rows)
    with (out/'schedule_proposal.csv').open(encoding='utf-8-sig') as f:proposal=list(csv.DictReader(f))
    def esc(x):return html.escape(str(x))
    style='<style>body{font:17px/1.5 system-ui;background:#f1f5f9;color:#16324d;margin:0}main{max-width:1200px;margin:35px auto;padding:20px}section{background:white;padding:24px;border-radius:12px;margin:20px 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}thead{position:sticky;top:0;background:#e8f0f8}.warning{background:#fff0dc;border-left:5px solid #bf6411;padding:15px}input,select,button{padding:10px;font:inherit}svg{width:100%;background:#f8fafc}a{color:#0569a5}</style>'
    table='<table><thead><tr><th>Рейс</th><th>Остановка</th><th>Событие</th><th>Исходное</th><th>Кандидат</th><th>Принятое</th><th>Источник</th></tr></thead><tbody>'
    for r in proposal:table+='<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [r['trip_id'][:8],r['stop'],'Прибытие' if r['event']=='arrival' else 'Отправление',r['before'],r['proposed'],r['before'],r['file']+' / '+r['sheet']+' / '+r['cell']])+'</tr>'
    table+='</tbody></table>'
    (out/'schedule_review.html').write_text('<!doctype html><meta charset="utf-8">'+style+'<main><h1>Расписание: исходное и проверяемый вариант</h1><p class="warning">Сдвиг не принят: выявлены ухудшения. Колонка «Принятое» сохраняет исходное время. Это сравнение расписания существующей трассы; для изменённой геометрии время движения ещё не измерено.</p><input id="filter" placeholder="Остановка, рейс или время" oninput="document.querySelectorAll(\'tbody tr\').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))"><section>'+table+'</section></main>',encoding='utf-8')
    geo=json.loads((out/'route_variants.geojson').read_text(encoding='utf-8'))
    es={}
    for e in json.loads((ROOT/'data/osm.json').read_text(encoding='utf-8'))['elements']:es.setdefault((e['type'],e['id']),{}).update(e)
    nodes={i:e for (typ,i),e in es.items() if typ=='node'};roads=[]
    # Fixed local metric projection: longitude scaled by latitude, same scale on both axes.
    import math
    def xy(lon,lat):return ((lon-88.15)*111320*math.cos(math.radians(69.35)),(69.40-lat)*111320)
    for (typ,i),e in es.items():
        if typ!='way' or not e.get('tags',{}).get('highway'):continue
        coords=[xy(nodes[n]['lon'],nodes[n]['lat']) for n in e['nodes'] if n in nodes]
        if coords:roads.append('<polyline points="'+' '.join(f'{x:.1f},{y:.1f}' for x,y in coords)+'" fill="none" stroke="#cbd5df" stroke-width="3"><title>'+esc(e.get('tags',{}).get('name',''))+'</title></polyline>')
    choices={};lines=[];bounds={}
    for f in geo['features']:
        p=f['properties'];key=str(p['relation'])+'_'+str(p['from_node'])+'_'+str(p['to_node']);choices[key]='№'+p['route']+': '+p['from_name']+' → '+p['to_name'];coords=[xy(*v) for v in f['geometry']['coordinates']];bounds.setdefault(key,[]).extend(coords)
        color='#d37516' if p['variant']=='before' else '#086db9'
        lines.append('<g class="variant" data-id="'+key+'"><polyline points="'+' '.join(f'{x:.1f},{y:.1f}' for x,y in coords)+'" fill="none" stroke="'+color+'" stroke-width="10" vector-effect="non-scaling-stroke"/>'+''.join(f'<circle cx="{x}" cy="{y}" r="12" fill="#122d45"/>' for x,y in (coords[0],coords[-1]))+'</g>')
    boxes={k:[min(x for x,y in pts)-100,min(y for x,y in pts)-100,max(x for x,y in pts)-min(x for x,y in pts)+200,max(y for x,y in pts)-min(y for x,y in pts)+200] for k,pts in bounds.items()}
    page='<!doctype html><meta charset="utf-8">'+style+'<main><h1>Трассы на дорожной карте</h1><p class="warning">Все синие линии — непроверенные кандидаты. Их нельзя считать принятыми автобусными маршрутами.</p><p>Оранжевая линия — исходный путь по OSM, синяя — более короткий путь. Конечные точки участка сохранены. Масштаб осей согласован; названия улиц видны при наведении. © OpenStreetMap contributors, ODbL.</p><select id="choice" onchange="show()">'+''.join('<option value="'+k+'">'+esc(v)+'</option>' for k,v in choices.items())+'</select><button onclick="zoom(.7)">Приблизить</button><button onclick="zoom(1.4)">Отдалить</button><section><svg id="map" viewBox="0 0 5200 11200" style="height:650px">'+''.join(roads+lines)+'</svg></section></main><script>const boxes='+json.dumps(boxes)+';function show(){let k=document.getElementById("choice").value;document.querySelectorAll(".variant").forEach(e=>e.style.display=e.dataset.id===k?"":"none");document.getElementById("map").setAttribute("viewBox",boxes[k].join(" "))}function zoom(f){let m=document.getElementById("map"),b=m.getAttribute("viewBox").split(" ").map(Number);m.setAttribute("viewBox",[b[0]+b[2]*(1-f)/2,b[1]+b[3]*(1-f)/2,b[2]*f,b[3]*f].join(" "))}show();</script>'
    (out/'route_map.html').write_text(page,encoding='utf-8')
    review='<!doctype html><meta charset="utf-8">'+style+f'<main><h1>Проверка: не стало ли хуже?</h1><section><h2>Вариант №{s["selected_route"]}, сдвиг +{shift} минут — отклонён</h2><p>На АДЦ хуже стали {s["worsened"]} рассмотренных возможностей пересадки. Дополнительно проверены {len(rows)} случаев прихода на остановку за минуту до прежнего отправления: для {len(worse)} ожидание того же направления увеличилось.</p><p>Эти проверки не равны обследованию пассажиров и не заменяют поиск альтернативных поездок по всей сети. Они показывают, что прежнее утверждение об общем улучшении не доказано.</p><p class="warning">Принятых изменений сейчас нет. Исходное расписание сохраняется. Средний выигрыш одного узла не перекрывает автоматически вред другим поездкам.</p></section><section><h2>Посмотреть результаты</h2><p><a href="schedule_review.html">Таблица расписания: было, кандидат, принятое</a></p><p><a href="route_map.html">Выбор вариантов трасс на карте</a></p><p><a href="direct_service_before_after.csv">Все дополнительные проверки ожидания</a></p><p><a href="results_research.html">Предыдущие расчёты — исследовательские кандидаты</a></p></section><section><h2>Что необходимо для полной модели</h2><ul><li>Соответствие остановок расписания конкретным платформам и пешеходные пути между ними.</li><li>Посадки, высадки и заполнение салона по рейсам и времени.</li><li>Вместимость машин, привязка рейсов к автобусам, смены и обязательные первые/последние рейсы.</li><li>Разрешённые автобусные повороты и измеренные времена проезда новых участков.</li><li>Разрешение противоречий календаря и времени в исходных таблицах.</li></ul><p>Отсутствующие величины не подставляются. Новый график для изменённой геометрии пока не рассчитан: уменьшение длины не доказывает соответствующего уменьшения времени.</p></section></main>'
    old=out/'results.html'
    if old.exists():(out/'results_research.html').write_text(old.read_text(encoding='utf-8'),encoding='utf-8')
    old.write_text(review,encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
