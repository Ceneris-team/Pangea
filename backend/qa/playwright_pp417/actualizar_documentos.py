"""Amplía los cinco documentos compartidos de Pangea a v0.15 para PP-417."""
from pathlib import Path
from copy import copy
import re,hashlib,json
import openpyxl
from openpyxl.workbook.properties import CalcProperties
from docx import Document
ROOT=Path(__file__).resolve().parents[3]
QA=ROOT/'backend/qa'; EV=QA/'03_Evidencias/HU-27'
FECHA='04/11/2026'; COMMIT='5430e91 (origin/dev, copia aislada Pangea-pp417)'
API=['paginacion_invalida[parametros0]','paginacion_invalida[parametros1]','paginacion_invalida[parametros2]','segunda_pagina_sin_duplicados','busqueda_sin_coincidencias','filtro_no_elimina_datos','sesion_ausente']
UI=['CA1 tabla con columnas y 10 alarmas propias','CA2 filtro Activa e Inactiva y limpiar','CA3 búsqueda parcial y combinada','paginación y reinicio al filtrar','sin coincidencias conserva Crear alarma','usuario sin alarmas: mensaje y Crear alarma habilitado']
REQS=['Paginación inválida devuelve 422','Paginación inválida devuelve 422','Paginación inválida devuelve 422','Página 2 completa sin duplicados','Búsqueda inexistente devuelve lista vacía','Filtrar no elimina alarmas','Sin sesión devuelve 401','Tabla con cinco columnas, condición y solo alarmas propias','Filtro Activa/Inactiva y limpieza','Búsqueda parcial combinada con estado','Paginación de 10 y reinicio al filtrar','Sin coincidencias conserva Crear alarma','Sin alarmas muestra mensaje y permite Crear alarma']
MAP=[4,4,4,4,3,2,5,1,2,3,4,3,6]
def add(s,values):
 r=s.max_row+1
 # Ignora filas vacías preformateadas de las plantillas.
 used=[i for i in range(1,s.max_row+1) if s.cell(i,1).value is not None]
 r=max(used)+1
 if s.title in ('Portada','Resumen'):r=s.max_row+1
 for j,v in enumerate(values,1):
  c=s.cell(r,j,v)
  if r>2:
   src=s.cell(r-1,j);c._style=copy(src._style);c.alignment=copy(src.alignment)
 return r
