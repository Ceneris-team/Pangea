"""QA PP-27 (PP-439): reprocesar archivos fallidos.

Casos que complementan la suite de desarrollo (test_reprocesos.py,
test_reprocesos_concurrentes.py, test_reprocesos_ui.py). Reutiliza su fixture
`entorno` (Técnico CENERIS global dentro de empresa y proyecto, archivo Fallido
con original conservado). Se copia a backend/tests/routers/ del worktree de dev 78edb10.
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import datetime as dt

import pytest

from app.models import ArchivoIngesta, IntentoProcesamiento, Suscripcion, Telemetria
from app.services.ingesta.originales import conservar_original
from app.services.limites_plan import fecha_comercial
from app.tasks import reprocesos
from tests.routers.test_alarmas import dar_suscripcion_vigente
from tests.routers.test_mediciones import crear_conexion, crear_dispositivo, crear_ubicacion
from tests.routers.test_reprocesos import entorno, pedir  # noqa: F401  (fixture reutilizada)

COLA = "/ingesta/cola"


def fallido(e, nombre, sede=None, conexion=None, equipo=None, estado="Fallido", motivo="Error X"):
    a = ArchivoIngesta(
        id_cnxn=(conexion or e["conexion"]).id_cnxn,
        id_dspstv=(equipo or e["equipo"]).id_dspstv,
        nmbr_archv=nombre,
        estd=estado,
        mnsj_errr=motivo,
    )
    e["db"].add(a)
    e["db"].flush()
    return a


def otra_empresa(e, fabrica, vigente=True):
    db = e["db"]
    sede = fabrica.sede(fabrica.cliente())
    dar_suscripcion_vigente(db, sede)
    if not vigente:
        hoy = fecha_comercial()
        sus = db.query(Suscripcion).filter_by(id_clnt=sede.id_clnt).one()
        sus.fch_inc = hoy - dt.timedelta(days=90)
        sus.fch_vncmnt = hoy - dt.timedelta(days=60)
    proyecto = crear_ubicacion(db, sede, "Proyecto ajeno")
    conexion = crear_conexion(db, sede, "FTP ajeno")
    equipo = crear_dispositivo(db, proyecto, conexion, "Equipo ajeno")
    db.flush()
    return sede, conexion, equipo


def intentos(e, archivo):
    return e["db"].query(IntentoProcesamiento).filter_by(id_archv=archivo.id_archv).count()


# CP-540 · CA-01: filtro «Fallido» muestra nombre, datalogger, fecha, motivo; 10 por página; solo el contexto
def test_cp540_listado_fallidos_del_contexto(entorno, fabrica):
    e = entorno
    for i in range(11):
        fallido(e, f"F_{i:02}.dat", motivo=f"Columna {i} sin mapeo")
    fallido(e, "OK.dat", estado="Exitoso", motivo=None)
    _, cnxn, eq = otra_empresa(e, fabrica)
    ajeno = fallido(e, "AJENO.dat", conexion=cnxn, equipo=eq)
    e["db"].commit()
    r = e["client"].get(COLA, params={"estado": "Fallido"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 12 and d["por_pagina"] == 10 and len(d["items"]) == 10
    assert d["fallidos"] == 12 and d["puede_reprocesar"] is True
    item = d["items"][0]
    assert {"nmbr_archv", "datalogger_nombre", "fch_dtccn", "estado", "mnsj_errr"} <= item.keys()
    assert all(i["estado"] == "Fallido" and i["mnsj_errr"] for i in d["items"])
    assert all(i["datalogger_nombre"] == e["equipo"].nmbr for i in d["items"])
    p2 = e["client"].get(COLA, params={"estado": "Fallido", "pagina": 2}).json()
    nombres = [i["nmbr_archv"] for i in d["items"] + p2["items"]]
    assert len(nombres) == 12 == len(set(nombres)) and "AJENO.dat" not in nombres
    assert e["client"].get(f"{COLA}/{ajeno.id_archv}/intentos").status_code == 403
    assert e["client"].get(f"{COLA}/{e['archivo'].id_archv}/intentos").status_code == 200


# CP-541 · CA-02: Reintentar → «En espera», solicitud registrada, motivo anterior visible
def test_cp541_reintentar_pasa_a_en_espera(entorno):
    e = entorno
    r = e["client"].post(f"{COLA}/{e['archivo'].id_archv}/reintentar")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "En espera" and d["mnsj_errr"] == "Mapeo pendiente"
    assert d["fch_prcsd"] is None and d["rgstrs_prcsds"] is None
    intento = e["db"].query(IntentoProcesamiento).one()
    assert intento.rsltd == "Pendiente" and intento.id_usr == e["usuario"].id_usr
    listado = e["client"].get(COLA, params={"estado": "En espera"}).json()
    assert [i["id_archv"] for i in listado["items"]] == [e["archivo"].id_archv]
    m = e["client"].get("/ingesta/metricas").json()
    assert m["pendientes"] == 1 and m["fallidos"] == 0


# CP-542 · CA-02: solo «Fallido» es elegible; sin solicitudes duplicadas
@pytest.mark.parametrize("estado", ["Pendiente", "Procesando", "Exitoso"])
def test_cp542_no_elegible_devuelve_409(entorno, estado):
    e = entorno
    e["archivo"].estd = estado
    e["db"].commit()
    r = e["client"].post(f"{COLA}/{e['archivo'].id_archv}/reintentar")
    assert r.status_code == 409 and "Fallido" in r.json()["detail"]
    assert intentos(e, e["archivo"]) == 0 and e["archivo"].estd == estado


def test_cp542_individual_tras_masivo_no_duplica(entorno):
    e = entorno
    assert e["client"].post(f"{COLA}/reintentar-fallidos").json() == {"reencolados": 1}
    assert e["client"].post(f"{COLA}/{e['archivo'].id_archv}/reintentar").status_code == 409
    assert e["client"].post(f"{COLA}/reintentar-fallidos").json() == {"reencolados": 0}
    assert intentos(e, e["archivo"]) == 1


def test_cp542_archivo_inexistente_404(entorno):
    assert entorno["client"].post(f"{COLA}/999999999/reintentar").status_code == 404


# CP-544 · CA-03: el masivo respeta el filtro de estado y valida la entrada
@pytest.mark.parametrize("estado", ["En espera", "Procesando", "Procesado"])
def test_cp544_masivo_con_otro_estado_no_modifica(entorno, estado):
    e = entorno
    r = e["client"].post(f"{COLA}/reintentar-fallidos", params={"estado": estado})
    assert r.json() == {"reencolados": 0}
    assert e["archivo"].estd == "Fallido" and intentos(e, e["archivo"]) == 0


def test_cp544_masivo_estado_invalido_422(entorno):
    e = entorno
    r = e["client"].post(f"{COLA}/reintentar-fallidos", params={"estado": "Exitoso"})
    assert r.status_code == 422
    assert e["archivo"].estd == "Fallido"


def test_cp544_masivo_por_datalogger(entorno):
    e = entorno
    cnxn2 = crear_conexion(e["db"], e["sede"], "Segundo FTP")
    eq2 = crear_dispositivo(e["db"], e["proyecto"], cnxn2, "Segundo equipo")
    otro = fallido(e, "D2.dat", conexion=cnxn2, equipo=eq2)
    e["db"].commit()
    r = e["client"].post(f"{COLA}/reintentar-fallidos", params={"id_cnxn": cnxn2.id_cnxn})
    assert r.json() == {"reencolados": 1}
    assert otro.estd == "Pendiente" and e["archivo"].estd == "Fallido"


# CP-544 · CA-03: «registra los archivos elegibles» aunque otra empresa del alcance esté en modo consulta
# OBS-73: solo por API (la UI exige elegir empresa); hoy todo el lote responde 409.
@pytest.mark.xfail(strict=True, reason="OBS-73: el masivo global se aborta por una empresa en modo consulta")
def test_cp544_masivo_global_no_aborta_por_empresa_en_modo_consulta(entorno, fabrica):
    e = entorno
    _, cnxn, eq = otra_empresa(e, fabrica, vigente=False)
    ajeno = fallido(e, "SUSPENDIDA.dat", conexion=cnxn, equipo=eq)
    e["db"].commit()
    e["identidad"].update(cliente_id=None, proyecto_id=None)  # Técnico global sin empresa elegida
    listado = e["client"].get(COLA, params={"estado": "Fallido"}).json()
    assert listado["fallidos"] >= 2 and listado["puede_reprocesar"] is True
    r = e["client"].post(f"{COLA}/reintentar-fallidos", params={"estado": "Fallido"})
    # Esperado: se registran los elegibles (empresa con operación) y se informa el resto.
    assert r.status_code == 200, r.text
    assert e["archivo"].estd == "Pendiente" and ajeno.estd == "Fallido"


# CP-545 / CP-553 · CA-04: un archivo con el mismo nombre no sustituye al original
def test_cp553_mismo_nombre_no_es_la_misma_version(entorno):
    e = entorno
    gemelo = fallido(e, e["archivo"].nmbr_archv)
    conservar_original(gemelo, f"Fecha,Nivel\n{e['fecha']:%Y-%m-%d %H:%M:%S},77\n".encode())
    e["db"].commit()
    assert gemelo.sha256 != e["archivo"].sha256
    assert reprocesos.procesar_reproceso(e["archivo"].id_archv, pedir(e).id_intnt)["estado"] == (
        "Exitoso"
    )
    lecturas = e["db"].query(Telemetria).filter_by(id_archv=e["archivo"].id_archv).all()
    assert [float(t.vlr) for t in lecturas] == [12.5]
    assert gemelo.estd == "Fallido"


# CP-548 · CA-06: Procesado con fecha y resumen; Fallido con la nueva causa; métricas
def test_cp548_resultado_final_y_metricas(entorno):
    e = entorno
    reprocesos.procesar_reproceso(e["archivo"].id_archv, pedir(e).id_intnt)
    d = e["client"].get(f"{COLA}/{e['archivo'].id_archv}").json()
    assert d["estado"] == "Procesado" and d["fch_prcsd"] and d["rgstrs_prcsds"] == 1
    assert d["mnsj_errr"] is None
    m = e["client"].get("/ingesta/metricas").json()
    assert m["exitosos"] == 1 and m["fallidos"] == 0 and m["pendientes"] == 0


def test_cp548_vuelve_a_fallar_con_nueva_causa(entorno):
    e = entorno
    e["formato"].estd = "Inactivo"
    e["db"].commit()
    reprocesos.procesar_reproceso(e["archivo"].id_archv, pedir(e).id_intnt)
    d = e["client"].get(f"{COLA}/{e['archivo'].id_archv}").json()
    assert d["estado"] == "Fallido" and d["mnsj_errr"] and d["mnsj_errr"] != "Mapeo pendiente"
    assert d["puede_reprocesar"] is True


# CP-549 · CA-07: historial con solicitante, tipo, fechas, resultado y errores; conserva anteriores
def test_cp549_historial_conserva_intentos(entorno):
    e = entorno
    db = e["db"]
    db.add(
        IntentoProcesamiento(
            id_archv=e["archivo"].id_archv,
            rsltd="Fallido",
            mnsj_errr="Mapeo pendiente",
            fch_intnt=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2),
        )
    )
    e["formato"].estd = "Inactivo"
    db.commit()
    reprocesos.procesar_reproceso(e["archivo"].id_archv, pedir(e).id_intnt)
    e["formato"].estd = "Activo"
    db.commit()
    reprocesos.procesar_reproceso(e["archivo"].id_archv, pedir(e).id_intnt)
    h = e["client"].get(f"{COLA}/{e['archivo'].id_archv}/intentos").json()
    assert [i["rsltd"] for i in h] == ["Exitoso", "Fallido", "Fallido"]
    assert h[2]["usuario_nombre"] is None and h[2]["mnsj_errr"] == "Mapeo pendiente"
    for manual in h[:2]:
        assert manual["usuario_nombre"] == e["usuario"].nmbr_cmplt and manual["reintentos"] == 0
        assert manual["fch_intnt"] <= manual["fch_inicio"] <= manual["fch_fin"]
    assert h[1]["mnsj_errr"] and h[0]["registros_guardados"] == 1


# CP-551 · Detalles: reintentos automáticos solo ante transitorios, con espera creciente
def test_cp551_backoff_transitorio(entorno, monkeypatch):
    e = entorno

    def caido(*args):
        raise TimeoutError("Almacén inaccesible")

    monkeypatch.setattr(reprocesos, "leer_original", caido)
    intento = pedir(e)
    esperas = []
    for _ in range(3):
        reprocesos.procesar_reproceso(e["archivo"].id_archv, intento.id_intnt)
        siguiente = e["db"].query(IntentoProcesamiento).filter_by(rsltd="Pendiente").one()
        esperas.append(round((siguiente.proximo_envio - intento.fch_fin).total_seconds()))
        assert siguiente.id_intento_anterior == intento.id_intnt
        intento = siguiente
    assert esperas == [2, 4, 8]


def test_cp551_error_de_contenido_sin_reintento_automatico(entorno):
    e = entorno
    e["archivo"].contenido_original = b"alterado"
    e["db"].commit()
    reprocesos.procesar_reproceso(e["archivo"].id_archv, pedir(e).id_intnt)
    assert reprocesos.despachar_pendientes()["publicados"] == 0
    assert intentos(e, e["archivo"]) == 1 and e["archivo"].estd == "Fallido"
    assert "huella" in e["archivo"].mnsj_errr


# CP-552 · PP-237: rol de empresa Técnico ve la cola pero no puede reprocesar
def test_cp552_tecnico_de_empresa_sin_accion(entorno):
    e = entorno
    e["identidad"].update(
        rol="Usuario Empresa", scope="por_cliente", rol_empresa="Tecnico", _entorno_resuelto=True
    )
    d = e["client"].get(COLA).json()
    assert d["puede_reprocesar"] is False
    assert e["client"].get(f"{COLA}/{e['archivo'].id_archv}").json()["puede_reprocesar"] is False
    assert e["client"].post(f"{COLA}/{e['archivo'].id_archv}/reintentar").status_code == 403
    assert e["client"].post(f"{COLA}/reintentar-fallidos").status_code == 403
    assert intentos(e, e["archivo"]) == 0
