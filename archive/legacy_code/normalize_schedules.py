import json,re,hashlib,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def col(cell):
    result=0
    for c in re.match('[A-Z]+',cell)[0]:result=result*26+ord(c)-64
    return result

def minutes(value):
    if not isinstance(value,str):return None
    m=re.fullmatch(r'(?:\d{4}-\d\d-\d\dT)?(\d{1,2}):(\d\d)(?::(\d\d)(?:\.(\d+))?)?',value.strip())
    if not m:return None
    h,mi,se,frac=m.groups()
    if int(h)>23 or int(mi)>59:return None
    return int(h)*60+int(mi)+(int(se or 0)+float('0.'+(frac or '0')))/60

def main():
    books=json.loads((ROOT/'data/schedules/extracted.json').read_text(encoding='utf-8')); trips=[];issues=[];seen={};duplicates=0;blocks=0
    for book in books:
        for sh in book['sheets']:
            headers={};block=0;context=[];calendar='unknown';route='unknown'
            for row in sh['rows']:
                values=' '.join(str(c['value']) for c in row)
                title=re.search(r'маршрута?\s*№\s*(\d+\s*[\"«]?[АБAB]?)',values,re.I)
                if title:route=re.sub(r'[\s\"«]','',title[1]).upper().replace('A','А').replace('B','Б')
                if any('остановочные пункты' in str(c['value']).lower() for c in row):
                    headers={col(c['cell']):str(c['value']).strip() for c in row if col(c['cell'])>1};block+=1;blocks+=1
                    calendar='weekday' if 'буд' in sh['name'].lower() else 'weekend' if 'вых' in sh['name'].lower() else 'daily' if 'еж' in sh['name'].lower() else 'unknown'
                context.append(values)
                low=values.lower()
                if 'расчетное' in low or 'расчётное' in low:
                    if 'ежеднев' in low:calendar='daily'
                    elif 'будн' in low:calendar='weekday'
                    elif 'выход' in low:calendar='weekend'
                    elif 'буд' in sh['name'].lower():calendar='weekday'
                    elif 'вых' in sh['name'].lower():calendar='weekend'
                if ('вых' in sh['name'].lower() and calendar=='weekday') or ('буд' in sh['name'].lower() and calendar=='weekend'):
                    calendar='conflict'
                if not headers:continue
                cells={col(c['cell']):c for c in row};events=[]
                for c,name in sorted(headers.items()):
                    arr=minutes(cells.get(c,{}).get('value'));dep=minutes(cells.get(c+1,{}).get('value'))
                    if arr is None and dep is None:continue
                    events.append({'stop':name,'arrival':arr,'departure':dep,'arrival_cell':cells.get(c,{}).get('cell'),'departure_cell':cells.get(c+1,{}).get('cell')})
                if len(events)<2:continue
                previous=-1;shift=0;invalid=False
                for e in events:
                    for key in ('arrival','departure'):
                        value=e[key]
                        if value is None:continue
                        value+=shift
                        if value<previous:
                            if previous%1440>1200 and value%1440<240:shift+=1440;value+=1440
                            else:invalid=True
                        e[key]=value;previous=value
                source={'file':book['file'],'sheet':sh['name'],'row':int(re.search(r'\d+',row[0]['cell'])[0]),'block':block}
                if invalid:issues.append({**source,'issue':'non_monotonic_times'});continue
                signature=json.dumps([route,calendar,[(e['stop'],e['arrival'],e['departure']) for e in events]],ensure_ascii=False)
                if signature in seen:seen[signature]['sources'].append(source);duplicates+=1;continue
                trip={'id':hashlib.sha256(signature.encode()).hexdigest()[:16],'route':route,'calendar':calendar,'events':events,'sources':[source]}
                trips.append(trip);seen[signature]=trip
                if calendar in ('unknown','conflict') or route=='unknown':issues.append({**source,'issue':'unknown_calendar_or_route'})
    (ROOT/'data/schedules/trips.json').write_text(json.dumps(trips,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'files':len(books),'sheets':sum(len(b['sheets']) for b in books),'blocks':blocks,'distinct_trips':len(trips),'exact_duplicate_rows_removed':duplicates,'issues':issues,'calendars':{k:sum(t['calendar']==k for t in trips) for k in ('daily','weekday','weekend','unknown','conflict')}}
    (ROOT/'output/schedule_import.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in report.items() if k!='issues'});print('issues',len(issues))
if __name__=='__main__':main()