files=[]
for f in QA.glob('0*/*v0.14.xlsx'):
 w=openpyxl.load_workbook(f)
 for s in w:
  for row in s:
   for c in row:
    if isinstance(c.value,str) and not c.value.startswith('='):
     c.value=c.value.replace('v0.14','v0.15')
  for h in (s.oddHeader,s.evenHeader,s.firstHeader,s.oddFooter,s.evenFooter,s.firstFooter):
   for part in (h.left,h.center,h.right):
    if part.text:part.text=part.text.replace('v0.14','v0.15')
 if 'Portada' in w:
  add(w['Portada'],['HU agregada','HU-27 Listar alarmas · PP-417 · 13/13 casos QA; 44/44 API y 6/6 UI; 47/47 frontend.'])
  add(w['Portada'],['Versión y fecha','v0.15 · '+FECHA])
 if 'Casos de Prueba' in w:
  for i,t in enumerate(API+UI):
   cid=f'CP-{462+i}'; evid=f'EV-CP-{462+i}'
   add(w['Casos de Prueba'],[cid,'HU-27',f'RQ-HU27-{MAP[i]:02}','Negativa' if i<3 or i==6 else ('E2E' if i>=7 else 'Funcional'),'Alta','Cliente Final','Postgres local aislado; sesión y alarmas según el caso','Ejecutar '+t,'13 propias, 1 ajena; estados Activa/Inactiva',REQS[i],REQS[i]+'; comprobado con aserciones','Aprobado','—',evid,'QA',FECHA,('test_hu27_qa.py::test_'+t) if i<7 else 'pp417.spec.mjs::'+t,'Local, dev',COMMIT])
  for n,config in [(39,'PLAN_LIMITS_REQUIRE_SUBSCRIPTION ausente'),(40,'PLAN_LIMITS_REQUIRE_SUBSCRIPTION=false')]:
   add(w['Regresión'],[f'RG-{n}','Regresión','Alarmas y casos adicionales','HU-27','Transversal','Alta','44 pruebas API','Código compartido HU27/HU28','Esta ronda','—','pytest tests/routers/test_alarmas.py tests/routers/test_hu27_qa.py','No ejecutado','Aprobado',FECHA,'QA',config+'; TEST_DATABASE_URL puerto 55432; 44 aprobadas',None,'pytest_default_negocio.html' if n==39 else 'pytest_hu27.html','BD por defecto: un control da error de conexión (OBS-60)'])
 if 'Registro' in w:
  for i in range(13):
   p=EV/('pytest_hu27.html' if i<7 else 'playwright/index.html')
   add(w['Registro'],[f'EV-CP-{462+i}',f'CP-{462+i}','HU-27','HTML',REQS[i],p.name,str(p.relative_to(ROOT)),'QA',FECHA,p.stat().st_size/1024,hashlib.sha256(p.read_bytes()).hexdigest(),COMMIT,'Disponible','Aprobado','—'])
 if 'Observaciones' in w:
  add(w['Observaciones'],['OBS-59','CP-469','HU-27','PP-222: Acciones muestra Gestionar / Disponible próximamente, sin operación. CA1 pide la columna, pero no define sus operaciones.','PO confirma el alcance de gestionar; editar/eliminar/activar no se dieron por probados.','QA',FECHA,'Abierta','Decisión del PO','Baja','PO',None,None,'La presencia visual está cubierta. No se registra defecto sin una operación exigida.'])
  add(w['Observaciones'],['OBS-60','RG-39','HU-27','La BD por defecto localhost:5432 no responde para la suite: un control termina con error de conexión.','Usar TEST_DATABASE_URL local puerto 55432. Ambas configuraciones de suscripción dan 44/44.','QA',FECHA,'Resuelta en QA','Entorno','Baja','QA',None,FECHA,'Primera corrida interrumpida; HTML del control: pytest_bd_default.html. Errores iniciales de fixtures y correo .test corregidos en scripts QA; no son producto.'])
  add(w['Historial de rondas'],[1,'HU-27',FECHA,COMMIT,13,13,0,0,0,0,2,'EV-CP-462 a EV-CP-474','44 API, 6 UI y 47 frontend aprobadas; observación de alcance OBS-59.'])
 if 'RTM' in w:
  labels=['Tabla con nombre, parámetro, condición, estado y acciones','Filtro por estado Activa/Inactiva','Búsqueda por nombre','10 registros por página y navegación','Solo alarmas propias y sesión obligatoria','Estado vacío y Crear alarma habilitado']
  for k,label in enumerate(labels,1):
   ids=[f'CP-{462+i}'for i,v in enumerate(MAP)if v==k]
   add(w['RTM'],[f'RQ-HU27-{k:02}',label,'CA-'+str(k) if k<=3 else 'Detalles de conversación','HU-27','PP-72','Alta',', '.join(ids),len(ids),'Cubierto','Aprobado','—','OBS-59: acciones visuales, operación sin definir' if k==1 else '—','RG-39, RG-40'])
  add(w['Historias'],['HU-27','HU-27','Listar alarmas','Alarmas','Listo','PP-222 Listo; PP-223 Listo; PP-224 Listo','PP-417 Listo',', '.join(f'RQ-HU27-{k:02}'for k in range(1,7)),6,6,13,13,0,0,0,'APTO CON OBSERVACIONES','Sin bloqueo; PO confirma alcance de Gestionar (OBS-59). Estados propuestos para cierre del informe.',COMMIT])
  for i in range(13):add(w['Fuente casos'],[f'CP-{462+i}','HU-27','Aprobado'])
 if 'Resumen' in w:
  add(w['Resumen'],['Resultado por historia HU-27'])
  n=13 if ('Casos de Prueba' in w or 'Registro' in w) else (6 if 'RTM' in w else 0)
  add(w['Resumen'],['HU-27',n,n,0,0,'Sin defectos nuevos; OBS-59 abierta; OBS-60 entorno'])
 w.calculation=CalcProperties(fullCalcOnLoad=True)
 out=f.with_name(f.name.replace('v0.14','v0.15'));w.save(out);files.append(out)
