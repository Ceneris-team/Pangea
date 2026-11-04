"""
QA - PP-414 Validar HU-21 "Conceder permisos" (PP-183, PP-184, PP-185).

Se ejecuta sobre origin/dev (5430e91) en un worktree, con tokens reales: solo se
sustituye get_db, así que cada petición pasa por get_current_user como en la app.
Desde backend/ del worktree, con la BD de test migrada:
    PLAN_LIMITS_REQUIRE_SUBSCRIPTION=false \
    TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:55432/pangea_test_hu21 \
    python -m pytest <ruta>/test_hu21_qa.py --html=<ruta>/pytest_hu21.html --self-contained-html
"""

import datetime as dt
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.main import app
from app.models import (
    Exportacion,
    LimitePlan,
    LogAuditoria,
    MapeoColumna,
    MapeoFormato,
    PermisoUbicacion,
    PermisoUsuarioSede,
    PlanSuscripcion,
    Suscripcion,
    UsuarioCliente,
    UsuarioProyecto,
)
from app.models.panel_widget import Panel, PanelUbicacion
from app.routers import exportaciones as router_exportaciones
from app.routers import panel as router_panel
from app.security.jwt_auth import create_access_token
from app.services.exportaciones import ahora
from app.services.limites_plan import fecha_comercial
from tests.conftest import _engine, db_session, fabrica  # noqa: F401
from tests.routers.test_exportaciones import AlmacenFalso
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_medicion,
    crear_parametro,
    crear_ubicacion,
    mapear_parametro,
)

MSG_ANTERIOR = "Permisos actualizados correctamente"


def _suscribir(db, cliente, usuarios=20):
    plan = PlanSuscripcion(nmbr=f"QA HU21 {cliente.id_clnt}", prc_mnsl=100)
    db.add(plan)
    db.flush()
    db.add_all([
        LimitePlan(id_pln=plan.id_pln, mx_sds=0, mx_ubccns=50, mx_dspstvs=50, mx_usrs=usuarios),
        Suscripcion(
            id_clnt=cliente.id_clnt, id_pln=plan.id_pln, fch_inc=fecha_comercial(),
            fch_vncmnt=fecha_comercial() + dt.timedelta(days=30), estd="Activa",
        ),
    ])
    db.flush()


class Mundo:
    """Dos empresas: A con dos sedes (S1 con P1 y P2, S2 con P3) y B con PB."""

    def __init__(self, db, fabrica):
        self.db, self.fabrica = db, fabrica
        self.a, self.b = fabrica.cliente(), fabrica.cliente()
        _suscribir(db, self.a)
        _suscribir(db, self.b)
        self.s1, self.s2, self.sb = fabrica.sede(self.a), fabrica.sede(self.a), fabrica.sede(self.b)
        self.p1 = crear_ubicacion(db, self.s1, "Norte QA")
        self.p2 = crear_ubicacion(db, self.s1, "Relaves QA")
        self.p3 = crear_ubicacion(db, self.s2, "Norte QA")
        self.pb = crear_ubicacion(db, self.sb, "Norte QA")
        self.disp, self.parametros = {}, {}
        for proyecto, sede, clave in ((self.p1, self.s1, "p1"), (self.p2, self.s1, "p2"),
                                      (self.p3, self.s2, "p3"), (self.pb, self.sb, "pb")):
            conexion = crear_conexion(db, sede, f"DL {clave}")
            dispositivo = crear_dispositivo(db, proyecto, conexion, f"Datalogger {clave}")
            parametro = crear_parametro(db, f"Nivel {clave} QA {self.a.id_clnt}")
            mapear_parametro(db, dispositivo, parametro)
            crear_medicion(db, dispositivo, parametro, sede, valor=10)
            self.disp[clave], self.parametros[clave] = dispositivo, parametro
        self.admin = fabrica.usuario(fabrica.rol("Administrador"), scp="global")
        self.tecnico = fabrica.usuario(fabrica.rol("Técnico CENERIS"), scp="global")
        self.comercial = fabrica.usuario(fabrica.rol("Administrador Comercial"), scp="global")
        self.rol_empresa = fabrica.rol("Usuario Empresa")
        self.rol_cf = fabrica.rol("Cliente Final")
        self.cf = self._cliente_final()
        self.admin_a, self.m_admin_a = self.miembro(self.a, "Administrador")
        self.tec_a, self.m_tec_a = self.miembro(self.a, "Tecnico")
        self.lector, self.m_lector = self.miembro(self.a, "Lector", [self.p1])
        self.admin_b, self.m_admin_b = self.miembro(self.b, "Administrador")

    def _cliente_final(self):
        cuenta = self.fabrica.usuario(self.rol_cf)
        for modulo, nivel in (("Tableros", "Edición"), ("Dispositivos", "Lectura"),
                              ("Ubicaciones", "Lectura"), ("Alarmas", "Edición")):
            self.db.add(PermisoUsuarioSede(id_usr=cuenta.id_usr, id_sd=self.s1.id_sd,
                                           id_rl=self.rol_cf.id_rl, mdl=modulo, nvl=nivel))
        self.db.add(PermisoUbicacion(id_usr=cuenta.id_usr, id_ubccn=self.p1.id_ubccn))
        self.db.flush()
        return cuenta

    def miembro(self, cliente, rol, proyectos=(), usuario=None):
        usuario = usuario or self.fabrica.usuario(self.rol_empresa, scp="por_cliente")
        miembro = UsuarioCliente(id_usr=usuario.id_usr, id_clnt=cliente.id_clnt, rol_emp=rol, estd="Activo")
        self.db.add(miembro)
        self.db.flush()
        for proyecto in proyectos:
            self.db.add(UsuarioProyecto(id_mmb=miembro.id_mmb, id_ubccn=proyecto.id_ubccn))
        self.db.flush()
        return usuario, miembro

    def token(self, usuario):
        sede = None
        if usuario.scp == "por_sede":
            sede = self.db.query(PermisoUsuarioSede.id_sd).filter_by(id_usr=usuario.id_usr).first()[0]
        return create_access_token(usuario.id_usr, sede, usuario.scp, usuario.rol.nmbr)

    def h(self, usuario, **extra):
        return {"Authorization": f"Bearer {self.token(usuario)}", **extra}

    def asignadas(self, usuario):
        return {i for (i,) in self.db.query(PermisoUbicacion.id_ubccn).filter_by(id_usr=usuario.id_usr)}

    def proyectos_miembro(self, miembro):
        return {i for (i,) in self.db.query(UsuarioProyecto.id_ubccn).filter_by(id_mmb=miembro.id_mmb)}


