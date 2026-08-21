"""
HU06 - Mapear formato de marca de sensor: tests de los endpoints del CRUD
y de la vista previa.

DEC-09: el mapeo se identifica por DISPOSITIVO + tipo de trama, no por
sede + marca. Cada dispositivo se crea con su propia Ubicacion/ConexionFTP
(mismo patrón que test_dispositivos.py); marca y sede se derivan del
dispositivo, no se mandan en el body.

Corren contra la Postgres real de test (ver tests/conftest.py). La vista
previa usa los .dat que ya existen en tests/fixtures/, que son tramas
reales de campo: el de calidad de agua trae un header con unidades
pegadas al nombre y comillas en los valores, que es justo el caso que el
mapeo por índice (mp_clmn.indc_clmn) existe para resolver.
"""

import pathlib

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import ConexionFTP, Dispositivo, Ubicacion
from app.models.mapeo_dispositivo import MapeoColumna, MapeoFormato, Parametro
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
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


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def tecnico_editor(db_session, fabrica):
    """Técnico CENERIS con permiso de Edición sobre Ingesta en su sede,
    ya autenticado. Devuelve (sede, rol) para los tests que los necesiten."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Ingesta", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return sede, rol


@pytest.fixture()
def parametros(db_session):
    creados = []
    for nombre, unidad in [
        ("Temperatura HU06", "°C"),
        ("pH HU06", "pH"),
        ("Conductividad HU06", "uS/cm"),
    ]:
        parametro = Parametro(nmbr=nombre, undd=unidad, dscrpcn="parámetro creado por los tests")
        db_session.add(parametro)
        creados.append(parametro)
    db_session.flush()
    return creados


def crear_dispositivo(db_session, sede, nombre="CR1000 HU06", marca="Campbell HU06"):
    """DEC-09: el mapeo cuelga de un dispositivo. Cadena mínima
    (Ubicacion + ConexionFTP + Dispositivo) para tener uno."""
    ubicacion = Ubicacion(
        id_sd=sede.id_sd,
        nmbr=f"Ubicacion de {nombre}",
        lttd=0,
        lngtd=0,
        plgn_gjsn=POLIGONO_DUMMY,
    )
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=f"Conexion de {nombre}",
        hst="127.0.0.1",
        usr_ftp="usr",
        rt_rmt="/data",
        crdncl_cfrd="cifrado-de-prueba",
    )
    db_session.add_all([ubicacion, conexion])
    db_session.flush()

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=nombre,
        mrc=marca,
        lttd=0,
        lngtd=0,
    )
    db_session.add(dispositivo)
    db_session.flush()
    return dispositivo


def cuerpo_mapeo(parametros, id_dspstv, tp_trm="H", **overrides):
    cuerpo = {
        "id_dspstv": id_dspstv,
        "tp_trm": tp_trm,
        "dlmtdr": ",",
        "fl_inc_dts": 1,
        "frmt_fch": "YYYY-MM-DD HH:mm:ss",
        "columnas": [
            {"indc_clmn": 9, "id_prmtr": parametros[0].id_prmtr},
            {"indc_clmn": 16, "id_prmtr": parametros[1].id_prmtr},
        ],
    }
    cuerpo.update(overrides)
    return cuerpo


class TestListarParametros:
    """CA1: el selector de parámetro estándar del formulario."""

    def test_devuelve_los_parametros(self, client, tecnico_editor, parametros):
        resp = client.get("/parametros")
        assert resp.status_code == 200
        nombres = [p["nmbr"] for p in resp.json()]
        assert "Temperatura HU06" in nombres

    def test_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        assert client.get("/parametros").status_code == 403


class TestCrearMapeo:
    """CA3: 'GUARDAR' registra el mapeo y lo asocia al dispositivo."""

    def test_crea_y_devuelve_el_mensaje_de_la_hu(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)

        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv))
        assert resp.status_code == 201
        assert resp.json()["mensaje"] == "Mapeo guardado correctamente"

        mapeo = resp.json()["mapeo"]
        assert mapeo["id_dspstv"] == dispositivo.id_dspstv
        assert mapeo["dispositivo_nombre"] == dispositivo.nmbr
        # Marca y sede se derivan del dispositivo, no se mandaron en el body.
        assert mapeo["mrc"] == "Campbell HU06"
        assert mapeo["id_sd"] == sede.id_sd
        assert mapeo["total_columnas"] == 2
        # El formato de fecha vuelve en el lenguaje de la HU, no en strptime.
        assert mapeo["frmt_fch"] == "YYYY-MM-DD HH:mm:ss"
        # DEC-09: por defecto el separador decimal es punto, que es el
        # comportamiento que tenía el motor antes de que fuera configurable.
        assert mapeo["dlmtdr_dcml"] == "."

    def test_crear_con_columna_y_decimal_ambos_coma_devuelve_422(
        self, client, db_session, tecnico_editor, parametros
    ):
        """ "23,5" en una línea separada por comas son dos campos, no un
        número: se rechaza al guardar en vez de producir lecturas partidas
        en silencio."""
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)

        resp = client.post(
            "/mapeos",
            json=cuerpo_mapeo(
                parametros,
                dispositivo.id_dspstv,
                dlmtdr=",",
                dlmtdr_dcml=",",
            ),
        )
        assert resp.status_code == 422
        assert "ambos coma" in resp.json()["detail"]

    def test_delimitador_decimal_invalido_devuelve_422(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)

        resp = client.post(
            "/mapeos",
            json=cuerpo_mapeo(parametros, dispositivo.id_dspstv, dlmtdr_dcml="|"),
        )
        assert resp.status_code == 422

    def test_guarda_el_formato_de_fecha_como_strptime(
        self, client, db_session, tecnico_editor, parametros
    ):
        # El motor (parser._parsear_fecha) usa strptime: lo que se persiste
        # tiene que ser directamente consumible por resolver_formato().
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv))
        id_mp = resp.json()["mapeo"]["id_mp"]

        formato = db_session.query(MapeoFormato).filter(MapeoFormato.id_mp == id_mp).first()
        assert formato.frmt_fch == "%Y-%m-%d %H:%M:%S"
        assert formato.id_dspstv == dispositivo.id_dspstv

    def test_crea_las_filas_de_mp_clmn(self, client, db_session, tecnico_editor, parametros):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv))
        id_mp = resp.json()["mapeo"]["id_mp"]

        columnas = db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == id_mp).all()
        assert sorted(c.indc_clmn for c in columnas) == [9, 16]

    def test_duplicado_para_el_mismo_dispositivo_y_trama_devuelve_409(
        self, client, db_session, tecnico_editor, parametros
    ):
        # Único parcial (id_dspstv, tp_trm) WHERE estd='Activo'.
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)

        assert (
            client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).status_code
            == 201
        )
        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv))
        assert resp.status_code == 409
        assert "ya tiene un mapeo activo" in resp.json()["detail"].lower()

    def test_mismo_dispositivo_distinto_tipo_de_trama_si_se_permite(
        self, client, db_session, tecnico_editor, parametros
    ):
        # Un datalogger manda H_ y E_ con distinto formato: el único parcial
        # incluye tp_trm justamente para poder guardar ambos.
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)

        assert (
            client.post(
                "/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv, tp_trm="H")
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv, tp_trm="E")
            ).status_code
            == 201
        )

    def test_misma_marca_y_sede_dispositivos_distintos_no_chocan(
        self, client, db_session, tecnico_editor, parametros
    ):
        """No es un duplicado: son dispositivos distintos, aunque compartan
        marca y sede. Esto es justamente lo que DEC-09 debía permitir."""
        sede, _ = tecnico_editor
        disp_a = crear_dispositivo(db_session, sede, nombre="CR1000-A", marca="Campbell HU06")
        disp_b = crear_dispositivo(db_session, sede, nombre="CR1000-B", marca="Campbell HU06")

        assert (
            client.post("/mapeos", json=cuerpo_mapeo(parametros, disp_a.id_dspstv)).status_code
            == 201
        )
        assert (
            client.post("/mapeos", json=cuerpo_mapeo(parametros, disp_b.id_dspstv)).status_code
            == 201
        )

    def test_dispositivo_inexistente_devuelve_422(self, client, tecnico_editor, parametros):
        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros, 999999))
        assert resp.status_code == 422

    def test_delimitador_invalido_devuelve_422(
        self, client, db_session, tecnico_editor, parametros
    ):
        # Regla de negocio: solo coma, punto y coma, tabulador o espacio.
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        resp = client.post(
            "/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv, dlmtdr="|")
        )
        assert resp.status_code == 422

    def test_tipo_de_trama_ya_no_es_un_catalogo_cerrado(
        self, client, db_session, tecnico_editor, parametros
    ):
        """El tipo de trama es una letra libre (A-Z) que el técnico de
        telemetría define al crear el mapeo, no un catálogo fijo H/E/P:
        una letra fuera de ese catálogo histórico debe aceptarse igual."""
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        resp = client.post(
            "/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv, tp_trm="X")
        )
        assert resp.status_code == 201
        assert resp.json()["mapeo"]["tp_trm"] == "X"

    def test_tipo_de_trama_se_normaliza_a_mayuscula(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        resp = client.post(
            "/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv, tp_trm="x")
        )
        assert resp.status_code == 201
        assert resp.json()["mapeo"]["tp_trm"] == "X"

    def test_tipo_de_trama_vacio_devuelve_422(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        resp = client.post(
            "/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv, tp_trm="")
        )
        assert resp.status_code == 422

    def test_tipo_de_trama_de_mas_de_una_letra_devuelve_422(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        resp = client.post(
            "/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv, tp_trm="HE")
        )
        assert resp.status_code == 422

    def test_tipo_de_trama_no_alfabetico_devuelve_422(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        resp = client.post(
            "/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv, tp_trm="1")
        )
        assert resp.status_code == 422

    def test_parametro_inexistente_devuelve_422(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        cuerpo = cuerpo_mapeo(
            parametros, dispositivo.id_dspstv, columnas=[{"indc_clmn": 0, "id_prmtr": 999999}]
        )
        resp = client.post("/mapeos", json=cuerpo)
        assert resp.status_code == 422
        assert "no existen" in resp.json()["detail"]

    def test_dos_parametros_en_el_mismo_indice_devuelve_422(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        cuerpo = cuerpo_mapeo(
            parametros,
            dispositivo.id_dspstv,
            columnas=[
                {"indc_clmn": 3, "id_prmtr": parametros[0].id_prmtr},
                {"indc_clmn": 3, "id_prmtr": parametros[1].id_prmtr},
            ],
        )
        assert client.post("/mapeos", json=cuerpo).status_code == 422

    def test_usuario_por_sede_no_crea_mapeo_para_dispositivo_de_otra_sede(
        self, client, db_session, tecnico_editor, fabrica, parametros
    ):
        """HT-09 CA3: verificar_sede() bloquea aunque el usuario conozca el
        id_dspstv de un dispositivo de otra sede."""
        otra_sede = fabrica.sede()
        dispositivo_ajeno = crear_dispositivo(db_session, otra_sede)

        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo_ajeno.id_dspstv))
        assert resp.status_code == 403

    def test_denegado_con_permiso_de_solo_lectura(self, client, db_session, fabrica, parametros):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Ingesta", "Lectura", rol)
        dispositivo = crear_dispositivo(db_session, sede)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv))
        assert resp.status_code == 403


class TestBugDEC09ResuelveElMapeoDelDispositivoCorrecto:
    """DEC-09 - regresión del bug que motivó el cambio.

    Antes: mp_frmt se identificaba por (id_sd, mrc, tp_trm). Dos
    dataloggers de la MISMA marca en la MISMA sede, con sensores distintos
    conectados, compartían el mismo mapeo -las lecturas del segundo se
    guardaban bajo el parámetro equivocado, sin ningún error visible-.

    Ahora: cada dispositivo tiene su propio mapeo, aunque compartan marca y
    sede. Este test arma exactamente ese escenario -2 dispositivos, misma
    marca, misma sede, columnas distintas para el mismo tp_trm- y verifica
    que resolver_formato() (el motor de ingesta) resuelve el mapeo de CADA
    dispositivo, no el del otro.
    """

    def test_cada_dispositivo_resuelve_su_propio_mapeo_no_el_del_otro(self, db_session, fabrica):
        from app.services.ingesta.mapeo import resolver_formato

        sede = fabrica.sede()
        parametro_temperatura = Parametro(nmbr="Temperatura DEC-09", undd="°C")
        parametro_ph = Parametro(nmbr="pH DEC-09", undd="pH")
        db_session.add_all([parametro_temperatura, parametro_ph])
        db_session.flush()

        # Dos dataloggers de la MISMA marca, en la MISMA sede: exactamente
        # el escenario del bug.
        disp_a = crear_dispositivo(db_session, sede, nombre="CR1000-Sensor-Temp", marca="Campbell")
        disp_b = crear_dispositivo(db_session, sede, nombre="CR1000-Sensor-pH", marca="Campbell")

        mapeo_a = MapeoFormato(
            id_dspstv=disp_a.id_dspstv,
            tp_trm="H",
            dlmtdr=",",
            fl_inc_dts=1,
            frmt_fch="%Y-%m-%d %H:%M:%S",
        )
        mapeo_b = MapeoFormato(
            id_dspstv=disp_b.id_dspstv,
            tp_trm="H",
            dlmtdr=";",
            fl_inc_dts=2,
            frmt_fch="%d/%m/%Y",
        )
        db_session.add_all([mapeo_a, mapeo_b])
        db_session.flush()

        db_session.add_all(
            [
                MapeoColumna(
                    id_mp=mapeo_a.id_mp, indc_clmn=1, id_prmtr=parametro_temperatura.id_prmtr
                ),
                MapeoColumna(id_mp=mapeo_b.id_mp, indc_clmn=1, id_prmtr=parametro_ph.id_prmtr),
            ]
        )
        db_session.flush()

        resuelto_a = resolver_formato(db_session, disp_a.id_dspstv, "H_datos.dat")
        resuelto_b = resolver_formato(db_session, disp_b.id_dspstv, "H_datos.dat")

        # Cada dispositivo resuelve SU mapeo, con SU configuración de parseo.
        assert resuelto_a.id_mp == mapeo_a.id_mp
        assert resuelto_a.config.delimitador == ","
        assert resuelto_b.id_mp == mapeo_b.id_mp
        assert resuelto_b.config.delimitador == ";"
        assert resuelto_a.id_mp != resuelto_b.id_mp

        # Y la columna 1 se traduce a un parámetro DISTINTO según el
        # dispositivo: esto es lo que antes se mezclaba en silencio.
        from app.services.ingesta.mapeo import construir_mapeo

        columnas_header = ["Fecha", "Valor"]
        mapa_a = construir_mapeo(db_session, resuelto_a.id_mp, columnas_header)
        mapa_b = construir_mapeo(db_session, resuelto_b.id_mp, columnas_header)
        assert mapa_a["Valor"] == "Temperatura DEC-09"
        assert mapa_b["Valor"] == "pH DEC-09"


class TestListarYObtenerMapeos:
    """CA5 (listado) y CA4 (detalle al abrir uno existente)."""

    def test_el_mapeo_nuevo_aparece_asociado_a_su_dispositivo(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede, nombre="Dispositivo Listado")
        client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv))

        resp = client.get("/mapeos")
        assert resp.status_code == 200
        nombres = [m["dispositivo_nombre"] for m in resp.json()["items"]]
        assert "Dispositivo Listado" in nombres

    def test_filtro_por_marca(self, client, db_session, tecnico_editor, parametros):
        sede, _ = tecnico_editor
        disp_a = crear_dispositivo(db_session, sede, nombre="Disp Marca A", marca="Marca A")
        disp_b = crear_dispositivo(db_session, sede, nombre="Disp Marca B", marca="Marca B")
        client.post("/mapeos", json=cuerpo_mapeo(parametros, disp_a.id_dspstv))
        client.post("/mapeos", json=cuerpo_mapeo(parametros, disp_b.id_dspstv))

        resp = client.get("/mapeos", params={"marca": "Marca A"})
        assert [m["mrc"] for m in resp.json()["items"]] == ["Marca A"]

    def test_filtro_por_dispositivo(self, client, db_session, tecnico_editor, parametros):
        sede, _ = tecnico_editor
        disp_a = crear_dispositivo(db_session, sede, nombre="Disp Filtro A")
        disp_b = crear_dispositivo(db_session, sede, nombre="Disp Filtro B")
        client.post("/mapeos", json=cuerpo_mapeo(parametros, disp_a.id_dspstv))
        client.post("/mapeos", json=cuerpo_mapeo(parametros, disp_b.id_dspstv))

        resp = client.get("/mapeos", params={"id_dspstv": disp_a.id_dspstv})
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["id_dspstv"] == disp_a.id_dspstv

    def test_detalle_incluye_la_tabla_de_asignacion(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).json()[
            "mapeo"
        ]["id_mp"]

        resp = client.get(f"/mapeos/{id_mp}")
        assert resp.status_code == 200
        columnas = resp.json()["columnas"]
        assert [c["indc_clmn"] for c in columnas] == [9, 16]
        # El nombre del parámetro viene resuelto para no obligar al frontend
        # a cruzar contra GET /parametros.
        assert columnas[0]["parametro_nombre"] == "Temperatura HU06"

    def test_mapeo_inexistente_devuelve_404(self, client, tecnico_editor):
        assert client.get("/mapeos/999999").status_code == 404

    def test_usuario_de_otra_sede_no_ve_el_mapeo(
        self, client, db_session, tecnico_editor, fabrica, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).json()[
            "mapeo"
        ]["id_mp"]

        # HT-09 CA3: otro usuario, con permiso propio pero en otra sede.
        otro_rol = fabrica.rol("Administrador")
        otra_sede = fabrica.sede()
        otro_usuario = fabrica.usuario(rol=otro_rol)
        agregar_permiso(db_session, otro_usuario, otra_sede, "Ingesta", "Edición", otro_rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro_usuario, otro_rol.nmbr, sede_id=otra_sede.id_sd
        )

        assert client.get(f"/mapeos/{id_mp}").status_code == 403
        assert [m["id_mp"] for m in client.get("/mapeos").json()["items"]] == []


class TestActualizarMapeo:
    """CA4: modifica un campo, actualiza, y devuelve el mensaje."""

    def test_actualiza_un_campo_y_devuelve_el_mensaje_de_la_hu(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).json()[
            "mapeo"
        ]["id_mp"]

        resp = client.put(f"/mapeos/{id_mp}", json={"dlmtdr": ";"})
        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "Mapeo actualizado correctamente"
        assert resp.json()["mapeo"]["dlmtdr"] == ";"

    def test_omitir_columnas_conserva_la_asignacion(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).json()[
            "mapeo"
        ]["id_mp"]

        client.put(f"/mapeos/{id_mp}", json={"fl_inc_dts": 2})

        columnas = db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == id_mp).all()
        assert len(columnas) == 2

    def test_enviar_columnas_reemplaza_la_asignacion(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).json()[
            "mapeo"
        ]["id_mp"]

        resp = client.put(
            f"/mapeos/{id_mp}",
            json={"columnas": [{"indc_clmn": 4, "id_prmtr": parametros[2].id_prmtr}]},
        )
        assert resp.status_code == 200

        columnas = db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == id_mp).all()
        assert [c.indc_clmn for c in columnas] == [4]

    def test_delimitador_invalido_devuelve_422(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).json()[
            "mapeo"
        ]["id_mp"]
        assert client.put(f"/mapeos/{id_mp}", json={"dlmtdr": "|"}).status_code == 422

    def test_mapeo_inexistente_devuelve_404(self, client, tecnico_editor):
        assert client.put("/mapeos/999999", json={"dlmtdr": ";"}).status_code == 404

    def test_cambiar_solo_el_decimal_a_coma_choca_con_la_coma_de_columna(
        self, client, db_session, tecnico_editor, parametros
    ):
        """DEC-09: el conflicto se evalúa contra el valor ya guardado, no
        solo contra el body. El mapeo se creó con ',' de columna, así que
        pasar el decimal a ',' lo deja indecidible."""
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).json()[
            "mapeo"
        ]["id_mp"]

        resp = client.put(f"/mapeos/{id_mp}", json={"dlmtdr_dcml": ","})
        assert resp.status_code == 422
        assert "ambos coma" in resp.json()["detail"]

    def test_decimal_coma_con_columna_punto_y_coma_se_acepta(
        self, client, db_session, tecnico_editor, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).json()[
            "mapeo"
        ]["id_mp"]

        resp = client.put(f"/mapeos/{id_mp}", json={"dlmtdr": ";", "dlmtdr_dcml": ","})
        assert resp.status_code == 200
        assert resp.json()["mapeo"]["dlmtdr_dcml"] == ","

    def test_denegado_con_permiso_de_solo_lectura(
        self, client, db_session, tecnico_editor, fabrica, parametros
    ):
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dispositivo.id_dspstv)).json()[
            "mapeo"
        ]["id_mp"]

        rol_lector = fabrica.rol("Cliente Final")
        lector = fabrica.usuario(rol=rol_lector)
        agregar_permiso(db_session, lector, sede, "Ingesta", "Lectura", rol_lector)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            lector, rol_lector.nmbr, sede_id=sede.id_sd
        )

        assert client.put(f"/mapeos/{id_mp}", json={"dlmtdr": ";"}).status_code == 403


class TestVistaPrevia:
    """CA2: primeras 10 filas interpretadas, sin persistir el archivo."""

    def _subir(self, client, nombre_fixture, **campos):
        contenido = (FIXTURES / nombre_fixture).read_bytes()
        datos = {"dlmtdr": ",", "fl_inc_dts": "1", "frmt_fch": "YYYY-MM-DD HH:mm:ss"}
        datos.update({k: str(v) for k, v in campos.items()})
        return client.post(
            "/mapeos/vista-previa",
            files={"archivo": (nombre_fixture, contenido, "text/plain")},
            data=datos,
        )

    def test_devuelve_las_columnas_del_header(self, client, tecnico_editor):
        resp = self._subir(client, "ejemplo_estado_gabinete.dat")
        assert resp.status_code == 200

        columnas = resp.json()["columnas"]
        assert columnas[0]["nombre_columna"] == "Fecha"
        assert columnas[2]["nombre_columna"] == "Estado_Gabinete"

    def test_muestra_como_maximo_10_filas(self, client, tecnico_editor):
        resp = self._subir(client, "ejemplo_calidad_agua.dat")
        assert resp.status_code == 200
        assert resp.json()["filas_mostradas"] <= 10

    def test_interpreta_la_fecha_de_cada_fila(self, client, tecnico_editor):
        resp = self._subir(client, "ejemplo_estado_gabinete.dat")
        filas = resp.json()["filas"]
        assert filas, "el fixture debería producir al menos una fila"
        assert filas[0]["fecha_hora"] is not None
        assert filas[0]["error"] is None

    def test_asigna_el_parametro_estandar_a_la_columna(self, client, tecnico_editor, parametros):
        resp = self._subir(
            client,
            "ejemplo_estado_gabinete.dat",
            asignaciones=f"2:{parametros[0].id_prmtr}",
        )
        columnas = resp.json()["columnas"]
        assert columnas[2]["parametro_nombre"] == "Temperatura HU06"
        assert columnas[2]["parametro_unidad"] == "°C"
        # Las columnas sin asignar quedan explícitamente sin parámetro.
        assert columnas[1]["parametro_nombre"] is None

    def test_acepta_id_dspstv_opcional_sin_que_afecte_el_resultado(
        self, client, db_session, tecnico_editor
    ):
        """DEC-09: se manda por consistencia con el resto del formulario,
        pero la vista previa no lo necesita para interpretar el archivo."""
        sede, _ = tecnico_editor
        dispositivo = crear_dispositivo(db_session, sede)

        resp = self._subir(client, "ejemplo_estado_gabinete.dat", id_dspstv=dispositivo.id_dspstv)
        assert resp.status_code == 200
        assert resp.json()["columnas"][0]["nombre_columna"] == "Fecha"

    def test_no_persiste_nada(self, client, db_session, tecnico_editor):
        # Regla explícita de la HU: el archivo de muestra es temporal.
        formatos_antes = db_session.query(MapeoFormato).count()
        columnas_antes = db_session.query(MapeoColumna).count()

        self._subir(client, "ejemplo_calidad_agua.dat")

        assert db_session.query(MapeoFormato).count() == formatos_antes
        assert db_session.query(MapeoColumna).count() == columnas_antes

    def test_delimitador_equivocado_marca_error_en_cada_fila(self, client, tecnico_editor):
        # Con ';' sobre un archivo separado por comas el header queda de una
        # sola columna, así que no se ubica la fecha. La vista previa se
        # devuelve igual (200) pero con el error visible fila por fila: es
        # justo la señal que el usuario necesita para corregir el
        # delimitador antes de guardar.
        resp = self._subir(client, "ejemplo_estado_gabinete.dat", dlmtdr=";")
        assert resp.status_code == 200
        assert all(fila["error"] for fila in resp.json()["filas"])

    def test_delimitador_no_permitido_devuelve_422(self, client, tecnico_editor):
        assert self._subir(client, "ejemplo_estado_gabinete.dat", dlmtdr="|").status_code == 422

    def test_archivo_real_con_crlf_no_revienta(self, client, tecnico_editor):
        # Regresión: un .dat real de datalogger (CRLF + NUL de relleno al
        # final) hacía que parsear_dat() reventara con
        # "_csv.Error: new-line character seen in unquoted field" en vez de
        # devolver la vista previa -los fixtures preexistentes usan LF y no
        # lo detectaban-. Ver el fix en vista_previa() (normaliza saltos de
        # línea antes de llamar al parser) y el hallazgo en el README.
        resp = self._subir(client, "H_ejemplo_crlf_real.dat")
        assert resp.status_code == 200

        body = resp.json()
        assert body["filas_mostradas"] == 1
        assert body["filas"][0]["error"] is None
        assert body["filas"][0]["fecha_hora"] == "2026-06-08T14:35:00"
        assert len(body["columnas"]) == 23

    def test_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        assert self._subir(client, "ejemplo_estado_gabinete.dat").status_code == 403
