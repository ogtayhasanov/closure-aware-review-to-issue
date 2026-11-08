"""Read-only inventory of candidate human annotations; no workbook writes."""
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import sys
sys.stdout.reconfigure(encoding='utf-8')

DL=Path(r'C:\Users\Ogtay\Downloads')
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def xlsx_rows(path):
    with zipfile.ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sh in wb.find('s:sheets',NS):
            target=rels[sh.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            rows=[]
            for row in ET.fromstring(z.read(target)).findall('.//s:sheetData/s:row',NS):
                values={}
                for c in row:
                    if not c.tag.endswith('}c'):continue
                    v=c.find('s:v',NS)
                    val=v.text if v is not None else ''
                    if c.attrib.get('t')=='s': val=strings[int(val)] if val else ''
                    elif c.attrib.get('t')=='inlineStr': val=''.join(c.find('s:is',NS).itertext())
                    if val: values[c.attrib['r']]=val
                if values:rows.append(values)
            yield sh.attrib['name'],rows

if __name__=='__main__':
    paths=[Path(r'C:\Users\Ogtay\Desktop\test\taxonomy_annotation_pack_FORMATTED.xlsx'),
           DL/'taxonomy_annotation_pack_FORMATTED (1).xlsx',DL/'closure_taxonomy_second_annotator_pack.xlsx',
           DL/'blinded_status_annotation_72_FORMATTED.xlsx']
    report=[]
    for p in paths:
        if not p.exists():continue
        sheets=[]
        for name,rows in xlsx_rows(p):
            # Show headers and compact counts of populated columns, not all issue text.
            counts={}
            for row in rows:
                for cell,val in row.items():
                    col=''.join(c for c in cell if c.isalpha())
                    counts[col]=counts.get(col,0)+1
            item={'sheet':name,'nonempty_rows':len(rows),'first_rows':rows[:2],'column_nonempty_counts':counts}
            sheets.append(item)
        report.append({'path':str(p),'sheets':sheets})
    out=Path(__file__).parent/'annotation_inventory.json'
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))
