"""Exhaustive timetable phase optimization at a named interchange."""
import bisect,csv,hashlib,html,json,math,statistics
from pathlib import Path
from timetable_router import name
ROOT=Path(__file__).resolve().parent

def hh(value):
    seconds=round(value*60);return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'

def load_patterns(day,hub):
    trips=json.loads((ROOT/'data/schedules/trips.json').read_text(encoding='utf-8'));patterns={}
    for t in trips:
        if t['calendar'] not in (day,'daily') or t['route']=='unknown':continue
        signature=(t['route'],name(t['events'][0]['stop']),name(t['events'][-1]['stop']))
        pid=hashlib.sha256(repr(signature).encode()).hexdigest()[:12]
        for idx,e in enumerate(t['events']):
            if name(e['stop'])!=name(hub):continue
            # A repeated visit to the hub is a distinct position in a pattern.
            key=pid+':'+str(sum(name(v['stop'])==name(hub) for v in t['events'][:idx]))
            p=patterns.setdefault(key,dict(route=t['route'],origin=t['events'][0]['stop'],destination=t['events'][-1]['stop'],arrivals=[],departures=[]))
            source=t['sources'][0]
            if idx>0 and e['arrival'] is not None:p['arrivals'].append((e['arrival'],t['id'],source,e['arrival_cell']))
            if idx<len(t['events'])-1 and e['departure'] is not None:p['departures'].append((e['departure'],t['id'],source,e['departure_cell']))
    return trips,patterns

def evaluate(patterns,requests,buffer,shift_route=None,shift=0,details=False):
    deps={p:sorted((v[0]+(shift if x['route']==shift_route else 0),v[1]) for v in x['departures']) for p,x in patterns.items()}
    rows=[];waits=[];missed=0
    for p,q,event in requests:
        arrival=event[0]+(shift if patterns[p]['route']==shift_route else 0)
        times=deps[q];idx=bisect.bisect_left(times,(arrival+buffer,''))
        if idx==len(times):wait=None;missed+=1;departure=None;trip=None
        else:departure,trip=times[idx];wait=departure-arrival;waits.append(wait)
        if details:rows.append(dict(incoming_pattern=p,outgoing_pattern=q,arrival_trip=event[1],arrival=arrival,departure=departure,wait=wait,departure_trip=trip,source=event[2],cell=event[3]))
    return {'missed':missed,'mean_wait':statistics.mean(waits) if waits else math.inf,'sum_wait':sum(waits),'p90_wait':sorted(waits)[min(len(waits)-1,int(.9*len(waits)))] if waits else None,'max_wait':max(waits) if waits else None},rows

