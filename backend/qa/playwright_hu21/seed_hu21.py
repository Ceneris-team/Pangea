"""Datos locales de QA HU-21 (solo BD pangea_e2e_hu21). Vuelve a un estado conocido.

Uso, desde backend/ del worktree y con DATABASE_URL apuntando a pangea_e2e_hu21:
    python <ruta>/seed_hu21.py
Imprime un JSON con los ids que usan Playwright y test_hu21_ws_real.py.
"""

import datetime as dt
import json

from app.database import SessionLocal
from app.models import (
    Cliente,
    ConexionFTP,
    Dispositivo,
    LimitePlan,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    PermisoUbicacion,
    PermisoUsuarioSede,
    PlanSuscripcion,
    Rol,
    Sede,
    Suscripcion,
    Telemetria,
    Ubicacion,
    Usuario,
    UsuarioCliente,
    UsuarioProyecto,
)
from app.scripts.seed_usuarios_prueba import PASSWORD_PRUEBA
from app.security.hashing import hash_password
from app.services.limites_plan import fecha_comercial

POLIGONO = {"type": "Polygon", "coordinates": [[[-77.043, -12.046], [-77.042, -12.0462],
            [-77.0421, -12.047], [-77.0432, -12.0468], [-77.043, -12.046]]]}


def obtener(db, modelo, filtro, **valores):
    fila = db.query(modelo).filter_by(**filtro).first()
    if fila is None:
        fila = modelo(**filtro, **valores)
        db.add(fila)
        db.flush()
    return fila


def empresa(db, nombre, ruc, plan):
    cliente = obtener(db, Cliente, {"rc": ruc}, rzn_scl=nombre, crr_cntct=f"{ruc}@hu21.pangea-dev.com", estd="Activo")
    obtener(db, Suscripcion, {"id_clnt": cliente.id_clnt, "id_pln": plan.id_pln},
            fch_inc=fecha_comercial(), fch_vncmnt=fecha_comercial() + dt.timedelta(days=30), estd="Activa")
    return cliente


def proyecto(db, sede, nombre, estado="Activa"):
    fila = obtener(db, Ubicacion, {"id_sd": sede.id_sd, "nmbr": nombre}, dscrpcn="QA HU-21",
                   lttd=-12.0464, lngtd=-77.0428, plgn_gjsn=POLIGONO)
    fila.estd = estado
    conexion = obtener(db, ConexionFTP, {"id_sd": sede.id_sd, "nmbr": f"DL {nombre}"}, prtcl="FTP",
                       hst="127.0.0.1", prt=21, usr_ftp="usr", crdncl_cfrd="cifrado-qa", rt_rmt="/data",
                       frcnc_mnts=1, estd="Activa")
    disp = obtener(db, Dispositivo, {"id_ubccn": fila.id_ubccn, "nmbr": f"Datalogger {nombre} {sede.nmbr}"},
                   id_cnxn=conexion.id_cnxn, mrc="Campbell", lttd=-12.0464, lngtd=-77.0428, estd="Activo")
    parametro = obtener(db, Parametro, {"nmbr": f"Nivel {fila.id_ubccn} QA"}, undd="m", dscrpcn="QA", tipo_dato="numerico")
    mapeo = obtener(db, MapeoFormato, {"id_dspstv": disp.id_dspstv, "tp_trm": "H"}, dlmtdr=",", fl_inc_dts=1,
                    frmt_fch="%Y-%m-%d %H:%M:%S")
    obtener(db, MapeoColumna, {"id_mp": mapeo.id_mp, "indc_clmn": 1}, id_prmtr=parametro.id_prmtr)
    if db.query(Telemetria).filter_by(id_dspstv=disp.id_dspstv).count() == 0:
        ahora = dt.datetime.now(dt.timezone.utc)
        for minutos in (5, 10, 15):
            db.add(Telemetria(fch_hr=ahora - dt.timedelta(minutes=minutos), id_dspstv=disp.id_dspstv,
                              id_prmtr=parametro.id_prmtr, id_sd=sede.id_sd, vlr=10 + minutos))
    db.flush()
    return fila, disp


def cuenta(db, correo, nombre, rol, scp):
    return obtener(db, Usuario, {"crr": correo}, id_rl=rol.id_rl, scp=scp, nmbr_cmplt=nombre,
                   cntrsn_hsh=hash_password(PASSWORD_PRUEBA), estd="Activo", dbe_cmbr_pswrd=False)