@pytest.fixture()
def mundo(db_session, fabrica):  # noqa: F811
    return Mundo(db_session, fabrica)


@pytest.fixture()
def api(db_session):  # noqa: F811
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


def put_anterior(api, m, actor, objetivo, ids):
    return api.put(f"/usuarios/{objetivo.id_usr}/permisos-ubicaciones",
                   json={"ubicacion_ids": ids}, headers=m.h(actor))


def patch_miembro(api, m, actor, cliente, miembro, rol, estado, ids):
    return api.patch(f"/empresas/{cliente.id_clnt}/usuarios/{miembro.id_mmb}",
                     json={"rol": rol, "estado": estado, "proyecto_ids": ids}, headers=m.h(actor))


def filas_de(respuesta):
    cuerpo = respuesta.json()
    return cuerpo if isinstance(cuerpo, list) else cuerpo.get("items", [])


# ---------------------------------------------------------------- CA-01
def test_ca01_admin_ceneris_gestiona_las_dos_modalidades(api, mundo):
    m = mundo
    assert put_anterior(api, m, m.admin, m.cf, [m.p1.id_ubccn, m.p2.id_ubccn]).status_code == 200
    r = patch_miembro(api, m, m.admin, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn])
    assert r.status_code == 200, r.text


def test_ca01_admin_de_empresa_gestiona_solo_su_empresa(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn]).status_code == 200
    r = patch_miembro(api, m, m.admin_a, m.b, m.m_admin_b, "Lector", "Activo", [m.pb.id_ubccn])
    assert r.status_code == 403
    assert api.get(f"/empresas/{m.b.id_clnt}/usuarios", headers=m.h(m.admin_a)).status_code == 403


def test_ca01_miembro_de_otra_empresa_no_se_alcanza_cambiando_la_ruta(api, mundo):
    m = mundo
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_admin_b, "Lector", "Activo", [m.p1.id_ubccn])
    assert r.status_code == 404
    assert m.db.get(UsuarioCliente, m.m_admin_b.id_mmb).rol_emp == "Administrador"


@pytest.mark.parametrize("actor", ["tecnico", "comercial", "tec_a", "lector", "cf"])
def test_ca01_quien_no_administra_no_modifica_accesos_por_peticion_directa(api, mundo, actor):
    m = mundo
    quien = getattr(m, actor)
    assert put_anterior(api, m, quien, m.cf, [m.p2.id_ubccn]).status_code == 403
    assert patch_miembro(api, m, quien, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn]).status_code == 403
    assert m.asignadas(m.cf) == {m.p1.id_ubccn}
    assert m.proyectos_miembro(m.m_lector) == {m.p1.id_ubccn}


def test_ca01_tampoco_abren_el_panel_anterior(api, mundo):
    m = mundo
    for quien in (m.tecnico, m.tec_a, m.lector, m.admin_a):
        r = api.get(f"/usuarios/{m.cf.id_usr}/permisos-ubicaciones", headers=m.h(quien))
        assert r.status_code == 403, r.text


def test_ca01_sin_sesion_devuelve_401(api, mundo):
    m = mundo
    assert api.get(f"/usuarios/{m.cf.id_usr}/permisos-ubicaciones").status_code == 401
    assert api.patch(f"/empresas/{m.a.id_clnt}/usuarios/{m.m_lector.id_mmb}",
                     json={"rol": "Lector", "estado": "Activo", "proyecto_ids": []}).status_code == 401


@pytest.mark.parametrize("objetivo", ["lector", "admin_a", "admin", "tecnico", "comercial"])
def test_ca01_la_api_rechaza_el_flujo_anterior_para_otros_destinatarios(api, mundo, objetivo):
    m = mundo
    quien = getattr(m, objetivo)
    r = put_anterior(api, m, m.admin, quien, [m.p1.id_ubccn])
    assert r.status_code == 409, r.text
    assert m.asignadas(quien) == set()


# ---------------------------------------------------------------- CA-02
def test_ca02_panel_anterior_muestra_contexto_completo(api, mundo):
    m = mundo
    panel = api.get(f"/usuarios/{m.cf.id_usr}/permisos-ubicaciones", headers=m.h(m.admin)).json()
    assert panel["id_usr"] == m.cf.id_usr and panel["nmbr_cmplt"] == m.cf.nmbr_cmplt
    assert panel["rol_nombre"] == "Cliente Final"
    item = next(i for i in panel["items"] if i["id_ubccn"] == m.p1.id_ubccn)
    assert (item["empresa"], item["sede"], item["estado"], item["tiene_acceso"]) == (
        m.a.rzn_scl, m.s1.nmbr, "Activa", True)


