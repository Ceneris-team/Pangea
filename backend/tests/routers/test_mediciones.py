"""
HU 13 - Seleccionar parámetros y ubicaciones: tests de CA1 (selector de
parámetros solo con lo mapeado en HU06 para las ubicaciones asignadas al
usuario), CA2 (filtro por parámetro), CA3 (filtro por ubicación, sobre el
selector de ubicaciones reusado de HU07) y CA4 re-redactado en DEC-11
(RAID_LOG_PANGEA.md): "LIMPIAR FILTROS" ya no depende de ningún filtro de
fecha, solo restaura todos los datos disponibles para la cuenta.

La auditoría del 12/08/2026 encontró la lógica de negocio ya correcta y
sin test; este archivo cubre esa ausencia, en particular el aislamiento
por PermisoUbicacion (HU21), que es el punto crítico de la HU.

Corre contra la Postgres real de test (ver conftest.py). Las filas de
`tlmtr` usan `datetime.now()` como fch_hr: la migración de HT-08 y el job
de Beat mantienen particiones creadas alrededor de la fecha real, así que
no hace falta invocar asegurar_particiones() a mano.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    Dispositivo,
    EventoTexto,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    PermisoUbicacion,
    Telemetria,
    Ubicacion,
)
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user

POLIGONO_DUMMY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


def usuario_jwt(usuario_db, rol_nombre, sede_id=None, scope="por_sede"):
    return {"sub": str(usuario_db.id_usr), "sede_id": sede_id, "scope": scope, "rol": rol_nombre}


def agregar_permiso(db, usuario_db, sede_db, modulo, nivel, rol_db):
    db.add(
        PermisoUsuarioSede(
            id_usr=usuario_db.id_usr, id_sd=sede_db.id_sd, id_rl=rol_db.id_rl, mdl=modulo, nvl=nivel
        )
    )
    db.flush()


def asignar_ubicacion(db, usuario_db, ubicacion):
    db.add(PermisoUbicacion(id_usr=usuario_db.id_usr, id_ubccn=ubicacion.id_ubccn))
    db.flush()


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def crear_ubicacion(db_session, sede, nombre="Ubicacion de prueba"):
    ubicacion = Ubicacion(
        id_sd=sede.id_sd,
        nmbr=nombre,
        lttd=0,
        lngtd=0,
        plgn_gjsn=POLIGONO_DUMMY,
    )
    db_session.add(ubicacion)
    db_session.flush()
    return ubicacion


def crear_conexion(db_session, sede, nombre="Datalogger de prueba"):
    from app.models import ConexionFTP

    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=nombre,
        prtcl="FTP",
        hst="127.0.0.1",
        prt=21,
        usr_ftp="usr",
        crdncl_cfrd="cifrado-de-prueba",
        rt_rmt="/data",
        frcnc_mnts=1,
        estd="Activa",
    )
    db_session.add(conexion)
    db_session.flush()
    return conexion


def crear_dispositivo(db_session, ubicacion, conexion, nombre="CR1000-HU13", marca="Campbell"):
    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=nombre,
        mrc=marca,
        lttd=0,
        lngtd=0,
        estd="Activo",
    )
    db_session.add(dispositivo)
    db_session.flush()
    return dispositivo


def crear_parametro(db_session, nombre, unidad="u", tipo_dato="numerico"):
    parametro = Parametro(
        nmbr=nombre, undd=unidad, dscrpcn="parámetro creado por los tests", tipo_dato=tipo_dato
    )
    db_session.add(parametro)
    db_session.flush()
    return parametro


def mapear_parametro(db_session, dispositivo, parametro, indice=1, tipo_trama="H"):
    """DEC-09: el mapeo cuelga del dispositivo (mp_frmt.id_dspstv), y la
    columna del archivo se enlaza al parámetro vía mp_clmn. Sin esta
    cadena completa, listar_parametros_disponibles no debe devolver el
    parámetro (CA1: solo catálogo mapeado, no toda la tabla prmtr).

    Un dispositivo admite como máximo un mp_frmt ACTIVO por tipo de
    trama (uq_mpfrmt_dspstv_tptrm_activo); para mapear un segundo
    parámetro del mismo dispositivo/tipo de trama hay que agregar otra
    mp_clmn (otro índice de columna) al mapeo ya existente, no crear un
    mp_frmt nuevo.
    """
    mapeo = (
        db_session.query(MapeoFormato)
        .filter(
            MapeoFormato.id_dspstv == dispositivo.id_dspstv,
            MapeoFormato.tp_trm == tipo_trama,
            MapeoFormato.estd == "Activo",
        )
        .first()
    )
    if mapeo is None:
        mapeo = MapeoFormato(
            id_dspstv=dispositivo.id_dspstv,
            tp_trm=tipo_trama,
            dlmtdr=",",
            fl_inc_dts=1,
            frmt_fch="%Y-%m-%d %H:%M:%S",
        )
        db_session.add(mapeo)
        db_session.flush()
    columna = MapeoColumna(id_mp=mapeo.id_mp, indc_clmn=indice, id_prmtr=parametro.id_prmtr)
    db_session.add(columna)
    db_session.flush()
    return mapeo


def crear_medicion(db_session, dispositivo, parametro, sede, valor=10.0, fecha=None):
    fecha = fecha or dt.datetime.now(dt.timezone.utc)
    medicion = Telemetria(
        fch_hr=fecha,
        id_dspstv=dispositivo.id_dspstv,
        id_prmtr=parametro.id_prmtr,
        id_sd=sede.id_sd,
        vlr=valor,
    )
    db_session.add(medicion)
    db_session.flush()
    return medicion


def crear_evento_texto(db_session, dispositivo, parametro, sede, valor="Puerta Abierta", fecha=None):
    evento = EventoTexto(
        fch_hr=fecha or dt.datetime.now(dt.timezone.utc),
        id_dspstv=dispositivo.id_dspstv,
        id_prmtr=parametro.id_prmtr,
        id_sd=sede.id_sd,
        vlr=valor,
    )
    db_session.add(evento)
    db_session.flush()
    return evento


@pytest.fixture()
def escenario_basico(db_session, fabrica):
    """Cliente Final con UNA ubicación asignada, un dispositivo con un
    parámetro mapeado, y una medición ya persistida. Devuelve todas las
    piezas para que cada test arme variaciones encima."""
    rol_cliente = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol_cliente)
    agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol_cliente)

    ubicacion = crear_ubicacion(db_session, sede, nombre="Ubicacion Asignada")
    asignar_ubicacion(db_session, usuario, ubicacion)

    conexion = crear_conexion(db_session, sede)
    dispositivo = crear_dispositivo(db_session, ubicacion, conexion)
    parametro = crear_parametro(db_session, "Temperatura HU13", unidad="°C")
    mapear_parametro(db_session, dispositivo, parametro)
    medicion = crear_medicion(db_session, dispositivo, parametro, sede)

    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol_cliente.nmbr, sede_id=sede.id_sd
    )

    return {
        "usuario": usuario,
        "rol": rol_cliente,
        "sede": sede,
        "ubicacion": ubicacion,
        "dispositivo": dispositivo,
        "parametro": parametro,
        "medicion": medicion,
    }


class TestCA1SelectorDeParametros:
    """CA1: la lista de /mediciones/parametros depende de las ubicaciones
    asignadas (PermisoUbicacion, HU21) y del mapeo real (mp_clmn/mp_frmt,
    HU06), no del catálogo completo de prmtr."""

    def test_devuelve_solo_parametros_mapeados_de_las_ubicaciones_asignadas(
        self, client, db_session, escenario_basico
    ):
        resp = client.get("/mediciones/parametros")
        assert resp.status_code == 200
        nombres = [p["nmbr"] for p in resp.json()["items"]]
        assert nombres == ["Temperatura HU13"]

    def test_parametro_del_catalogo_sin_mapear_no_aparece(
        self, client, db_session, escenario_basico
    ):
        # CA1 explícito: existe en prmtr pero nunca se enlazó vía mp_clmn
        # a ningún dispositivo de las ubicaciones del usuario.
        crear_parametro(db_session, "pH Sin Mapear", unidad="pH")

        resp = client.get("/mediciones/parametros")
        nombres = [p["nmbr"] for p in resp.json()["items"]]
        assert nombres == ["Temperatura HU13"]
        assert "pH Sin Mapear" not in nombres

    def test_parametro_mapeado_en_ubicacion_ajena_no_aparece(
        self, client, db_session, escenario_basico, fabrica
    ):
        # Mismo cliente, pero el parámetro está mapeado en un dispositivo
        # de una ubicación que NO le fue asignada.
        sede = escenario_basico["sede"]
        ubicacion_ajena = crear_ubicacion(db_session, sede, nombre="Ubicacion No Asignada")
        conexion = crear_conexion(db_session, sede, nombre="Datalogger Ajeno")
        dispositivo_ajeno = crear_dispositivo(
            db_session, ubicacion_ajena, conexion, nombre="CR1000-Ajeno"
        )
        parametro_ajeno = crear_parametro(db_session, "Conductividad Ajena", unidad="uS/cm")
        mapear_parametro(db_session, dispositivo_ajeno, parametro_ajeno)

        resp = client.get("/mediciones/parametros")
        nombres = [p["nmbr"] for p in resp.json()["items"]]
        assert nombres == ["Temperatura HU13"]
        assert "Conductividad Ajena" not in nombres

    def test_cliente_final_sin_ubicaciones_asignadas_recibe_lista_vacia(
        self, client, db_session, fabrica
    ):
        # Caso marcado como crítico en la auditoría: ni error 500 ni fuga
        # de datos de otras cuentas, solo lista vacía.
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol)
        # Existe una ubicación con parámetro mapeado en la sede, pero no
        # se le asignó al usuario vía PermisoUbicacion.
        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        dispositivo = crear_dispositivo(db_session, ubicacion, conexion)
        parametro = crear_parametro(db_session, "Temperatura No Asignada")
        mapear_parametro(db_session, dispositivo, parametro)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.get("/mediciones/parametros")
        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    def test_administrador_ve_parametros_de_todas_las_ubicaciones_sin_restriccion(
        self, client, db_session, escenario_basico, fabrica
    ):
        # Mismo patrón que HU07/HU10: Administrador no pasa por
        # PermisoUbicacion. Se agrega una ubicación de OTRA sede con su
        # propio parámetro mapeado para confirmar que también la ve.
        otra_sede = fabrica.sede()
        otra_ubicacion = crear_ubicacion(db_session, otra_sede, nombre="Ubicacion Otra Sede")
        otra_conexion = crear_conexion(db_session, otra_sede, nombre="Datalogger Otra Sede")
        otro_dispositivo = crear_dispositivo(
            db_session, otra_ubicacion, otra_conexion, nombre="CR1000-OtraSede"
        )
        otro_parametro = crear_parametro(db_session, "Turbidez Otra Sede", unidad="NTU")
        mapear_parametro(db_session, otro_dispositivo, otro_parametro)

        rol_admin = fabrica.rol("Administrador")
        admin = fabrica.usuario(rol=rol_admin)
        agregar_permiso(
            db_session, admin, escenario_basico["sede"], "Tableros", "Lectura", rol_admin
        )
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            admin, rol_admin.nmbr, sede_id=escenario_basico["sede"].id_sd
        )

        resp = client.get("/mediciones/parametros")
        nombres = {p["nmbr"] for p in resp.json()["items"]}
        assert nombres == {"Temperatura HU13", "Turbidez Otra Sede"}

    def test_tecnico_ceneris_ve_parametros_sin_restriccion_de_permiso_ubicacion(
        self, client, db_session, escenario_basico, fabrica
    ):
        rol_tecnico = fabrica.rol("Técnico CENERIS")
        tecnico = fabrica.usuario(rol=rol_tecnico)
        agregar_permiso(
            db_session, tecnico, escenario_basico["sede"], "Tableros", "Lectura", rol_tecnico
        )
        # El técnico NO tiene fila en PermisoUbicacion para esta ubicación.
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            tecnico, rol_tecnico.nmbr, sede_id=escenario_basico["sede"].id_sd
        )

        resp = client.get("/mediciones/parametros")
        nombres = [p["nmbr"] for p in resp.json()["items"]]
        assert nombres == ["Temperatura HU13"]


class TestCA2FiltroPorParametro:
    """CA2: seleccionar uno o más parámetros y aplicar devuelve solo esos
    registros."""

    def test_filtra_por_un_parametro(self, client, db_session, escenario_basico):
        otro_parametro = crear_parametro(db_session, "Humedad HU13", unidad="%")
        mapear_parametro(db_session, escenario_basico["dispositivo"], otro_parametro, indice=2)
        crear_medicion(
            db_session,
            escenario_basico["dispositivo"],
            otro_parametro,
            escenario_basico["sede"],
            valor=55.0,
        )

        resp = client.get(
            "/mediciones", params={"parametro_ids": [escenario_basico["parametro"].id_prmtr]}
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["parametro_nombre"] == "Temperatura HU13"

    def test_seleccion_multiple_de_parametros(self, client, db_session, escenario_basico):
        parametro_2 = crear_parametro(db_session, "Humedad HU13", unidad="%")
        mapear_parametro(db_session, escenario_basico["dispositivo"], parametro_2, indice=2)
        crear_medicion(
            db_session,
            escenario_basico["dispositivo"],
            parametro_2,
            escenario_basico["sede"],
            valor=55.0,
        )

        parametro_3 = crear_parametro(db_session, "Presion HU13", unidad="hPa")
        mapear_parametro(db_session, escenario_basico["dispositivo"], parametro_3, indice=3)
        crear_medicion(
            db_session,
            escenario_basico["dispositivo"],
            parametro_3,
            escenario_basico["sede"],
            valor=1013.0,
        )

        resp = client.get(
            "/mediciones",
            params={
                "parametro_ids": [escenario_basico["parametro"].id_prmtr, parametro_2.id_prmtr]
            },
        )
        body = resp.json()
        nombres = {i["parametro_nombre"] for i in body["items"]}
        assert body["total"] == 2
        assert nombres == {"Temperatura HU13", "Humedad HU13"}
        assert "Presion HU13" not in nombres


class TestCA3FiltroPorUbicacionYAislamiento:
    """CA3 + aislamiento: selector de ubicaciones (GET /ubicaciones, HU07)
    y filtro de /mediciones respetan PermisoUbicacion; un id ajeno no se
    puede forzar por query param."""

    def test_selector_de_ubicaciones_solo_devuelve_las_asignadas(
        self, client, db_session, escenario_basico, fabrica
    ):
        # El selector de ubicaciones de ConsultaDatos.tsx llama a GET
        # /ubicaciones (HU07), que exige permiso sobre el módulo
        # "Ubicaciones" -distinto del "Tableros" que exige /mediciones*-.
        # El seed real (seed_usuarios_prueba.py) le da ambos a Cliente
        # Final; se replica aquí para que el escenario sea representativo.
        agregar_permiso(
            db_session,
            escenario_basico["usuario"],
            escenario_basico["sede"],
            "Ubicaciones",
            "Lectura",
            escenario_basico["rol"],
        )
        # Otra ubicación de la MISMA sede, pero no asignada al usuario.
        crear_ubicacion(db_session, escenario_basico["sede"], nombre="Ubicacion No Asignada")

        resp = client.get("/ubicaciones", params={"por_pagina": 100})
        nombres = [u["nmbr"] for u in resp.json()["items"]]
        assert nombres == ["Ubicacion Asignada"]

    def test_filtra_por_ubicacion_asignada(self, client, db_session, escenario_basico):
        resp = client.get(
            "/mediciones", params={"ubicacion_ids": [escenario_basico["ubicacion"].id_ubccn]}
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["ubicacion_nombre"] == "Ubicacion Asignada"

    def test_seleccion_multiple_de_ubicaciones(self, client, db_session, escenario_basico):
        sede = escenario_basico["sede"]
        usuario = escenario_basico["usuario"]

        ubicacion_2 = crear_ubicacion(db_session, sede, nombre="Ubicacion Asignada 2")
        asignar_ubicacion(db_session, usuario, ubicacion_2)
        conexion_2 = crear_conexion(db_session, sede, nombre="Datalogger 2")
        dispositivo_2 = crear_dispositivo(db_session, ubicacion_2, conexion_2, nombre="CR1000-2")
        mapear_parametro(db_session, dispositivo_2, escenario_basico["parametro"], indice=1)
        crear_medicion(db_session, dispositivo_2, escenario_basico["parametro"], sede, valor=20.0)

        resp = client.get(
            "/mediciones",
            params={
                "ubicacion_ids": [
                    escenario_basico["ubicacion"].id_ubccn,
                    ubicacion_2.id_ubccn,
                ]
            },
        )
        body = resp.json()
        ubicaciones = {i["ubicacion_nombre"] for i in body["items"]}
        assert body["total"] == 2
        assert ubicaciones == {"Ubicacion Asignada", "Ubicacion Asignada 2"}

    def test_no_puede_forzar_una_ubicacion_no_asignada_por_query_param(
        self, client, db_session, escenario_basico, fabrica
    ):
        # Ubicación ajena, con su propio dispositivo/medición, en otra
        # sede -para no depender de PermisoUbicacion de la sede propia.
        otra_sede = fabrica.sede()
        ubicacion_ajena = crear_ubicacion(db_session, otra_sede, nombre="Ubicacion Ajena")
        conexion_ajena = crear_conexion(db_session, otra_sede, nombre="Datalogger Ajeno")
        dispositivo_ajeno = crear_dispositivo(
            db_session, ubicacion_ajena, conexion_ajena, nombre="CR1000-Ajeno"
        )
        parametro_ajeno = crear_parametro(db_session, "Nivel Ajeno", unidad="m")
        mapear_parametro(db_session, dispositivo_ajeno, parametro_ajeno)
        crear_medicion(db_session, dispositivo_ajeno, parametro_ajeno, otra_sede, valor=99.0)

        # El Cliente Final pide explícitamente la ubicación ajena por id.
        resp = client.get("/mediciones", params={"ubicacion_ids": [ubicacion_ajena.id_ubccn]})
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_filtro_combinado_de_parametro_y_ubicacion_es_interseccion(
        self, client, db_session, escenario_basico
    ):
        sede = escenario_basico["sede"]
        usuario = escenario_basico["usuario"]

        # Segunda ubicación asignada, con un parámetro DISTINTO.
        ubicacion_2 = crear_ubicacion(db_session, sede, nombre="Ubicacion Asignada 2")
        asignar_ubicacion(db_session, usuario, ubicacion_2)
        conexion_2 = crear_conexion(db_session, sede, nombre="Datalogger 2")
        dispositivo_2 = crear_dispositivo(db_session, ubicacion_2, conexion_2, nombre="CR1000-2")
        parametro_2 = crear_parametro(db_session, "Humedad HU13", unidad="%")
        mapear_parametro(db_session, dispositivo_2, parametro_2, indice=1)
        crear_medicion(db_session, dispositivo_2, parametro_2, sede, valor=40.0)

        # También el parámetro original está mapeado y medido en la
        # ubicación 2 (mismo parámetro, otra ubicación).
        mapear_parametro(db_session, dispositivo_2, escenario_basico["parametro"], indice=2)
        crear_medicion(db_session, dispositivo_2, escenario_basico["parametro"], sede, valor=30.0)

        # Pide: parametro de la ubicacion 1, pero filtrando por ubicacion 2.
        # La interseccion debe ser el registro de "Temperatura HU13" en
        # Ubicacion Asignada 2, NO el de Ubicacion Asignada (ubicación
        # excluida) ni el de "Humedad HU13" (parámetro excluido).
        resp = client.get(
            "/mediciones",
            params={
                "parametro_ids": [escenario_basico["parametro"].id_prmtr],
                "ubicacion_ids": [ubicacion_2.id_ubccn],
            },
        )
        body = resp.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["parametro_nombre"] == "Temperatura HU13"
        assert item["ubicacion_nombre"] == "Ubicacion Asignada 2"

    def test_administrador_ve_ubicaciones_de_cualquier_sede_sin_permiso_ubicacion(
        self, client, db_session, escenario_basico, fabrica
    ):
        # Mismo patrón que HU07: Administrador no pasa por PermisoUbicacion.
        otra_sede = fabrica.sede()
        crear_ubicacion(db_session, otra_sede, nombre="Ubicacion Admin")

        rol_admin = fabrica.rol("Administrador")
        admin = fabrica.usuario(rol=rol_admin)
        agregar_permiso(db_session, admin, otra_sede, "Ubicaciones", "Lectura", rol_admin)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            admin, rol_admin.nmbr, sede_id=otra_sede.id_sd
        )

        resp = client.get("/ubicaciones", params={"por_pagina": 100})
        nombres = {u["nmbr"] for u in resp.json()["items"]}
        assert "Ubicacion Admin" in nombres
        assert "Ubicacion Asignada" in nombres  # de escenario_basico, otra sede


class TestFiltroPorDispositivo:
    """Una Ubicación puede tener más de un Dispositivo -dos dataloggers
    midiendo el mismo parámetro en la misma estación, caso real reportado
    sobre HU15 (visualización de gráficos): sin este filtro, sus lecturas
    llegaban mezcladas y no había forma de aislar la serie de uno solo."""

    def test_filtra_por_dispositivo_dentro_de_la_misma_ubicacion(
        self, client, db_session, escenario_basico
    ):
        ubicacion = escenario_basico["ubicacion"]
        sede = escenario_basico["sede"]
        parametro = escenario_basico["parametro"]

        # Segundo datalogger de la MISMA ubicación, midiendo el mismo
        # parámetro -el escenario exacto de "Estacion Prueba" con dos
        # dataloggers-.
        conexion_2 = crear_conexion(db_session, sede, nombre="Datalogger 2")
        dispositivo_2 = crear_dispositivo(
            db_session, ubicacion, conexion_2, nombre="CR1000-2"
        )
        mapear_parametro(db_session, dispositivo_2, parametro, indice=1)
        crear_medicion(db_session, dispositivo_2, parametro, sede, valor=99.0)

        resp = client.get(
            "/mediciones",
            params={"dispositivo_ids": [escenario_basico["dispositivo"].id_dspstv]},
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["vlr"] == 10.0  # el de escenario_basico, no el 99.0

    def test_dispositivo_de_ubicacion_no_asignada_no_devuelve_nada(
        self, client, db_session, escenario_basico, fabrica
    ):
        # Un id_dspstv de una ubicación fuera de PermisoUbicacion no debe
        # colarse: el filtro de ubicaciones permitidas sigue aplicando
        # siempre, así que pedir ese id simplemente no matchea ninguna fila
        # -no hace falta validar dispositivo_ids contra una whitelist
        # aparte para que el aislamiento se sostenga-.
        sede = escenario_basico["sede"]
        ubicacion_ajena = crear_ubicacion(db_session, sede, nombre="Ubicacion No Asignada")
        conexion_ajena = crear_conexion(db_session, sede, nombre="Datalogger Ajeno")
        dispositivo_ajeno = crear_dispositivo(db_session, ubicacion_ajena, conexion_ajena)
        mapear_parametro(db_session, dispositivo_ajeno, escenario_basico["parametro"], indice=1)
        crear_medicion(db_session, dispositivo_ajeno, escenario_basico["parametro"], sede, valor=77.0)

        resp = client.get(
            "/mediciones",
            params={"dispositivo_ids": [dispositivo_ajeno.id_dspstv]},
        )
        assert resp.json()["total"] == 0


class TestCA4LimpiarFiltros:
    """CA4 (re-redactado, DEC-11): sin filtros aplicados o tras
    limpiarlos, se muestran todos los datos disponibles para la cuenta,
    sin depender de ningún filtro de fecha."""

    def test_sin_filtros_devuelve_todos_los_datos_disponibles_para_la_cuenta(
        self, client, db_session, escenario_basico
    ):
        parametro_2 = crear_parametro(db_session, "Humedad HU13", unidad="%")
        mapear_parametro(db_session, escenario_basico["dispositivo"], parametro_2, indice=2)
        crear_medicion(
            db_session,
            escenario_basico["dispositivo"],
            parametro_2,
            escenario_basico["sede"],
            valor=55.0,
        )

        resp = client.get("/mediciones")
        body = resp.json()
        assert body["total"] == 2
        nombres = {i["parametro_nombre"] for i in body["items"]}
        assert nombres == {"Temperatura HU13", "Humedad HU13"}

    def test_quitar_los_filtros_equivale_a_no_haber_filtrado(
        self, client, db_session, escenario_basico
    ):
        parametro_2 = crear_parametro(db_session, "Humedad HU13", unidad="%")
        mapear_parametro(db_session, escenario_basico["dispositivo"], parametro_2, indice=2)
        crear_medicion(
            db_session,
            escenario_basico["dispositivo"],
            parametro_2,
            escenario_basico["sede"],
            valor=55.0,
        )

        # Simula "APLICAR" con un filtro de parámetro.
        filtrado = client.get(
            "/mediciones", params={"parametro_ids": [escenario_basico["parametro"].id_prmtr]}
        ).json()
        assert filtrado["total"] == 1

        # Simula "LIMPIAR FILTROS": la misma consulta sin ningún query param.
        limpio = client.get("/mediciones").json()
        assert limpio["total"] == 2
        assert {i["parametro_nombre"] for i in limpio["items"]} == {
            "Temperatura HU13",
            "Humedad HU13",
        }

    def test_cliente_final_sin_ubicaciones_asignadas_no_ve_mediciones(
        self, client, db_session, fabrica
    ):
        # Mismo caso crítico que CA1, pero contra el endpoint de datos:
        # debe devolver 0 resultados, no error ni datos de otra cuenta.
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol)

        ubicacion = crear_ubicacion(db_session, sede)
        conexion = crear_conexion(db_session, sede)
        dispositivo = crear_dispositivo(db_session, ubicacion, conexion)
        parametro = crear_parametro(db_session, "Temperatura No Asignada")
        mapear_parametro(db_session, dispositivo, parametro)
        crear_medicion(db_session, dispositivo, parametro, sede)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.get("/mediciones")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []


class TestEventosDeTexto:
    """Un parámetro tipo_dato='texto' (ej. "MensajeP" de una trama de
    puerta) se persiste en evnt_txt, no en tlmtr -y antes de esto
    /mediciones no lo consultaba: aparecía en el selector de parámetros
    (CA1 no filtra por tipo) pero nunca en la tabla de resultados."""

    def test_evento_de_texto_aparece_en_los_resultados(self, client, db_session, escenario_basico):
        parametro_txt = crear_parametro(db_session, "MensajeP", unidad="-", tipo_dato="texto")
        mapear_parametro(
            db_session, escenario_basico["dispositivo"], parametro_txt, indice=2, tipo_trama="P"
        )
        crear_evento_texto(
            db_session,
            escenario_basico["dispositivo"],
            parametro_txt,
            escenario_basico["sede"],
            valor="Puerta Abierta",
        )

        resp = client.get("/mediciones")
        body = resp.json()
        assert body["total"] == 2  # la medición numérica de escenario_basico + este evento
        item = next(i for i in body["items"] if i["parametro_nombre"] == "MensajeP")
        assert item["vlr"] == "Puerta Abierta"

    def test_filtra_eventos_de_texto_por_parametro(self, client, db_session, escenario_basico):
        parametro_txt = crear_parametro(db_session, "MensajeP", unidad="-", tipo_dato="texto")
        mapear_parametro(
            db_session, escenario_basico["dispositivo"], parametro_txt, indice=2, tipo_trama="P"
        )
        crear_evento_texto(
            db_session,
            escenario_basico["dispositivo"],
            parametro_txt,
            escenario_basico["sede"],
            valor="Llave No Encontrada",
        )

        resp = client.get("/mediciones", params={"parametro_ids": [parametro_txt.id_prmtr]})
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["vlr"] == "Llave No Encontrada"


class TestHU32FiltrosAvanzados:
    """HU32: valor mínimo/máximo (decimales, acumulativo = rango) y
    frecuencia de muestreo (minutos), sobre los parámetros/ubicaciones ya
    seleccionados en HU13. Los 4 CA de la HU + los dos casos que la HT
    marca como fáciles de romper: que valor_min/max no toque EventoTexto
    y que dos consultas con filtros avanzados distintos no comparta
    caché."""

    @pytest.fixture(autouse=True)
    def _cache_limpia(self):
        # Cada test de esta clase reutiliza escenario_basico (misma sede
        # y usuario), así que dos ejecuciones consecutivas de la suite
        # comparten ámbito de caché -sin esto, una entrada que dejó una
        # corrida anterior podría servirle a la siguiente su respuesta
        # vieja. Se saltea sola si no hay Redis, igual que test_cache_ht10.
        from app.services.cache import consultas as cache

        try:
            cache._cliente().ping()
            hay_redis = True
        except Exception:
            hay_redis = False
        if hay_redis:
            cache.invalidar_todo()
        yield
        if hay_redis:
            cache.invalidar_todo()

    def test_ca1_valor_minimo_y_maximo_acotan_el_rango(self, client, db_session, escenario_basico):
        dispositivo = escenario_basico["dispositivo"]
        parametro = escenario_basico["parametro"]
        sede = escenario_basico["sede"]
        # escenario_basico ya deja un valor en 10.0; se agregan el resto
        # del rango para poder distinguir "filtrado" de "todo".
        crear_medicion(db_session, dispositivo, parametro, sede, valor=1.0)
        crear_medicion(db_session, dispositivo, parametro, sede, valor=50.0)
        crear_medicion(db_session, dispositivo, parametro, sede, valor=99.0)

        resp = client.get("/mediciones", params={"valor_min": 5, "valor_max": 60})
        body = resp.json()
        valores = {i["vlr"] for i in body["items"]}
        assert valores == {10.0, 50.0}

    def test_ca2_aplicar_filtros_avanzados_solo_valor_minimo(
        self, client, db_session, escenario_basico
    ):
        dispositivo = escenario_basico["dispositivo"]
        parametro = escenario_basico["parametro"]
        sede = escenario_basico["sede"]
        crear_medicion(db_session, dispositivo, parametro, sede, valor=1.0)
        crear_medicion(db_session, dispositivo, parametro, sede, valor=200.0)

        resp = client.get("/mediciones", params={"valor_min": 15})
        body = resp.json()
        valores = {i["vlr"] for i in body["items"]}
        assert valores == {200.0}
        assert 10.0 not in valores and 1.0 not in valores

    def test_ca3_filtros_avanzados_se_combinan_con_rango_de_fechas_hu12(
        self, client, db_session, escenario_basico
    ):
        dispositivo = escenario_basico["dispositivo"]
        parametro = escenario_basico["parametro"]
        sede = escenario_basico["sede"]
        ahora = dt.datetime.now(dt.timezone.utc)

        # Dentro del rango de fechas Y dentro del rango de valor.
        crear_medicion(
            db_session, dispositivo, parametro, sede, valor=30.0, fecha=ahora - dt.timedelta(hours=1)
        )
        # Dentro del rango de fechas, pero FUERA del rango de valor.
        crear_medicion(
            db_session, dispositivo, parametro, sede, valor=999.0, fecha=ahora - dt.timedelta(hours=1)
        )
        # Dentro del rango de valor, pero FUERA del rango de fechas.
        crear_medicion(
            db_session, dispositivo, parametro, sede, valor=30.0, fecha=ahora - dt.timedelta(days=10)
        )

        resp = client.get(
            "/mediciones",
            params={
                "fecha_inicio": (ahora - dt.timedelta(days=1)).isoformat(),
                "fecha_fin": ahora.isoformat(),
                "valor_min": 5,
                "valor_max": 50,
            },
        )
        body = resp.json()
        # Solo el de escenario_basico (10.0, "ahora") + el de 30.0 dentro
        # de ambos rangos: la intersección, no la unión.
        valores = {i["vlr"] for i in body["items"]}
        assert valores == {10.0, 30.0}
        assert 999.0 not in valores

    def test_ca4_limpiar_filtros_avanzados_restaura_el_rango_de_fechas_activo(
        self, client, db_session, escenario_basico
    ):
        dispositivo = escenario_basico["dispositivo"]
        parametro = escenario_basico["parametro"]
        sede = escenario_basico["sede"]
        crear_medicion(db_session, dispositivo, parametro, sede, valor=500.0)

        con_filtro = client.get("/mediciones", params={"valor_max": 20}).json()
        assert con_filtro["total"] == 1
        assert con_filtro["items"][0]["vlr"] == 10.0

        # "LIMPIAR FILTROS AVANZADOS": misma consulta sin valor_min/max,
        # pero conservando el resto (aquí, sin filtros de fecha porque
        # escenario_basico no aplicó ninguno -CA4 no depende de eso-).
        sin_filtro = client.get("/mediciones").json()
        assert sin_filtro["total"] == 2
        assert {i["vlr"] for i in sin_filtro["items"]} == {10.0, 500.0}

    def test_valor_min_max_no_filtra_ni_rompe_eventos_de_texto(
        self, client, db_session, escenario_basico
    ):
        parametro_txt = crear_parametro(db_session, "MensajeP HU32", unidad="-", tipo_dato="texto")
        mapear_parametro(
            db_session, escenario_basico["dispositivo"], parametro_txt, indice=2, tipo_trama="P"
        )
        crear_evento_texto(
            db_session,
            escenario_basico["dispositivo"],
            parametro_txt,
            escenario_basico["sede"],
            valor="Puerta Abierta",
        )

        # valor_min/valor_max no deben excluir el evento de texto ni
        # romper con un error de comparación texto-vs-numero en Postgres.
        resp = client.get("/mediciones", params={"valor_min": 5, "valor_max": 20})
        assert resp.status_code == 200
        body = resp.json()
        nombres = {i["parametro_nombre"] for i in body["items"]}
        assert "MensajeP HU32" in nombres
        assert "Temperatura HU13" in nombres  # el numérico de 10.0, dentro del rango

    def test_frecuencia_muestreo_reduce_a_una_lectura_por_intervalo(
        self, client, db_session, escenario_basico
    ):
        dispositivo = escenario_basico["dispositivo"]
        parametro = escenario_basico["parametro"]
        sede = escenario_basico["sede"]
        ahora = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

        # Cuatro lecturas cada 5 minutos dentro de la misma ventana de 15
        # minutos que escenario_basico ya no toca (usa "ahora" real).
        base = ahora - dt.timedelta(hours=2)
        for i in range(4):
            crear_medicion(
                db_session, dispositivo, parametro, sede, valor=float(i), fecha=base + dt.timedelta(minutes=5 * i)
            )

        resp = client.get(
            "/mediciones",
            params={
                "fecha_inicio": (base - dt.timedelta(minutes=1)).isoformat(),
                "fecha_fin": (base + dt.timedelta(minutes=20)).isoformat(),
                "frecuencia_muestreo": 15,
            },
        )
        body = resp.json()
        # 20 minutos de datos a intervalos de 5' son 4 lecturas; a 15'
        # de frecuencia, como mucho 2 buckets caben en esa ventana.
        assert body["total"] <= 2

    def test_dos_consultas_con_filtros_avanzados_distintos_no_comparten_cache(
        self, client, db_session, escenario_basico
    ):
        dispositivo = escenario_basico["dispositivo"]
        parametro = escenario_basico["parametro"]
        sede = escenario_basico["sede"]
        crear_medicion(db_session, dispositivo, parametro, sede, valor=5.0)
        crear_medicion(db_session, dispositivo, parametro, sede, valor=500.0)

        resp_bajo = client.get("/mediciones", params={"valor_max": 20})
        resp_alto = client.get("/mediciones", params={"valor_min": 100})

        valores_bajo = {i["vlr"] for i in resp_bajo.json()["items"]}
        valores_alto = {i["vlr"] for i in resp_alto.json()["items"]}

        # Si compartieran clave de caché, la segunda respuesta traería los
        # mismos resultados que la primera en vez de los suyos.
        assert valores_bajo == {5.0, 10.0}
        assert valores_alto == {500.0}
        assert valores_bajo != valores_alto


class TestDenegadoSinPermiso:
    def test_denegado_sin_permiso_en_tableros(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        # Sin agregar_permiso: ninguna fila en prms_usr_sd para "Tableros".
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        assert client.get("/mediciones").status_code == 403
        assert client.get("/mediciones/parametros").status_code == 403