def miembro(db, usuario, cliente, rol, proyectos=()):
    fila = obtener(db, UsuarioCliente, {"id_usr": usuario.id_usr, "id_clnt": cliente.id_clnt}, rol_emp=rol, estd="Activo")
    fila.rol_emp, fila.estd = rol, "Activo"
    db.query(UsuarioProyecto).filter_by(id_mmb=fila.id_mmb).delete()
    for item in proyectos:
        db.add(UsuarioProyecto(id_mmb=fila.id_mmb, id_ubccn=item.id_ubccn))
    db.flush()
    return fila


def main():
    db = SessionLocal()
    plan = obtener(db, PlanSuscripcion, {"nmbr": "Plan QA HU-21"}, prc_mnsl=100, funcionalidades=["tableros"])
    obtener(db, LimitePlan, {"id_pln": plan.id_pln}, mx_sds=0, mx_ubccns=50, mx_dspstvs=50, mx_usrs=50)
    a = empresa(db, "QA Andina", "20000000021", plan)
    b = empresa(db, "QA Sur", "20000000022", plan)
    s1 = obtener(db, Sede, {"id_clnt": a.id_clnt, "nmbr": "Sede Lima"}, estd="Activa")
    s2 = obtener(db, Sede, {"id_clnt": a.id_clnt, "nmbr": "Sede Cusco"}, estd="Activa")
    sb = obtener(db, Sede, {"id_clnt": b.id_clnt, "nmbr": "Sede Arequipa"}, estd="Activa")
    p1, d1 = proyecto(db, s1, "Norte QA")
    p2, d2 = proyecto(db, s1, "Relaves QA")
    p3, d3 = proyecto(db, s2, "Norte QA")
    pi, _ = proyecto(db, s1, "Antiguo QA", "Inactiva")
    pb, db_disp = proyecto(db, sb, "Norte QA")

    rol_cf = db.query(Rol).filter_by(nmbr="Cliente Final").one()
    rol_emp = obtener(db, Rol, {"nmbr": "Usuario Empresa"}, dscrpcn="Usuario Empresa")
    cf = cuenta(db, "cf@hu21.pangea-dev.com", "Clara Final", rol_cf, "por_sede")
    for modulo, nivel in (("Tableros", "Edición"), ("Dispositivos", "Lectura"),
                          ("Ubicaciones", "Lectura"), ("Alarmas", "Edición")):
        obtener(db, PermisoUsuarioSede, {"id_usr": cf.id_usr, "id_sd": s1.id_sd, "mdl": modulo},
                id_rl=rol_cf.id_rl, nvl=nivel)
    db.query(Usuario).filter(Usuario.crr.like("%@pangea-dev.com")).update({"dbe_cmbr_pswrd": False}, synchronize_session=False)
    db.query(PermisoUbicacion).filter_by(id_usr=cf.id_usr).delete()
    db.add(PermisoUbicacion(id_usr=cf.id_usr, id_ubccn=p1.id_ubccn))

    admin_a = cuenta(db, "admin-a@hu21.pangea-dev.com", "Ada Administradora", rol_emp, "por_cliente")
    tec_a = cuenta(db, "tec-a@hu21.pangea-dev.com", "Tito Tecnico", rol_emp, "por_cliente")
    lector = cuenta(db, "lector@hu21.pangea-dev.com", "Lia Lectora", rol_emp, "por_cliente")
    lector2 = cuenta(db, "lector2@hu21.pangea-dev.com", "Leo Lector", rol_emp, "por_cliente")
    admin_b = cuenta(db, "admin-b@hu21.pangea-dev.com", "Bea Sur", rol_emp, "por_cliente")
    m_admin_a = miembro(db, admin_a, a, "Administrador")
    m_tec_a = miembro(db, tec_a, a, "Tecnico")
    m_lector = miembro(db, lector, a, "Lector", [p1])
    m_lector2 = miembro(db, lector2, a, "Lector", [p1, p2])
    m_admin_b = miembro(db, admin_b, b, "Administrador")
    db.commit()
    print(json.dumps({
        "a": a.id_clnt, "b": b.id_clnt, "p1": p1.id_ubccn, "p2": p2.id_ubccn, "p3": p3.id_ubccn, "pi": pi.id_ubccn,
        "pb": pb.id_ubccn, "cf": cf.id_usr, "m_admin_a": m_admin_a.id_mmb, "m_tec_a": m_tec_a.id_mmb,
        "m_lector": m_lector.id_mmb, "m_lector2": m_lector2.id_mmb, "m_admin_b": m_admin_b.id_mmb,
        "d1": d1.id_dspstv, "d2": d2.id_dspstv, "d3": d3.id_dspstv, "db": db_disp.id_dspstv,
    }))
    db.close()


if __name__ == "__main__":
    main()
