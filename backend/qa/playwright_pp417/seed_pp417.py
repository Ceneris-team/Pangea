"""Datos exclusivos de pangea_e2e_pp417; se elimina esa BD al terminar."""
from app.database import SessionLocal
from tests.conftest import Fabrica
from tests.routers.test_alarmas import agregar_permiso, dar_suscripcion_vigente, crear_ubicacion, crear_parametro
from app.models import Alarma, CondicionAlarma
from app.security.hashing import hash_password
db = SessionLocal()
f = Fabrica(db)
rol = f.rol('Cliente Final')
sede = f.sede()
dar_suscripcion_vigente(db, sede)
ub = crear_ubicacion(db, sede)
p = crear_parametro(db, 'Nivel PP417', 'm')
for correo, cantidad in [('listado@pp417.pangea-dev.com',13), ('vacio@pp417.pangea-dev.com',0), ('otro@pp417.pangea-dev.com',1)]:
    u = f.usuario(rol=rol)
    u.crr = correo
    u.cntrsn_hsh = hash_password('QaLocal417!2026')
    u.dbe_cmbr_pswrd = False
    agregar_permiso(db,u,sede,'Alarmas','Edición',rol)
    db.flush()
    for i in range(cantidad):
        a = Alarma(id_usr=u.id_usr,id_sd=sede.id_sd,nmbr=f'Nivel {i:02}' if cantidad>1 else 'Alarma ajena',id_prmtr=p.id_prmtr,id_ubccn=ub.id_ubccn,estd='Activa' if i%2==0 else 'Inactiva')
        db.add(a); db.flush()
        db.add(CondicionAlarma(id_alrm=a.id_alrm,oprdr='>',vlr_umbrl=3.5))
db.commit()
print('3 cuentas y 14 alarmas creadas en BD aislada PP417')

