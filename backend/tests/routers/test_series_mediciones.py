import datetime as dt

from app.models import ArchivoIngesta, MapeoColumna, MapeoFormato, Telemetria
from tests.routers.test_mediciones import (  # noqa: F401
    client as client_fixture,
)
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_medicion,
    mapear_parametro,
)
from tests.routers.test_mediciones import (
    escenario_basico as escenario_fixture,
)

client = client_fixture
escenario_basico = escenario_fixture


def consulta(client, id_serie, inicio, fin, **params):
    return client.get(
        f"/mediciones/series/{id_serie}",
        params={
            "fecha_inicio": inicio.isoformat(),
            "fecha_fin": fin.isoformat(),
            **params,
        },
    )


def test_kpi_por_datalogger_referencia_y_permisos(client, db_session, escenario_basico):
    e = escenario_basico
    columna = db_session.query(MapeoColumna).filter_by(id_prmtr=e["parametro"].id_prmtr).one()
    columna.visualizacion = {"significado": "contador", "vista": "kpi", "confirmada": True}
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    for minutos, valor in [(-1, 100), (1, 101), (2, 105)]:
        crear_medicion(
            db_session,
            e["dispositivo"],
            e["parametro"],
            e["sede"],
            valor=valor,
            fecha=t + dt.timedelta(minutes=minutos),
        )
    otro = crear_dispositivo(
        db_session,
        e["ubicacion"],
        crear_conexion(db_session, e["sede"], "Segundo"),
        nombre="Segundo",
    )
    mapear_parametro(db_session, otro, e["parametro"])
    crear_medicion(
        db_session, otro, e["parametro"], e["sede"], valor=9000, fecha=t + dt.timedelta(minutes=1)
    )
    respuesta = consulta(client, columna.id_mp_cl, t, t + dt.timedelta(minutes=10))
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["resumen"]["valor"] == 5
    assert {i["id_dspstv"] for i in respuesta.json()["items"]} == {e["dispositivo"].id_dspstv}
    catalogo = client.get("/mediciones/series", params={"ubicacion_id": e["ubicacion"].id_ubccn})
    assert len(catalogo.json()["items"]) == 2
    assert consulta(client, 999999999, t, t).status_code == 404
    assert consulta(client, columna.id_mp_cl, t + dt.timedelta(days=1), t).status_code == 422


def test_formato_deduplicacion_y_resumen_antes_del_muestreo(client, db_session, escenario_basico):
    e = escenario_basico
    c = db_session.query(MapeoColumna).filter_by(id_prmtr=e["parametro"].id_prmtr).one()
    c.visualizacion = {"significado": "secuencia", "vista": "kpi"}
    formato2 = MapeoFormato(id_dspstv=e["dispositivo"].id_dspstv, tp_trm="P", frmt_fch="%Y-%m-%d")
    db_session.add(formato2)
    db_session.flush()
    db_session.add(
        MapeoColumna(id_mp=formato2.id_mp, indc_clmn=1, id_prmtr=e["parametro"].id_prmtr)
    )
    archivos = []
    for nombre in ["/ruta/h_datos.dat", "P_datos.dat"]:
        a = ArchivoIngesta(id_cnxn=e["dispositivo"].id_cnxn, nmbr_archv=nombre)
        db_session.add(a)
        db_session.flush()
        archivos.append(a)
    t = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    for minutos, valor, origen in [(1, 100, 0), (2, 101, 0), (2, 101, 0), (3, 105, 0), (4, 999, 1)]:
        m = crear_medicion(
            db_session,
            e["dispositivo"],
            e["parametro"],
            e["sede"],
            valor=valor,
            fecha=t + dt.timedelta(minutes=minutos),
        )
        m.id_archv = archivos[origen].id_archv
    db_session.flush()
    respuesta = consulta(client, c.id_mp_cl, t, t + dt.timedelta(minutes=10), max_puntos=2)
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert len(datos["items"]) == 2
    assert datos["muestreado"]
    assert datos["resumen"]["valor"] == 3
    assert datos["resumen"]["duplicados"] == 1
    assert sum(b["delta"] for b in datos["resumen"]["barras"]) == 3


