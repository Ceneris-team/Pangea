"""
HT-10 - Tests extremo a extremo de la caché de consultas.

Cubren los dos CA que no se pueden verificar con lógica pura (eso está en
tests/services/test_cache_consultas.py):

CA4 - AISLAMIENTO MULTI-SEDE. El más crítico del proyecto: los datos
      cacheados de una sede NUNCA se devuelven ante una petición de otra
      sede. Se verifica sobre los tres endpoints cacheados, y con el
      orden de peticiones que rompería una caché mal construida: la sede
      A pide PRIMERO (deja la entrada caliente) y la sede B pide
      inmediatamente después, con la MISMA URL.

CA2 - INVALIDACION al llegar una lectura nueva, por los DOS caminos de
      escritura: guardar_lecturas() (pipeline automático) y el endpoint
      de carga manual.

Corre contra la Postgres real de test (ver conftest.py) y contra el Redis
real. Los tests que necesitan Redis se saltan solos si no está levantado:
así la suite sigue siendo ejecutable en una máquina sin el stack completo
en vez de fallar con un error de conexión que no dice nada del código.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    ConexionFTP,
    Dispositivo,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    PermisoUbicacion,
    Telemetria,
    Ubicacion,
)
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user
from app.services.cache import consultas as cache

POLIGONO_DUMMY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


def _hay_redis() -> bool:
    try:
        # Sin close(): el cliente lo comparte el proceso (ver
        # consultas._cliente), cerrarlo acá lo rompería para los tests.
        cache._cliente().ping()
        return True
    except Exception:
        return False


requiere_redis = pytest.mark.skipif(
    not _hay_redis(), reason="HT-10: requiere Redis levantado (docker compose up redis)"
)


@pytest.fixture(autouse=True)
def _cache_limpia():
    """Cada test arranca con la caché vacía y la deja vacía.

    Sin esto, la entrada que deja un test le llega caliente al siguiente y
    los tests de aislamiento pasarían o fallarían según el orden de
    ejecución -justo el tipo de test que no puede ser frágil-.
    """
    if _hay_redis():
        cache.invalidar_todo()
    yield
    if _hay_redis():
        cache.invalidar_todo()


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


def _montar_sede(db, fabrica, nombre_ubicacion, valor, nombre_parametro):
    """Una sede completa y aislada: sede + ubicación + conexión +
    dispositivo + parámetro + una lectura con un valor RECONOCIBLE.

    El valor es distinto por sede a propósito: es lo que permite afirmar
    "esta respuesta trae datos de la otra sede" en vez de solo contar
    elementos.
    """
    sede = fabrica.sede()
    ubicacion = Ubicacion(
        id_sd=sede.id_sd, nmbr=nombre_ubicacion, lttd=1, lngtd=1, plgn_gjsn=POLIGONO_DUMMY
    )
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=f"FTP {nombre_ubicacion}",
        prtcl="FTP",
        hst="127.0.0.1",
        prt=21,
        usr_ftp="u",
        crdncl_cfrd="x",
        rt_rmt="/",
        frcnc_mnts=1,
        estd="Activa",
    )
    db.add_all([ubicacion, conexion])
    db.flush()

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=f"Disp {nombre_ubicacion}",
        mrc="Marca",
        lttd=1,
        lngtd=1,
    )
    db.add(dispositivo)
    db.flush()

    parametro = db.query(Parametro).filter(Parametro.nmbr == nombre_parametro).first()
    if parametro is None:
        parametro = Parametro(nmbr=nombre_parametro, undd="C")
        db.add(parametro)
        db.flush()

    db.add(
        Telemetria(
            fch_hr=dt.datetime.now(dt.timezone.utc),
            id_dspstv=dispositivo.id_dspstv,
            id_prmtr=parametro.id_prmtr,
            id_sd=sede.id_sd,
            vlr=valor,
        )
    )
    db.flush()
    return sede, ubicacion, dispositivo, parametro


def _usuario_de_sede(db, fabrica, sede, ubicacion, modulos):
    """Cliente Final con scope por_sede, con permiso sobre los módulos
    pedidos y con ESA ubicación asignada (HU21)."""
    rol = fabrica.rol("Cliente Final")
    usuario = fabrica.usuario(rol=rol, scp="por_sede")
    for modulo in modulos:
        agregar_permiso(db, usuario, sede, modulo, "Lectura", rol)
    asignar_ubicacion(db, usuario, ubicacion)
    return usuario


# ---------------------------------------------------------------------
# CA4 - aislamiento multi-sede
# ---------------------------------------------------------------------


@requiere_redis
class TestCA4AislamientoEntreSedes:
    """El CA más crítico: nada cacheado por una sede puede salir en la
    respuesta de otra.

    En los tres tests el orden es deliberado: la sede A pide primero (deja
    la caché caliente) y la sede B pide después con la misma URL. Con una
    clave construida solo con la query string -el error clásico-, B
    recibiría la respuesta de A y estos tests fallarían.
    """

    def test_mediciones_no_filtra_datos_entre_sedes(self, client, db_session, fabrica):
        sede_a, ubic_a, _, _ = _montar_sede(db_session, fabrica, "Ubic A", 11.11, "Temp HT10")
        sede_b, ubic_b, _, _ = _montar_sede(db_session, fabrica, "Ubic B", 99.99, "Temp HT10")
        usuario_a = _usuario_de_sede(db_session, fabrica, sede_a, ubic_a, ["Tableros"])
        usuario_b = _usuario_de_sede(db_session, fabrica, sede_b, ubic_b, ["Tableros"])

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_a, "Cliente Final", sede_id=sede_a.id_sd
        )
        respuesta_a = client.get("/mediciones").json()

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_b, "Cliente Final", sede_id=sede_b.id_sd
        )
        respuesta_b = client.get("/mediciones").json()

        valores_a = {item["vlr"] for item in respuesta_a["items"]}
        valores_b = {item["vlr"] for item in respuesta_b["items"]}
        assert 11.11 in valores_a and 99.99 not in valores_a
        assert 99.99 in valores_b and 11.11 not in valores_b

        ubicaciones_b = {item["id_ubccn"] for item in respuesta_b["items"]}
        assert ubic_a.id_ubccn not in ubicaciones_b

    def test_mapa_cliente_no_filtra_marcadores_entre_sedes(self, client, db_session, fabrica):
        """/mapa-cliente no tiene NINGUN parámetro de consulta, así que es
        el endpoint donde una clave sin ámbito colisionaría siempre."""
        sede_a, ubic_a, _, _ = _montar_sede(db_session, fabrica, "Mapa A", 11.11, "Temp HT10")
        sede_b, ubic_b, _, _ = _montar_sede(db_session, fabrica, "Mapa B", 99.99, "Temp HT10")
        usuario_a = _usuario_de_sede(db_session, fabrica, sede_a, ubic_a, ["Tableros"])
        usuario_b = _usuario_de_sede(db_session, fabrica, sede_b, ubic_b, ["Tableros"])

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_a, "Cliente Final", sede_id=sede_a.id_sd
        )
        items_a = client.get("/mapa-cliente").json()["items"]

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_b, "Cliente Final", sede_id=sede_b.id_sd
        )
        items_b = client.get("/mapa-cliente").json()["items"]

        assert [i["id_ubccn"] for i in items_a] == [ubic_a.id_ubccn]
        assert [i["id_ubccn"] for i in items_b] == [ubic_b.id_ubccn]
        assert "Mapa A" not in {i["nmbr"] for i in items_b}

    def test_ubicaciones_mapa_no_filtra_entre_sedes(self, client, db_session, fabrica):
        sede_a, ubic_a, _, _ = _montar_sede(db_session, fabrica, "HU22 A", 11.11, "Temp HT10")
        sede_b, ubic_b, _, _ = _montar_sede(db_session, fabrica, "HU22 B", 99.99, "Temp HT10")
        usuario_a = _usuario_de_sede(db_session, fabrica, sede_a, ubic_a, ["Ubicaciones"])
        usuario_b = _usuario_de_sede(db_session, fabrica, sede_b, ubic_b, ["Ubicaciones"])

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_a, "Cliente Final", sede_id=sede_a.id_sd
        )
        items_a = client.get("/ubicaciones/mapa").json()

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_b, "Cliente Final", sede_id=sede_b.id_sd
        )
        items_b = client.get("/ubicaciones/mapa").json()

        assert [i["id_ubccn"] for i in items_a] == [ubic_a.id_ubccn]
        assert [i["id_ubccn"] for i in items_b] == [ubic_b.id_ubccn]

    def test_dos_clientes_de_la_misma_sede_con_asignaciones_distintas(
        self, client, db_session, fabrica
    ):
        """Variante fina de CA4: misma sede, distinta asignación de HU21.

        Una clave que usara solo sede_id -y no el conjunto de ubicaciones-
        pasaría los tests de arriba y fallaría este, que es el caso real
        de dos Clientes Finales del mismo cliente corporativo.
        """
        sede = fabrica.sede()
        ubicaciones = []
        for nombre, valor in (("Comparte 1", 11.11), ("Comparte 2", 99.99)):
            ubicacion = Ubicacion(
                id_sd=sede.id_sd, nmbr=nombre, lttd=1, lngtd=1, plgn_gjsn=POLIGONO_DUMMY
            )
            db_session.add(ubicacion)
            db_session.flush()
            ubicaciones.append(ubicacion)

        rol = fabrica.rol("Cliente Final")
        usuario_1 = fabrica.usuario(rol=rol, scp="por_sede")
        usuario_2 = fabrica.usuario(rol=rol, scp="por_sede")
        for usuario, ubicacion in zip((usuario_1, usuario_2), ubicaciones):
            agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol)
            asignar_ubicacion(db_session, usuario, ubicacion)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_1, "Cliente Final", sede_id=sede.id_sd
        )
        items_1 = client.get("/mapa-cliente").json()["items"]

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario_2, "Cliente Final", sede_id=sede.id_sd
        )
        items_2 = client.get("/mapa-cliente").json()["items"]

        assert [i["id_ubccn"] for i in items_1] == [ubicaciones[0].id_ubccn]
        assert [i["id_ubccn"] for i in items_2] == [ubicaciones[1].id_ubccn]


# ---------------------------------------------------------------------
# CA2 - invalidación al llegar una lectura nueva
# ---------------------------------------------------------------------


@requiere_redis
class TestCA2Invalidacion:
    def test_guardar_lecturas_invalida_la_clave_de_su_sede(self, db_session, fabrica):
        """Camino 1: el pipeline automático.

        Se siembra una entrada de caché a mano con el índice de la sede y
        se comprueba que guardar_lecturas() la borra. Sembrar la entrada
        (en vez de pedirla por HTTP) aísla lo que este test verifica: la
        REGLA de invalidación, no el cacheado del endpoint -que ya cubren
        los tests de CA4-.
        """
        from app.services.ingesta.persistencia import guardar_lecturas
        from app.services.ingesta.validador import LecturaValidada

        sede, ubicacion, dispositivo, parametro = _montar_sede(
            db_session, fabrica, "Invalidacion pipeline", 1.0, "Temp HT10"
        )

        clave = cache.clave("mediciones", f"sd{sede.id_sd}:test")
        cache.guardar(clave, {"items": []}, indices=[cache.indice_de_sede(sede.id_sd)])
        assert cache.obtener(clave) is not None

        guardar_lecturas(
            db_session,
            [
                LecturaValidada(
                    numero_fila=1,
                    id_cnxn=dispositivo.id_cnxn,
                    fecha_hora=dt.datetime.now(dt.timezone.utc),
                    parametro=parametro.nmbr,
                    valor=42.0,
                )
            ],
            dispositivo,
            id_archv=None,
        )

        assert cache.obtener(clave) is None, (
            "CA2: una lectura nueva del pipeline debe invalidar la caché de su sede"
        )

    def test_guardar_lecturas_no_invalida_otras_sedes(self, db_session, fabrica):
        """Punto 3 de la HT: la invalidación es DIRIGIDA.

        Si cada lectura vaciara la caché entera, con el pipeline corriendo
        cada minuto sobre varias sedes la caché nunca sobreviviría hasta
        el segundo request y la HT no serviría de nada.
        """
        from app.services.ingesta.persistencia import guardar_lecturas
        from app.services.ingesta.validador import LecturaValidada

        sede_a, _, dispositivo_a, parametro = _montar_sede(
            db_session, fabrica, "Dirigida A", 1.0, "Temp HT10"
        )
        sede_b, _, _, _ = _montar_sede(db_session, fabrica, "Dirigida B", 2.0, "Temp HT10")

        clave_b = cache.clave("mediciones", f"sd{sede_b.id_sd}:test")
        cache.guardar(clave_b, {"items": []}, indices=[cache.indice_de_sede(sede_b.id_sd)])

        guardar_lecturas(
            db_session,
            [
                LecturaValidada(
                    numero_fila=1,
                    id_cnxn=dispositivo_a.id_cnxn,
                    fecha_hora=dt.datetime.now(dt.timezone.utc),
                    parametro=parametro.nmbr,
                    valor=42.0,
                )
            ],
            dispositivo_a,
            id_archv=None,
        )

        assert cache.obtener(clave_b) is not None, (
            "una lectura de la sede A no puede tirar la caché de la sede B"
        )

    def test_carga_manual_invalida_la_cache(self, client, db_session, fabrica):
        """Camino 2: POST /dispositivos/{id}/carga-manual, que escribe
        directo en tlmtr sin pasar por el pipeline.

        Este es el camino que se olvida: sin la llamada explícita en el
        router, un punto cargado a mano no aparecía en la gráfica hasta
        que caducara el TTL.
        """
        sede, ubicacion, dispositivo, parametro = _montar_sede(
            db_session, fabrica, "Carga manual", 1.0, "Temp HT10"
        )

        # La carga manual solo acepta parámetros mapeados para la trama H.
        formato = MapeoFormato(
            id_dspstv=dispositivo.id_dspstv, frmt_fch="%Y-%m-%d %H:%M:%S", tp_trm="H", estd="Activo"
        )
        db_session.add(formato)
        db_session.flush()
        db_session.add(
            MapeoColumna(id_mp=formato.id_mp, id_prmtr=parametro.id_prmtr, indc_clmn=1)
        )
        db_session.flush()

        rol = fabrica.rol("Administrador")
        usuario = fabrica.usuario(rol=rol, scp="por_sede")
        agregar_permiso(db_session, usuario, sede, "Dispositivos", "Edición", rol)
        asignar_ubicacion(db_session, usuario, ubicacion)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, "Administrador", sede_id=sede.id_sd
        )

        clave = cache.clave("mediciones", f"sd{sede.id_sd}:test")
        cache.guardar(
            clave,
            {"items": []},
            indices=[cache.indice_de_sede(sede.id_sd), cache.indice_de_ubicacion(ubicacion.id_ubccn)],
        )
        assert cache.obtener(clave) is not None

        respuesta = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-manual",
            json={
                "fch_hr": dt.datetime.now(dt.timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "valores": [{"id_prmtr": parametro.id_prmtr, "vlr": 33.3}],
            },
        )
        assert respuesta.status_code == 201, respuesta.text
        assert cache.obtener(clave) is None, (
            "CA2: la carga manual también debe invalidar la caché de su sede/ubicación"
        )


# ---------------------------------------------------------------------
# CA3 - downsampling sobre el endpoint real
# ---------------------------------------------------------------------


@requiere_redis
class TestCA3DownsamplingEndpoint:
    def test_rango_amplio_aplica_downsampling_con_maximo_configurable(
        self, client, db_session, fabrica
    ):
        """Rango de 60 días con más puntos que el máximo pedido: la
        respuesta se muestrea y lo declara."""
        sede, ubicacion, dispositivo, parametro = _montar_sede(
            db_session, fabrica, "Downsampling", 1.0, "Temp HT10"
        )
        usuario = _usuario_de_sede(db_session, fabrica, sede, ubicacion, ["Tableros"])
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, "Cliente Final", sede_id=sede.id_sd
        )

        ahora = dt.datetime.now(dt.timezone.utc)
        for minutos in range(0, 60 * 24, 30):
            db_session.add(
                Telemetria(
                    fch_hr=ahora - dt.timedelta(minutes=minutos),
                    id_dspstv=dispositivo.id_dspstv,
                    id_prmtr=parametro.id_prmtr,
                    id_sd=sede.id_sd,
                    vlr=minutos,
                )
            )
        db_session.flush()

        cuerpo = client.get(
            "/mediciones",
            params={
                "fecha_inicio": (ahora - dt.timedelta(days=60)).isoformat(),
                "fecha_fin": ahora.isoformat(),
                "max_puntos": 10,
                "por_pagina": 500,
            },
        ).json()

        assert cuerpo["downsampling"] is True
        assert cuerpo["total"] <= 10
        assert cuerpo["total_sin_muestrear"] > 10

    def test_rango_corto_no_aplica_downsampling(self, client, db_session, fabrica):
        """CA1/CA3: hasta 7 días se devuelve la serie completa, sin
        muestrear -el downsampling es solo para rangos amplios-."""
        sede, ubicacion, dispositivo, parametro = _montar_sede(
            db_session, fabrica, "Sin downsampling", 1.0, "Temp HT10"
        )
        usuario = _usuario_de_sede(db_session, fabrica, sede, ubicacion, ["Tableros"])
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, "Cliente Final", sede_id=sede.id_sd
        )

        ahora = dt.datetime.now(dt.timezone.utc)
        for horas in range(0, 24 * 5, 6):
            db_session.add(
                Telemetria(
                    fch_hr=ahora - dt.timedelta(hours=horas),
                    id_dspstv=dispositivo.id_dspstv,
                    id_prmtr=parametro.id_prmtr,
                    id_sd=sede.id_sd,
                    vlr=horas,
                )
            )
        db_session.flush()

        cuerpo = client.get(
            "/mediciones",
            params={
                "fecha_inicio": (ahora - dt.timedelta(days=7)).isoformat(),
                "fecha_fin": ahora.isoformat(),
                "max_puntos": 5,
                "por_pagina": 500,
            },
        ).json()

        assert cuerpo["downsampling"] is False
        assert cuerpo["total"] == cuerpo["total_sin_muestrear"]


@requiere_redis
class TestFiltroDeFechaHU12:
    """HT-10 punto 4: el rango de fechas ahora se aplica en SQL.

    Se documentaba en HU12 y el endpoint recibía los parámetros, pero no
    llegaban a la consulta. Este test fija el comportamiento para que no
    vuelva a perderse.
    """

    def test_las_lecturas_fuera_del_rango_no_se_devuelven(self, client, db_session, fabrica):
        sede, ubicacion, dispositivo, parametro = _montar_sede(
            db_session, fabrica, "Filtro fecha", 1.0, "Temp HT10"
        )
        usuario = _usuario_de_sede(db_session, fabrica, sede, ubicacion, ["Tableros"])
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, "Cliente Final", sede_id=sede.id_sd
        )

        ahora = dt.datetime.now(dt.timezone.utc)
        db_session.add(
            Telemetria(
                fch_hr=ahora - dt.timedelta(days=20),
                id_dspstv=dispositivo.id_dspstv,
                id_prmtr=parametro.id_prmtr,
                id_sd=sede.id_sd,
                vlr=555.0,
            )
        )
        db_session.flush()

        cuerpo = client.get(
            "/mediciones",
            params={
                "fecha_inicio": (ahora - dt.timedelta(days=2)).isoformat(),
                "fecha_fin": ahora.isoformat(),
                "por_pagina": 500,
            },
        ).json()

        assert 555.0 not in {item["vlr"] for item in cuerpo["items"]}
