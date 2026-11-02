import json,html,collections
from pathlib import Path
root=Path(__file__).resolve().parent
def build():
    d=json.loads((root/'output/schedule_import.json').read_text(encoding='utf-8'))
    issues=collections.Counter((x['file'],x['sheet'],x['issue']) for x in d['issues'])
    rows=''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in (*k,n))+'</tr>' for k,n in issues.items())
    report='<meta charset="utf-8"><title>Проверка расписаний</title><style>body{font:17px system-ui;max-width:1100px;margin:40px auto}td,th{padding:8px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}</style><h1>Расписания: импорт и проверка</h1><p>Исходные 24 файла сохранены без изменений в data/schedules. Координаты ячеек и источники каждого рейса сохраняются. Таблицы расписаний пока не подключены к оптимизатору новых трасс: сопоставление остановок с географией не завершено.</p><pre>'+html.escape(json.dumps({k:v for k,v in d.items() if k!='issues'},ensure_ascii=False,indent=2))+'</pre><h2>Требуют проверки</h2><p>non_monotonic_times: нарушена последовательность времени. unknown_calendar_or_route: не определён маршрут или календарь, либо заголовок конфликтует с названием листа. Строки не исправляются выдуманными значениями.</p><table><tr><th>Файл</th><th>Лист</th><th>Причина</th><th>Строк</th></tr>'+rows+'</table><h2>Новая постановка</h2><p>Новые трассы — центральный район. Начальные точки должны соответствовать реальным жилым зданиям. Сравнение должно учитывать конкретные отправления, пешеходные подходы, пересадки и оба направления нового маршрута. До завершения этой проверки прежний промышленный вариант не является рекомендацией.</p>'
    (root/'output/schedule_report.html').write_text(report,encoding='utf-8')
if __name__=='__main__':build()