def main():
    config_path=ROOT/'optimization_config.json'
    cfg=json.loads(config_path.read_text(encoding='utf-8'))
    trips,patterns=load_patterns(cfg['day'],cfg['hub'])
    requests=[(p,q,e) for p,a in patterns.items() for e in a['arrivals'] if cfg['start_min']<=e[0]<cfg['end_min'] for q,b in patterns.items() if a['route']!=b['route'] and sum(cfg['start_min']<=v[0]<cfg['end_min'] for v in b['departures'])>=cfg['min_departures_in_window']]
    if not requests:raise ValueError('No source-backed transfer opportunities at the requested hub')
    baseline,before=evaluate(patterns,requests,cfg['transfer_min'],details=True)
    ranking=[];best=(baseline['missed'],baseline['sum_wait'],0);choice=(None,0)
    for r in sorted({p['route'] for p in patterns.values()}):
        for shift in range(-cfg['max_shift_min'],cfg['max_shift_min']+1):
            if shift==0:continue
            m,_=evaluate(patterns,requests,cfg['transfer_min'],r,shift)
            ranking.append(dict(route=r,shift_min=shift,**m))
            score=(m['missed'],m['sum_wait'],abs(shift))
            if score<best:best=score;choice=(r,shift)
    after,after_rows=evaluate(patterns,requests,cfg['transfer_min'],*choice,details=True)
    comparable=[(a['wait'],b['wait']) for a,b in zip(before,after_rows) if a['wait'] is not None and b['wait'] is not None]
    sensitivity=[]
    for buffer in [2,3,5,8]:
        a,_=evaluate(patterns,requests,buffer);b,_=evaluate(patterns,requests,buffer,*choice);sensitivity.append(dict(transfer_min=buffer,before=a,after=b))
    out=ROOT/'output';out.mkdir(exist_ok=True)
    result=dict(config=cfg,patterns=len(patterns),transfer_opportunities=len(requests),candidates=len(ranking),selected_route=choice[0],shift_min=choice[1],before=baseline,after=after,improved=sum(b<a-1e-8 for a,b in comparable),worsened=sum(b>a+1e-8 for a,b in comparable),unchanged=sum(abs(b-a)<=1e-8 for a,b in comparable),sensitivity=sensitivity,objective='Lexicographic minimum: missed connections, then sum waiting minutes, then absolute shift. Equal weight per arriving trip and outgoing route pattern. Not measured passenger demand.',scope='One route shifted uniformly for all its imported trips on selected service day. No geometry change or trip removal. Vehicle blocks and other hubs are not assessed.')
    (out/'optimization_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'transfer_before_after.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['incoming_route','incoming_origin','outgoing_route','outgoing_destination','arrival_before','arrival_after','departure_before','departure_after','wait_before_min','wait_after_min','saved_min','arrival_source','source_cell'])
        for a,b in zip(before,after_rows):
            p=patterns[a['incoming_pattern']];q=patterns[a['outgoing_pattern']]
            w.writerow([p['route'],p['origin'],q['route'],q['destination'],hh(a['arrival']),hh(b['arrival']),hh(a['departure']) if a['departure'] is not None else '',hh(b['departure']) if b['departure'] is not None else '',a['wait'],b['wait'],a['wait']-b['wait'] if a['wait'] is not None and b['wait'] is not None else '',json.dumps(a['source'],ensure_ascii=False),a['cell']])
    with (out/'schedule_proposal.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['route','trip_id','stop','event','before','proposed','file','sheet','cell'])
        for t in trips:
            if t['route']!=choice[0] or t['calendar'] not in ('daily',cfg['day']):continue
            for e in t['events']:
                for kind in ('arrival','departure'):
                    if e[kind] is None:continue
                    src=t['sources'][0];w.writerow([t['route'],t['id'],e['stop'],kind,hh(e[kind]),hh(e[kind]+choice[1]),src['file'],src['sheet'],e[kind+'_cell']])
    with (out/'optimization_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['route','shift_min','missed','mean_wait','sum_wait','p90_wait','max_wait']);w.writeheader();w.writerows(ranking)
    def table(rows):return '<table>'+''.join('<tr>'+''.join('<td>'+html.escape(str(c))+'</td>' for c in row)+'</tr>' for row in rows)+'</table>'
    report='<meta charset="utf-8"><title>Норильск — согласование пересадок</title><style>body{font:18px system-ui;max-width:1100px;margin:40px auto;color:#21354b}td{padding:10px;border-bottom:1px solid #ddd}a{color:#0666aa}</style><h1>Согласование пересадок на остановке '+html.escape(cfg['hub'])+'</h1>'
    report+=f'<p>Предложение: сдвинуть расписание маршрута {html.escape(str(choice[0]))} на {choice[1]:+d} минут. Проверены {len(ranking)} вариантов. Число рейсов, интервалы и продолжительность каждого рейса сохраняются.</p>'
    report+=table([['Показатель','Было','Стало'],['Среднее ожидание, мин',round(baseline['mean_wait'],2),round(after['mean_wait'],2)],['90-й процентиль ожидания, мин',round(baseline['p90_wait'],2),round(after['p90_wait'],2)],['Без последующего рейса',baseline['missed'],after['missed']],['Улучшено / ухудшено возможностей пересадки',result['improved'],result['worsened']]])
    report+='<p>Каждая возможность — прибытие одного рейса и пересадка на одно другое направление. Это не число пассажиров. Период и минимальное время пересадки заданы в optimization_config.json. Данные — предоставленные пользователем таблицы; актуальность расписаний на сегодняшнюю дату отдельно не подтверждена.</p><p><a href="transfer_before_after.csv">Все пересадки: было и стало</a> · <a href="schedule_proposal.csv">Предлагаемое расписание с исходными ячейками</a> · <a href="optimization_candidates.csv">Все проверенные варианты</a></p><h2>Устойчивость к времени перехода</h2>'
    report+=table([['Переход, мин','Среднее было','Среднее стало']]+[[x['transfer_min'],round(x['before']['mean_wait'],2),round(x['after']['mean_wait'],2)] for x in sensitivity])
    report+='<h2>Границы решения</h2><p>Это оптимизация согласования расписаний в одном узле, а не всей маршрутной сети. Сопоставление по названию АДЦ объединяет платформы: фактический переход между ними требует проверки. Не оценены пересадки в других узлах, привязки водителей и автобусов, спрос, пассажировместимость и обязательные времена начала/конца работы. Таблицы с конфликтующим календарём и некорректной последовательностью времени исключены при импорте. Оригиналы не менялись. Предложение должно пройти проверку перевозчика перед внедрением.</p>'
    (out/'optimization_report.html').write_text(report,encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sensitivity','objective','scope')},ensure_ascii=False,indent=2));print(out/'optimization_report.html')
if __name__=='__main__':main()