def test_resumen_completo_al_leer_mas_de_un_lote(client, db_session, escenario_basico):
    e = escenario_basico
    columna = db_session.query(MapeoColumna).filter_by(id_prmtr=e["parametro"].id_prmtr).one()
    columna.visualizacion = {"significado": "secuencia", "vista": "kpi"}
    inicio = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)
    filas = [
        {
            "fch_hr": inicio + dt.timedelta(seconds=i),
            "id_dspstv": e["dispositivo"].id_dspstv,
            "id_prmtr": e["parametro"].id_prmtr,
            "id_sd": e["sede"].id_sd,
            "vlr": i,
        }
        for i in range(1100)
    ]
    filas.append(dict(filas[999]))
    db_session.execute(Telemetria.__table__.insert(), filas)
    db_session.flush()

    respuesta = consulta(
        client, columna.id_mp_cl, inicio, inicio + dt.timedelta(minutes=20), max_puntos=3
    )
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert [p["vlr"] for p in datos["items"]] == [0, 550, 1099]
    assert datos["resumen"]["lecturas"] == 1100
    assert datos["resumen"]["duplicados"] == 1
    assert datos["resumen"]["valor"] == 1100
    assert sum(b["delta"] for b in datos["resumen"]["barras"]) == 1100


def test_serie_ajena_no_se_expone(client, db_session, escenario_basico, fabrica):
    from tests.routers.test_mediciones import crear_ubicacion

    e = escenario_basico
    sede = fabrica.sede()
    ubicacion = crear_ubicacion(db_session, sede)
    dispositivo = crear_dispositivo(db_session, ubicacion, crear_conexion(db_session, sede))
    mapear_parametro(db_session, dispositivo, e["parametro"])
    c = (
        db_session.query(MapeoColumna)
        .join(MapeoFormato)
        .filter(MapeoFormato.id_dspstv == dispositivo.id_dspstv)
        .one()
    )
    t = dt.datetime.now(dt.timezone.utc)
    assert consulta(client, c.id_mp_cl, t, t).status_code == 404
    assert (
        client.get("/mediciones/series", params={"ubicacion_id": ubicacion.id_ubccn}).json()[
            "items"
        ]
        == []
    )


def test_configuracion_se_guarda_por_columna_y_se_conserva(
    client, db_session, escenario_basico, monkeypatch
):
    from app.main import app
    from app.security.dependencies import get_current_user
    from tests.routers.test_mediciones import agregar_permiso, usuario_jwt

    e = escenario_basico
    # Este test verifica mapeos; el contrato comercial tiene sus propios tests.
    monkeypatch.setenv("PLAN_LIMITS_REQUIRE_SUBSCRIPTION", "false")
    agregar_permiso(db_session, e["usuario"], e["sede"], "Ingesta", "Edición", e["rol"])
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        e["usuario"], e["rol"].nmbr, sede_id=e["sede"].id_sd
    )
    m = db_session.query(MapeoFormato).filter_by(id_dspstv=e["dispositivo"].id_dspstv).one()
    columna = {
        "indc_clmn": 1,
        "id_prmtr": e["parametro"].id_prmtr,
        "visualizacion": {"significado": "secuencia", "vista": "kpi", "confirmada": True},
    }
    respuesta = client.put(f"/mapeos/{m.id_mp}", json={"columnas": [columna]})
    assert respuesta.status_code == 200, respuesta.text
    detalle = client.get(f"/mapeos/{m.id_mp}").json()
    assert detalle["columnas"][0]["visualizacion"]["significado"] == "secuencia"
    del columna["visualizacion"]
    assert client.put(f"/mapeos/{m.id_mp}", json={"columnas": [columna]}).status_code == 200
    assert (
        client.get(f"/mapeos/{m.id_mp}").json()["columnas"][0]["visualizacion"]["significado"]
        == "secuencia"
    )
    columna["visualizacion"] = {"significado": "contador", "vista": "linea"}
    assert client.put(f"/mapeos/{m.id_mp}", json={"columnas": [columna]}).status_code == 422