def test_ca02_nombres_repetidos_se_distinguen_por_empresa_y_sede(api, mundo):
    m = mundo
    panel = api.get(f"/usuarios/{m.cf.id_usr}/permisos-ubicaciones", headers=m.h(m.admin)).json()
    norte = [(i["empresa"], i["sede"]) for i in panel["items"]
             if i["nmbr"] == "Norte QA" and i["id_ubccn"] in {m.p1.id_ubccn, m.p3.id_ubccn, m.pb.id_ubccn}]
    assert len(norte) == 3 and len(set(norte)) == 3


def test_ca02_no_se_presenta_como_asignable_lo_que_el_alcance_impediria(api, mundo):
    m = mundo
    panel = api.get(f"/usuarios/{m.cf.id_usr}/permisos-ubicaciones", headers=m.h(m.admin)).json()
    por_id = {i["id_ubccn"]: i for i in panel["items"]}
    assert por_id[m.p2.id_ubccn]["puede_asignar"] is True
    for fuera in (m.p3, m.pb):
        assert por_id[fuera.id_ubccn]["puede_asignar"] is False
        assert por_id[fuera.id_ubccn]["motivo_restriccion"]


def test_ca02_cuenta_empresarial_solo_ofrece_proyectos_de_su_empresa(api, mundo):
    m = mundo
    ids = {p["id_ubccn"] for p in api.get(f"/empresas/{m.a.id_clnt}/proyectos", headers=m.h(m.admin_a)).json()}
    assert ids == {m.p1.id_ubccn, m.p2.id_ubccn, m.p3.id_ubccn}


def test_ca02_lista_de_miembros_trae_rol_estado_y_seleccion_actual(api, mundo):
    m = mundo
    filas = api.get(f"/empresas/{m.a.id_clnt}/usuarios", headers=m.h(m.admin_a)).json()
    fila = next(f for f in filas if f["id_mmb"] == m.m_lector.id_mmb)
    assert (fila["correo"], fila["rol"], fila["estado"], fila["proyecto_ids"], fila["legado"]) == (
        m.lector.crr, "Lector", "Activo", [m.p1.id_ubccn], False)


def test_ca02_cuenta_anterior_aparece_identificada_en_empresas(api, mundo):
    m = mundo
    filas = api.get(f"/empresas/{m.a.id_clnt}/usuarios", headers=m.h(m.admin)).json()
    fila = next(f for f in filas if f["id_usr"] == m.cf.id_usr)
    assert fila["legado"] is True and fila["rol"] == "Cliente Final" and fila["id_mmb"] is None


# ---------------------------------------------------------------- CA-03
def test_ca03_anterior_guarda_exactamente_el_conjunto_y_confirma(api, mundo):
    m = mundo
    r = put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn])
    assert r.status_code == 200 and r.json()["mensaje"] == MSG_ANTERIOR
    assert m.asignadas(m.cf) == {m.p2.id_ubccn}


def test_ca03_empresa_guarda_exactamente_el_conjunto(api, mundo):
    m = mundo
    ids = [m.p2.id_ubccn, m.p3.id_ubccn]
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", ids)
    assert r.status_code == 200, r.text
    assert m.proyectos_miembro(m.m_lector) == set(ids)


def test_ca03_repetir_el_guardado_no_duplica_en_ninguna_modalidad(api, mundo):
    m = mundo
    for _ in range(2):
        assert put_anterior(api, m, m.admin, m.cf, [m.p1.id_ubccn, m.p1.id_ubccn, m.p2.id_ubccn]).status_code == 200
        assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo",
                             [m.p1.id_ubccn, m.p1.id_ubccn, m.p2.id_ubccn]).status_code == 200
    assert m.db.query(PermisoUbicacion).filter_by(id_usr=m.cf.id_usr).count() == 2
    assert m.db.query(UsuarioProyecto).filter_by(id_mmb=m.m_lector.id_mmb).count() == 2


def test_ca03_anterior_rechaza_lote_con_un_proyecto_invalido_sin_cambio_parcial(api, mundo):
    m = mundo
    for malo, codigo in ((m.p3.id_ubccn, 422), (m.pb.id_ubccn, 422), (99999999, 400)):
        r = put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn, malo])
        assert r.status_code == codigo, r.text
        assert r.json()["detail"]
        assert m.asignadas(m.cf) == {m.p1.id_ubccn}


def test_ca03_anterior_rechaza_proyecto_inactivo(api, mundo):
    m = mundo
    m.p2.estd = "Inactiva"
    m.db.flush()
    r = put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn])
    assert r.status_code == 422 and "inactivo" in r.json()["detail"].lower()


def test_ca03_empresa_rechaza_proyecto_ajeno_o_inexistente_sin_cambio_parcial(api, mundo):
    m = mundo
    for malo in (m.pb.id_ubccn, 99999999):
        r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn, malo])
        assert r.status_code == 422, r.text
        assert m.proyectos_miembro(m.m_lector) == {m.p1.id_ubccn}


def test_ca03_empresa_rechaza_proyecto_inactivo_explicando_el_motivo(api, mundo):
    """El motivo mostrado debe decir que el proyecto está inactivo."""
    m = mundo
    m.p2.estd = "Inactiva"
    m.db.flush()
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn])
    assert r.status_code == 422
    assert "inactiv" in r.json()["detail"].lower(), r.json()["detail"]


def test_ca03_conservar_marcado_un_proyecto_ya_inactivo_explica_el_motivo(api, mundo):
    """La UI deja marcado un proyecto asignado que pasó a inactivo; el rechazo debe explicarlo."""
    m = mundo
    m.db.add(UsuarioProyecto(id_mmb=m.m_lector.id_mmb, id_ubccn=m.p2.id_ubccn))
    m.p2.estd = "Inactiva"
    m.db.flush()
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo",
                      [m.p1.id_ubccn, m.p2.id_ubccn, m.p3.id_ubccn])
    assert r.status_code == 422
    assert "inactiv" in r.json()["detail"].lower(), r.json()["detail"]


