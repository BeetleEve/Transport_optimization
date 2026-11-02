"""Earliest arrival on supplied timetable; transfers at identically named stops."""
import argparse,bisect,heapq,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def name(value):
    value=value.lower().replace('ё','е').replace('улица','ул').replace('проспект','пр').replace('магазин','маг')
    return re.sub(r'[^а-яa-z0-9]','',value)

def build(day='weekday'):
    trips=json.loads((ROOT/'data/schedules/trips.json').read_text(encoding='utf-8'));graph={};labels={}
    for trip in trips:
        if trip['calendar'] not in (day,'daily'):continue
        events=trip['events']
        # Direct connections to all subsequent stops preserve staying on the bus.
        for i,a in enumerate(events):
            if a['departure'] is None:continue
            u=name(a['stop']);labels[u]=a['stop']
            for b in events[i+1:]:
                if b['arrival'] is None:continue
                v=name(b['stop']);labels[v]=b['stop']
                if u==v or b['arrival']<a['departure']:continue
                graph.setdefault(u,[]).append((a['departure'],b['arrival'],v,trip['route'],trip['id'],trip['sources'][0]))
    for u in graph:graph[u].sort()
    return graph,labels

def route(graph,origin,destination,start,transfer_min=2):
    queue=[(start,origin)];arrivals={origin:start};parents={}
    while queue:
        now,u=heapq.heappop(queue)
        if now!=arrivals[u]:continue
        if u==destination:break
        ready=now+(transfer_min if u!=origin else 0)
        for departure,arrival,v,line,trip,source in graph.get(u,[]):
            if departure<ready or arrival>=arrivals.get(v,float('inf')):continue
            arrivals[v]=arrival;parents[v]=(u,departure,arrival,line,trip,source);heapq.heappush(queue,(arrival,v))
    if destination not in arrivals:return None
    result=[];v=destination
    while v!=origin:
        u,dep,arr,line,trip,source=parents[v];result.append(dict(origin=u,destination=v,departure=dep,arrival=arr,route=line,trip=trip,source=source));v=u
    return list(reversed(result))

def main():
    p=argparse.ArgumentParser();p.add_argument('--from-stop',required=True);p.add_argument('--to-stop',required=True);p.add_argument('--time',default='08:00');p.add_argument('--day',choices=['weekday','weekend'],default='weekday');a=p.parse_args()
    g,labels=build(a.day);h,m=map(int,a.time.split(':'));answer=route(g,name(a.from_stop),name(a.to_stop),60*h+m)
    if answer is None:print('No journey found for these names and this service day.');return
    for leg in answer:
        leg['origin']=labels[leg['origin']];leg['destination']=labels[leg['destination']]
        for key in ('departure','arrival'):
            value=round(leg[key]);leg[key]=f'{value//60:02}:{value%60:02}'
    print(json.dumps(answer,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
