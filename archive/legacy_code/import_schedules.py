from pathlib import Path
import json,shutil,hashlib,datetime
import openpyxl,xlrd
NAMES=['1b.xlsx','1a.xlsx','33 (1).xlsx','40.xls','41.xls','2.xls','4.xls','5b.xlsx','5a.xls','6.xls','7B (1).xls','11.xls','12.xls','14ab.xls','14ab (1).xls','15.xls','16 А.xls','16 Б.xlsx','17.xls','22.xls','23.xls','24.xls','31.xlsx','31 (1).xlsx']
def main():
    root=Path(__file__).resolve().parent;dest=root/'data'/'schedules';dest.mkdir(exist_ok=True);books=[]
    for name in NAMES:
        p=dest/name
        if not p.exists():shutil.copy2(Path('C:/Users/golob/Downloads')/name,p)
        sheets=[]
        if p.suffix=='.xlsx':
            wb=openpyxl.load_workbook(p,data_only=True)
            for sh in wb:
                rows=[]
                for row in sh:
                    cells=[{'cell':c.coordinate,'value':str(c.value) if isinstance(c.value,(datetime.time,datetime.datetime)) else c.value} for c in row if c.value is not None]
                    if cells:rows.append(cells)
                sheets.append({'name':sh.title,'rows':rows})
        else:
            wb=xlrd.open_workbook(p)
            for sh in wb.sheets():
                rows=[]
                for r in range(sh.nrows):
                    cells=[]
                    for c in range(sh.ncols):
                        cell=sh.cell(r,c)
                        if cell.ctype in (0,6):continue
                        val=cell.value
                        if cell.ctype==3:val=xlrd.xldate_as_datetime(val,wb.datemode).isoformat()
                        cells.append({'cell':openpyxl.utils.get_column_letter(c+1)+str(r+1),'value':val})
                    if cells:rows.append(cells)
                sheets.append({'name':sh.name,'rows':rows})
        books.append({'file':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'sheets':sheets})
    (dest/'extracted.json').write_text(json.dumps(books,ensure_ascii=False,indent=2),encoding='utf-8')
    for b in books:
        print(b['file'])
        for sh in b['sheets']:
            print(sh['name'],len(sh['rows']));print(str(sh['rows'][:9]))
if __name__=='__main__':main()