def test_ca03_lector_activo_requiere_al_menos_un_proyecto(api, mundo):
    m = mundo
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [])
    assert r.status_code == 422 and m.proyectos_miembro(m.m_lector) == {m.p1.id_ubccn}


def test_ca03_pasar_a_lector_exige_seleccion_explicita(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_tec_a, "Lector", "Activo", []).status_code == 422
    assert m.db.get(UsuarioCliente, m.m_tec_a.id_mmb).rol_emp == "Tecnico"
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_tec_a, "Lector", "Activo", [m.p1.id_ubccn]).status_code == 200


@pytest.mark.parametrize("rol,estado", [("Dueño", "Activo"), ("Lector", "Suspendido")])
def test_ca03_rol_o_estado_invalido_se_rechaza(api, mundo, rol, estado):
    m = mundo
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, rol, estado, [m.p1.id_ubccn])
    assert r.status_code == 422
    assert m.db.get(UsuarioCliente, m.m_lector.id_mmb).rol_emp == "Lector"


def _fallar_commit(monkeypatch, db):
    def falla():
        db.flush()
        raise IntegrityError("simulado", {}, Exception("fallo de persistencia"))

    monkeypatch.setattr(db, "commit", falla)


def test_ca03_fallo_de_persistencia_anterior_no_deja_cambios(api, mundo, monkeypatch):
    m = mundo
    m.db.commit()
    _fallar_commit(monkeypatch, m.db)
    r = put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn])
    monkeypatch.undo()
    assert r.status_code == 409 and r.json()["detail"]
    assert m.asignadas(m.cf) == {m.p1.id_ubccn}


def test_ca03_fallo_de_persistencia_empresa_no_deja_cambios(api, mundo, monkeypatch):
    m = mundo
    m.db.commit()
    _fallar_commit(monkeypatch, m.db)
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn])
    monkeypatch.undo()
    assert r.status_code == 409 and r.json()["detail"]
    assert m.proyectos_miembro(m.m_lector) == {m.p1.id_ubccn}


def test_ca03_asignar_proyectos_a_miembro_activo_no_consume_otro_cupo(api, mundo):
    m = mundo
    antes = m.db.query(UsuarioCliente).filter_by(id_clnt=m.a.id_clnt).count()
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo",
                         [m.p1.id_ubccn, m.p2.id_ubccn]).status_code == 200
    assert m.db.query(UsuarioCliente).filter_by(id_clnt=m.a.id_clnt).count() == antes


# ---------------------------------------------------------------- CA-04 (API)
def test_ca04_abrir_y_no_guardar_conserva_lo_ultimo_guardado(api, mundo):
    m = mundo
    url = f"/usuarios/{m.cf.id_usr}/permisos-ubicaciones"
    antes = api.get(url, headers=m.h(m.admin)).json()
    despues = api.get(url, headers=m.h(m.admin)).json()
    assert antes == despues and m.asignadas(m.cf) == {m.p1.id_ubccn}


# ---------------------------------------------------------------- CA-05
def _sondas(api, m, usuario, clave):
    """Devuelve la lista de consultas que entregan un proyecto no autorizado."""
    h = m.h(usuario)
    prohibido, disp = getattr(m, clave).id_ubccn, m.disp[clave].id_dspstv
    nombre_disp, nombre_param = m.disp[clave].nmbr, m.parametros[clave].nmbr
    serie = m.db.query(MapeoColumna.id_mp_cl).join(MapeoFormato, MapeoFormato.id_mp == MapeoColumna.id_mp).filter(
        MapeoFormato.id_dspstv == disp).first()[0]
    inicio = (ahora() - dt.timedelta(days=1)).isoformat()
    fin = (ahora() + dt.timedelta(minutes=1)).isoformat()
    filtraciones = []

    def lista(nombre, ruta, params=None, clave="id_ubccn", valor=prohibido):
        r = api.get(ruta, headers=h, params=params)
        if r.status_code == 200 and any(f.get(clave) == valor for f in filas_de(r)):
            filtraciones.append(nombre)
        elif r.status_code >= 500:
            filtraciones.append(f"{nombre}: HTTP {r.status_code}")

    def directo(nombre, ruta):
        r = api.get(ruta, headers=h)
        if r.status_code == 200:
            filtraciones.append(nombre)
        elif r.status_code >= 500:
            filtraciones.append(f"{nombre}: HTTP {r.status_code}")

    lista("GET /ubicaciones", "/ubicaciones", {"por_pagina": 100})
    lista("GET /ubicaciones/mapa", "/ubicaciones/mapa")
    lista("GET /dispositivos", "/dispositivos", {"por_pagina": 100}, "id_dspstv", disp)
    lista("GET /dispositivos/mapa", "/dispositivos/mapa", None, "id_dspstv", disp)
    lista("GET /alarmas/ubicaciones", "/alarmas/ubicaciones")
    lista("GET /exportaciones/dispositivos", "/exportaciones/dispositivos", None, "id_dspstv", disp)
    lista("GET /series", "/mediciones/series", {"ubicacion_id": prohibido})
    directo("GET /ubicaciones/{id}", f"/ubicaciones/{prohibido}")
    directo("GET /ubicaciones/{id}/parametros", f"/ubicaciones/{prohibido}/parametros")
    directo("GET /dispositivos/{id}", f"/dispositivos/{disp}")
    directo("GET /dispositivos/{id}/logs", f"/dispositivos/{disp}/logs")
    r = api.get(f"/mediciones/series/{serie}", headers=h, params={"fecha_inicio": inicio, "fecha_fin": fin})
    if r.status_code == 200:
        filtraciones.append("GET /series/{id}")
    directo("GET /dispositivos/{id}/estadisticas", f"/dispositivos/{disp}/estadisticas")
    r = api.get("/mapeos", headers=h, params={"id_dspstv": disp})
    if r.status_code == 200 and filas_de(r):
        filtraciones.append("GET /mapeos")
    for nombre, filtro in (("por ubicacion", {"ubicacion_ids": [prohibido]}), ("sin filtro", {}),
                           ("por dispositivo", {"dispositivo_ids": [disp]})):
        r = api.get("/mediciones", headers=h, params={"fecha_inicio": inicio, "fecha_fin": fin, **filtro})
        if r.status_code == 200 and nombre_disp in r.text:
            filtraciones.append(f"GET /mediciones {nombre}")
    r = api.get("/mediciones/parametros", headers=h)
    if r.status_code == 200 and nombre_param in r.text:
        filtraciones.append("GET /mediciones/parametros")
    r = api.get("/mapa-cliente", headers=h)
    if r.status_code == 200 and f'"id_ubccn":{prohibido},' in r.text.replace(" ", ""):
        filtraciones.append("GET /mapa-cliente")
    r = api.post("/exportaciones", headers=h, json={
        "formato": "csv", "fecha_inicio": inicio, "fecha_fin": fin, "ubicacion_ids": [prohibido]})
    if r.status_code in (200, 202):
        filtraciones.append("POST /exportaciones")
    r = api.post("/exportaciones", headers=h, json={
        "formato": "csv", "fecha_inicio": inicio, "fecha_fin": fin, "dispositivo_ids": [disp]})
    if r.status_code in (200, 202):
        filtraciones.append("POST /exportaciones por dispositivo")
    return filtraciones