f=next(QA.glob('01*/*v0.14.docx'));d=Document(f)
for p in d.paragraphs:
 for r in p.runs:r.text=r.text.replace('v0.14','v0.15')
d.paragraphs[1].add_run(' Incluye HU-27 Listar alarmas (PP-417, 04/11/2026).')
for sec in d.sections:
 for area in (sec.header,sec.footer,sec.first_page_header,sec.first_page_footer):
  for p in area.paragraphs:
   for r in p.runs:
    r.text=r.text.replace('v0.14','v0.15').replace('HU-21','HU-21, HU-27')
d.add_page_break();d.add_heading('HU 27 Listar alarmas',1)
d.add_paragraph('PP-417 · v0.15 · 04/11/2026. Entorno local, origin/dev 5430e91. Estrategia aprobada por el usuario. 13 casos propios QA aprobados; 44 API, 6 UI y 47 pruebas de frontend aprobadas. OBS-59 conserva la decisión sobre el alcance funcional de Gestionar.')
d.add_heading('Entra en este plan para HU 27',2)
d.add_paragraph('Tabla, filtro Activa/Inactiva, búsqueda parcial y combinada, aislamiento por dueño, paginación de 10, mensaje vacío, Crear alarma visible y habilitado, navegación al formulario y sesión ausente.')
d.add_heading('Queda fuera para HU 27',2)
d.add_paragraph('Modificar, eliminar o activar alarmas: no se definen operaciones en los CA. Carga, estrés, escaneo, accesibilidad, producción y cobertura de líneas: sin requisito. OBS-59: confirmar con el PO qué acciones corresponden a esta HU.')
t=d.add_table(rows=1, cols=5);t.style=d.tables[0].style
for c,v in zip(t.rows[0].cells,['Herramienta','Tipo','Fundamento','Qué se valida','Evidencia']):c.text=v
for row in [('pytest + pytest-html','API y regresión','El endpoint filtra por dueño y valida paginación','CA1-3 y aislamiento','pytest_hu27.html; pytest_default_negocio.html'),('Playwright Edge','UI E2E real','Verificar pantalla con API y PostgreSQL','Tabla, filtros, paginación y estado vacío','playwright/index.html; capturas PNG')]:
 for c,v in zip(t.add_row().cells,row):c.text=v
d.add_heading('Cobertura agregada por QA',2)
d.add_paragraph('Siete casos de API adicionales y seis de UI. Las 37 pruebas existentes incluyen HU27 y HU28 y se conservan como regresión. Se ejecutaron 44 casos con la regla de suscripción por defecto y 44 con PLAN_LIMITS_REQUIRE_SUBSCRIPTION=false, siempre contra TEST_DATABASE_URL en 55432. Con la conexión de BD por defecto solo se ejecutó un control: error de entorno OBS-60. No se ejecutó la suite completa de backend. Matriz de comportamiento omitida: no combina ejes con resultados distintos.')
out=f.with_name(f.name.replace('v0.14','v0.15'));d.save(out);files.append(out)
for f in files:assert f.exists() and f.stat().st_size>0
(EV/'documentos_generados.json').write_text(json.dumps([str(f)for f in files],indent=2),encoding='utf8')
print('5 documentos v0.15 guardados; CP-462 a CP-474; RG-39/40; OBS-59/60')


