import json
from pathlib import Path
import openpyxl
from docx import Document
ROOT = Path(__file__).resolve().parents[3]
data = []
for p in ROOT.glob('0*/*v0.15.xlsx'):
    w = openpyxl.load_workbook(p, data_only=False)
    entry = {'path': str(p), 'sheets': []}
    for s in w:
        rows = []
        for row in s:
            vals = [c.value for c in row]
            if row[0].row <= 4 or any(isinstance(v, str) and any(t in v for t in ['HU-21','PP-185','DEF-10','DEF-11','RG-37','RG-38','CP-371','CP-372','CP-417','CP-461']) for v in vals):
                rows.append({'row': row[0].row, 'values': vals})
        entry['sheets'].append({'name':s.title,'dimensions':s.calculate_dimension(),'rows':rows})
    data.append(entry)
print(json.dumps(data, ensure_ascii=False, default=str))
doc = Document(next(ROOT.glob('01*/*v0.15.docx')))
print('PLAN:')
for i,p in enumerate(doc.paragraphs):
    if 'HU-21' in p.text or 'PP-185' in p.text or 'DEF-1' in p.text:
        print('PARA',i,p.text)
for i,t in enumerate(doc.tables):
    for j,r in enumerate(t.rows):
        text=' | '.join(c.text for c in r.cells)
        if 'HU-21' in text or 'PP-185' in text or 'DEF-1' in text:
            print('TABLE',i,j,text)