@pytest.fixture()
def bucket(monkeypatch):
    monkeypatch.setenv("EXPORT_S3_BUCKET", "exportaciones-privadas")
    monkeypatch.setattr(router_exportaciones, "encolar_exportacion", MagicMock())
    monkeypatch.setattr(router_exportaciones, "AlmacenExportaciones", AlmacenFalso)
    AlmacenFalso.objetos, AlmacenFalso.eliminados, AlmacenFalso.firmas = {}, [], []


@pytest.mark.parametrize("cuenta", ["cf", "lector"])
@pytest.mark.parametrize("clave", ["p2", "p3", "pb"], ids=["misma_sede", "otra_sede", "otra_empresa"])
def test_ca05_proyecto_no_autorizado_no_se_obtiene_por_ninguna_consulta(api, mundo, bucket, cuenta, clave):
    m = mundo
    assert _sondas(api, m, getattr(m, cuenta), clave) == []


@pytest.mark.parametrize("cuenta", ["cf", "lector"])
def test_ca05_control_positivo_las_sondas_si_detectan_el_proyecto_asignado(api, mundo, bucket, cuenta):
    """Control: con el proyecto autorizado las mismas sondas deben encontrar datos."""
    m = mundo
    encontradas = _sondas(api, m, getattr(m, cuenta), "p1")
    for esperada in ("GET /ubicaciones", "GET /dispositivos", "GET /ubicaciones/{id}",
                     "GET /dispositivos/{id}", "GET /mediciones por ubicacion", "GET /mediciones sin filtro",
                     "GET /mediciones/parametros", "GET /series/{id}", "POST /exportaciones"):
        assert esperada in encontradas, encontradas


def test_ca05_manipular_cabeceras_no_cruza_a_otra_empresa_ni_proyecto(api, mundo):
    m = mundo
    h = m.h(m.lector, **{"X-Cliente-Id": str(m.b.id_clnt)})
    assert api.get("/ubicaciones", headers=h).status_code == 403
    h = m.h(m.lector, **{"X-Proyecto-Id": str(m.p2.id_ubccn)})
    assert api.get("/ubicaciones", headers=h).status_code == 403
    h = m.h(m.cf, **{"X-Cliente-Id": str(m.b.id_clnt)})
    assert api.get("/ubicaciones", headers=h).status_code == 403


def test_ca05_recursos_de_proyecto_no_autorizado_devuelven_403(api, mundo):
    m = mundo
    r = api.get(f"/empresas/{m.a.id_clnt}/proyectos/{m.p2.id_ubccn}/recursos", headers=m.h(m.lector))
    assert r.status_code == 403
    r = api.get(f"/empresas/{m.b.id_clnt}/proyectos/{m.pb.id_ubccn}/recursos", headers=m.h(m.lector))
    assert r.status_code == 403


def test_ca05_lector_no_lista_proyectos_no_asignados_de_su_empresa(api, mundo):
    m = mundo
    ids = {p["id_ubccn"] for p in api.get(f"/empresas/{m.a.id_clnt}/proyectos", headers=m.h(m.lector)).json()}
    assert ids == {m.p1.id_ubccn}


def test_ca05_admin_y_tecnico_de_empresa_acceden_a_todo_incluidos_los_nuevos(api, mundo):
    m = mundo
    nuevo = crear_ubicacion(m.db, m.s2, "Proyecto nuevo QA")
    for quien in (m.admin_a, m.tec_a):
        r = api.get(f"/empresas/{m.a.id_clnt}/proyectos", headers=m.h(quien)).json()
        assert {p["id_ubccn"] for p in r} == {m.p1.id_ubccn, m.p2.id_ubccn, m.p3.id_ubccn, nuevo.id_ubccn}
        assert api.get(f"/ubicaciones/{m.pb.id_ubccn}", headers=m.h(quien)).status_code in (403, 404)


def test_ca05_alcance_global_respeta_el_entorno_seleccionado(api, mundo):
    m = mundo
    h = m.h(m.admin, **{"X-Cliente-Id": str(m.b.id_clnt)})
    ids = {f["id_ubccn"] for f in filas_de(api.get("/ubicaciones", headers=h, params={"por_pagina": 100}))}
    assert m.pb.id_ubccn in ids and m.p1.id_ubccn not in ids


def test_ca05_parametros_visibles_salen_de_dispositivos_autorizados(api, mundo):
    m = mundo
    otro = crear_parametro(m.db, f"Solo P2 QA {m.a.id_clnt}")
    mapear_parametro(m.db, m.disp["p2"], otro, indice=2)
    r = api.get("/mediciones/parametros", headers=m.h(m.lector), params={"ubicacion_ids": [m.p1.id_ubccn]})
    assert r.status_code == 200 and otro.nmbr not in r.text and m.parametros["p1"].nmbr in r.text
    assert otro.nmbr not in api.get("/mediciones/parametros", headers=m.h(m.lector)).text


@pytest.fixture()
def tableros_contratados(monkeypatch):
    """La compra del módulo no es de esta HU: se levanta esa puerta para llegar al alcance."""
    monkeypatch.setattr(router_panel, "ultimo_contrato", lambda *a, **k: None)


def _panel_compartido(m):
    panel = Panel(id_usr=m.admin_a.id_usr, id_sd=m.s1.id_sd, nmbr="Panel QA compartido", vsbldd="Empresa")
    m.db.add(panel)
    m.db.flush()
    for proyecto in (m.p1, m.p2):
        m.db.add(PanelUbicacion(id_pnl=panel.id_pnl, id_ubccn=proyecto.id_ubccn))
    m.db.flush()
    return panel


def test_ca05_compartir_panel_no_concede_sus_proyectos(api, mundo, tableros_contratados):
    m = mundo
    panel = _panel_compartido(m)
    h = m.h(m.lector)
    assert panel.id_pnl in {f["id_pnl"] for f in filas_de(api.get("/paneles", headers=h))}
    contenido = api.get(f"/paneles/{panel.id_pnl}/contenido", headers=h)
    assert contenido.status_code == 200, contenido.text
    assert "Norte QA" in contenido.text and "Relaves QA" not in contenido.text
    assert m.disp["p2"].nmbr not in contenido.text
    detalle = api.get(f"/paneles/{panel.id_pnl}", headers=h)
    assert detalle.status_code == 200 and "Relaves QA" not in detalle.text


def test_ca05_panel_propio_deja_de_mostrar_el_proyecto_revocado(api, mundo, tableros_contratados):
    m = mundo
    panel = Panel(id_usr=m.cf.id_usr, id_sd=m.s1.id_sd, nmbr="Panel propio QA")
    m.db.add(panel)
    m.db.flush()
    m.db.add(PanelUbicacion(id_pnl=panel.id_pnl, id_ubccn=m.p1.id_ubccn))
    m.db.flush()
    h = m.h(m.cf)
    assert "Norte QA" in api.get(f"/paneles/{panel.id_pnl}/contenido", headers=h).text
    assert put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn]).status_code == 200
    r = api.get(f"/paneles/{panel.id_pnl}/contenido", headers=h)
    assert r.status_code in (200, 403, 404) and "Norte QA" not in r.text


# ---------------------------------------------------------------- CA-06
def test_ca06_revocacion_anterior_se_aplica_en_la_siguiente_peticion_con_el_mismo_token(api, mundo):
    m = mundo
    h = m.h(m.cf)
    assert api.get(f"/dispositivos/{m.disp['p1'].id_dspstv}", headers=h).status_code == 200
    assert put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn]).status_code == 200
    assert api.get(f"/dispositivos/{m.disp['p1'].id_dspstv}", headers=h).status_code in (403, 404)
    assert api.get(f"/dispositivos/{m.disp['p2'].id_dspstv}", headers=h).status_code == 200


def test_ca06_revocacion_empresarial_se_aplica_con_el_mismo_token(api, mundo):
    m = mundo
    h = m.h(m.lector)
    assert api.get(f"/ubicaciones/{m.p1.id_ubccn}", headers=h).status_code == 200
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn]).status_code == 200
    assert api.get(f"/ubicaciones/{m.p1.id_ubccn}", headers=h).status_code == 403
    assert api.get(f"/ubicaciones/{m.p2.id_ubccn}", headers=h).status_code == 200


def test_ca06_cambio_de_rol_empresarial_se_aplica_con_el_mismo_token(api, mundo):
    m = mundo
    h = m.h(m.tec_a)
    assert api.get(f"/ubicaciones/{m.p2.id_ubccn}", headers=h).status_code == 200
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_tec_a, "Lector", "Activo", [m.p1.id_ubccn]).status_code == 200
    assert api.get(f"/ubicaciones/{m.p2.id_ubccn}", headers=h).status_code == 403
    assert api.get(f"/ubicaciones/{m.p1.id_ubccn}", headers=h).status_code == 200


def test_ca06_consulta_cacheada_no_sobrevive_a_la_revocacion(api, mundo):
    m = mundo
    h = m.h(m.cf)
    params = {"ubicacion_ids": [m.p1.id_ubccn],
              "fecha_inicio": (ahora() - dt.timedelta(days=1)).isoformat(),
              "fecha_fin": (ahora() + dt.timedelta(minutes=1)).isoformat()}
    assert api.get("/mediciones", headers=h, params=params).status_code == 200
    assert put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn]).status_code == 200
    segunda = api.get("/mediciones", headers=h, params=params)
    assert segunda.status_code in (200, 403)
    assert m.disp["p1"].nmbr not in segunda.text


@pytest.mark.parametrize("cuenta", ["cf", "lector"])
def test_ca06_version_de_acceso_cambia_al_asignar_o_revocar(api, mundo, cuenta):
    m = mundo
    h = m.h(getattr(m, cuenta))
    antes = api.get("/auth/acceso", headers=h).json()["version"]
    if cuenta == "cf":
        assert put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn]).status_code == 200
    else:
        assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn]).status_code == 200
    assert api.get("/auth/acceso", headers=h).json()["version"] != antes


def _exportacion_lista(m, usuario, entorno=None):
    filtros = {"ubicacion_ids": [m.p1.id_ubccn], "dispositivo_ids": [], "parametro_ids": [],
               "scope": usuario.scp, "rol": usuario.rol.nmbr, "sede_id": None,
               "cliente_id": None, "proyecto_id": None, **(entorno or {})}
    exportacion = Exportacion(
        id_usr=usuario.id_usr, frmt="csv", fltrs_aplcds=filtros, estd="Lista",
        objeto_bucket="exportaciones-privadas", objeto_clave="qa/hu21.csv", objeto_version="1",
        fch_exprcn=ahora() + dt.timedelta(hours=1),
    )
    m.db.add(exportacion)
    m.db.flush()
    return exportacion


def test_ca06_descarga_se_rechaza_tras_revocar_y_la_firma_dura_hasta_60s(api, mundo, bucket):
    m = mundo
    exportacion = _exportacion_lista(m, m.cf, {"sede_id": m.s1.id_sd})
    h = m.h(m.cf)
    r = api.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga", headers=h)
    assert r.status_code == 200, r.text
    assert AlmacenFalso.firmas[-1][1] <= 60
    assert put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn]).status_code == 200
    firmas = len(AlmacenFalso.firmas)
    r = api.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga", headers=h)
    assert r.status_code == 403, r.text
    assert len(AlmacenFalso.firmas) == firmas


def test_ca06_descarga_empresarial_se_rechaza_tras_revocar(api, mundo, bucket):
    m = mundo
    exportacion = _exportacion_lista(m, m.lector, {"cliente_id": m.a.id_clnt, "rol_empresa": "Lector"})
    h = m.h(m.lector, **{"X-Cliente-Id": str(m.a.id_clnt)})
    assert api.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga", headers=h).status_code == 200
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn]).status_code == 200
    assert api.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga", headers=h).status_code == 403


def test_ca06_nueva_exportacion_de_lo_revocado_se_rechaza(api, mundo, bucket):
    m = mundo
    assert put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn]).status_code == 200
    r = api.post("/exportaciones", headers=m.h(m.cf), json={
        "formato": "csv", "fecha_inicio": (ahora() - dt.timedelta(days=1)).isoformat(),
        "fecha_fin": ahora().isoformat(), "ubicacion_ids": [m.p1.id_ubccn],
    })
    assert r.status_code in (400, 403, 422), r.text


# ---------------------------------------------------------------- CA-07
def test_ca07_cuenta_anterior_con_seleccion_vacia_queda_sin_telemetria(api, mundo):
    m = mundo
    r = put_anterior(api, m, m.admin, m.cf, [])
    assert r.status_code == 200 and r.json()["mensaje"] == MSG_ANTERIOR
    h = m.h(m.cf)
    assert filas_de(api.get("/ubicaciones", headers=h)) == []
    assert api.get(f"/dispositivos/{m.disp['p1'].id_dspstv}", headers=h).status_code in (403, 404)
    assert api.get("/auth/acceso", headers=h).json()["proyecto_ids"] == []


def test_ca07_desactivar_lector_bloquea_su_sesion_abierta(api, mundo):
    m = mundo
    h = m.h(m.lector)
    assert api.get(f"/ubicaciones/{m.p1.id_ubccn}", headers=h).status_code == 200
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Inactivo", [m.p1.id_ubccn]).status_code == 200
    assert api.get(f"/ubicaciones/{m.p1.id_ubccn}", headers=h).status_code == 403


def test_ca07_desactivar_no_afecta_membresias_en_otras_empresas(api, mundo):
    m = mundo
    _, en_b = m.miembro(m.b, "Lector", [m.pb], usuario=m.lector)
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Inactivo", [m.p1.id_ubccn]).status_code == 200
    h = m.h(m.lector)
    assert api.get(f"/ubicaciones/{m.p1.id_ubccn}", headers=h).status_code == 403
    assert api.get(f"/ubicaciones/{m.pb.id_ubccn}", headers=h).status_code == 200
    assert m.db.get(UsuarioCliente, en_b.id_mmb).estd == "Activo"


def test_ca07_modificar_una_membresia_no_cambia_las_demas(api, mundo):
    m = mundo
    _, en_b = m.miembro(m.b, "Tecnico", usuario=m.lector)
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn]).status_code == 200
    assert m.db.get(UsuarioCliente, en_b.id_mmb).rol_emp == "Tecnico"


@pytest.mark.parametrize("rol,estado", [("Administrador", "Inactivo"), ("Tecnico", "Activo"), ("Lector", "Activo")])
def test_ca07_ultimo_administrador_no_se_desactiva_ni_cambia_de_rol(api, mundo, rol, estado):
    m = mundo
    r = patch_miembro(api, m, m.admin, m.a, m.m_admin_a, rol, estado, [m.p1.id_ubccn])
    assert r.status_code == 409, r.text
    miembro = m.db.get(UsuarioCliente, m.m_admin_a.id_mmb)
    assert (miembro.rol_emp, miembro.estd) == ("Administrador", "Activo")


def test_ca07_con_otro_administrador_activo_si_se_puede(api, mundo):
    m = mundo
    m.miembro(m.a, "Administrador")
    assert patch_miembro(api, m, m.admin, m.a, m.m_admin_a, "Administrador", "Inactivo", []).status_code == 200


def test_ca07_otro_administrador_inactivo_no_cuenta_como_continuidad(api, mundo):
    m = mundo
    _, otro = m.miembro(m.a, "Administrador")
    otro.estd = "Inactivo"
    m.db.flush()
    assert patch_miembro(api, m, m.admin, m.a, m.m_admin_a, "Administrador", "Inactivo", []).status_code == 409


def test_ca07_desactivar_no_acepta_cambiar_el_rol_a_la_vez(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Tecnico", "Inactivo", []).status_code == 422


def test_ca07_desactivar_lector_funciona_aunque_su_proyecto_este_inactivo(api, mundo):
    m = mundo
    m.p1.estd = "Inactiva"
    m.db.flush()
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Inactivo", [m.p1.id_ubccn]).status_code == 200


def test_ca07_reactivar_lector_con_proyecto_inactivo_explica_el_motivo(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Inactivo", [m.p1.id_ubccn]).status_code == 200
    m.p1.estd = "Inactiva"
    m.db.flush()
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p1.id_ubccn])
    assert r.status_code == 422
    assert "inactiv" in r.json()["detail"].lower(), r.json()["detail"]


def test_ca07_reactivar_lector_conserva_sus_proyectos(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Inactivo", [m.p1.id_ubccn]).status_code == 200
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p1.id_ubccn])
    assert r.status_code == 200, r.text
    assert m.proyectos_miembro(m.m_lector) == {m.p1.id_ubccn}


# ---------------------------------------------------------------- CA-08
def _registros(m, actor, entidad=None):
    q = m.db.query(LogAuditoria).filter(LogAuditoria.id_usr == actor.id_usr)
    if entidad:
        q = q.filter(LogAuditoria.entdd.like(f"{entidad}%"))
    return q.order_by(LogAuditoria.id_evnt.desc()).all()


def test_ca08_cambio_empresarial_registra_quien_cuando_y_antes_despues(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Tecnico", "Activo", []).status_code == 200
    fila = _registros(m, m.admin_a, "MiembroEmpresa")[0]
    assert fila.fch_evnt is not None
    assert fila.vlrs_antrrs["rol"] == "Lector" and fila.vlrs_nvs["rol"] == "Tecnico"
    assert fila.vlrs_antrrs["estado"] == "Activo" and fila.vlrs_nvs["estado"] == "Activo"
    assert fila.vlrs_antrrs["proyecto_ids"] == [m.p1.id_ubccn] and fila.vlrs_nvs["proyecto_ids"] == []
    assert fila.vlrs_nvs["cliente_id"] == m.a.id_clnt and fila.vlrs_nvs["usuario_id"] == m.lector.id_usr


def test_ca08_cambio_anterior_registra_usuario_empresa_y_proyectos(api, mundo):
    m = mundo
    assert put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn]).status_code == 200
    fila = _registros(m, m.admin, "permisos_ubicacion")[0]
    assert fila.entdd == f"permisos_ubicacion:{m.cf.id_usr}" and fila.fch_evnt is not None
    assert fila.vlrs_antrrs["ubicacion_ids"] == [m.p1.id_ubccn]
    assert fila.vlrs_nvs["ubicacion_ids"] == [m.p2.id_ubccn]
    assert fila.vlrs_nvs["empresa_ids"] == [m.a.id_clnt]
    assert fila.vlrs_nvs["rol"] == "Cliente Final"


def test_ca08_retirar_todo_el_acceso_anterior_queda_auditado(api, mundo):
    m = mundo
    assert put_anterior(api, m, m.admin, m.cf, []).status_code == 200
    fila = _registros(m, m.admin, "permisos_ubicacion")[0]
    assert fila.vlrs_antrrs["ubicacion_ids"] == [m.p1.id_ubccn] and fila.vlrs_nvs["ubicacion_ids"] == []
    assert fila.vlrs_antrrs["empresa_ids"] == [m.a.id_clnt]


def test_ca08_desactivacion_queda_auditada_con_su_estado(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Inactivo", [m.p1.id_ubccn]).status_code == 200
    fila = _registros(m, m.admin_a, "MiembroEmpresa")[0]
    assert fila.vlrs_antrrs["estado"] == "Activo" and fila.vlrs_nvs["estado"] == "Inactivo"


def test_ca08_registro_no_contiene_credenciales_ni_tokens(api, mundo):
    m = mundo
    token = m.token(m.admin_a)
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Tecnico", "Activo", []).status_code == 200
    assert put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn]).status_code == 200
    filas = _registros(m, m.admin_a) + _registros(m, m.admin)
    assert filas
    texto = " ".join(str(f.vlrs_antrrs) + str(f.vlrs_nvs) for f in filas).lower()
    for prohibido in ("cntrsn", "contrasena", "password", "hash", "token", token.lower()):
        assert prohibido not in texto


def test_ca08_intento_rechazado_no_se_registra_como_cambio(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", []).status_code == 422
    assert put_anterior(api, m, m.admin, m.cf, [m.pb.id_ubccn]).status_code == 422
    assert _registros(m, m.admin_a, "MiembroEmpresa") == []
    assert _registros(m, m.admin, "permisos_ubicacion") == []


def test_ca08_fallo_de_persistencia_no_deja_auditoria_de_exito(api, mundo, monkeypatch):
    m = mundo
    m.db.commit()
    _fallar_commit(monkeypatch, m.db)
    put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn])
    patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn])
    monkeypatch.undo()
    assert _registros(m, m.admin, "permisos_ubicacion") == []
    assert _registros(m, m.admin_a, "MiembroEmpresa") == []


def test_ca08_el_cambio_empresarial_se_ve_en_la_consulta_de_auditoria(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Tecnico", "Activo", []).status_code == 200
    r = api.get("/auditoria", headers=m.h(m.admin), params={"usuario_id": m.admin_a.id_usr})
    assert r.status_code == 200, r.text
    assert "MiembroEmpresa" in r.text
