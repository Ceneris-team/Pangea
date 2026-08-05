"""
HU06 - Mapear formato de marca de sensor: tests de los endpoints del CRUD
y de la vista previa.

Corren contra la Postgres real de test (ver tests/conftest.py). La vista
previa usa los .dat que ya existen en tests/fixtures/, que son tramas
reales de campo: el de calidad de agua trae un header con unidades
pegadas al nombre y comillas en los valores, que es justo el caso que el
mapeo por índice (mp_clmn.indc_clmn) existe para resolver.
"""
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.security.dependencies import get_current_user
from app.models.mapeo_dispositivo import MapeoColumna, MapeoFormato, Parametro
from app.models.suscripcion import PermisoUsuarioSede

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"


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
    for nombre, unidad in [("Temperatura HU06", "°C"), ("pH HU06", "pH"), ("Conductividad HU06", "uS/cm")]:
        parametro = Parametro(nmbr=nombre, undd=unidad, dscrpcn="parámetro creado por los tests")
        db_session.add(parametro)
        creados.append(parametro)
    db_session.flush()
    return creados


def cuerpo_mapeo(parametros, marca="Campbell HU06", tp_trm="H", **overrides):
    cuerpo = {
        "mrc": marca,
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
    """CA3: 'GUARDAR' registra el mapeo y lo asocia a la marca."""

    def test_crea_y_devuelve_el_mensaje_de_la_hu(self, client, db_session, tecnico_editor, parametros):
        sede, _ = tecnico_editor

        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros))
        assert resp.status_code == 201
        assert resp.json()["mensaje"] == "Mapeo guardado correctamente"

        mapeo = resp.json()["mapeo"]
        assert mapeo["mrc"] == "Campbell HU06"
        assert mapeo["id_sd"] == sede.id_sd
        assert mapeo["total_columnas"] == 2
        # El formato de fecha vuelve en el lenguaje de la HU, no en strptime.
        assert mapeo["frmt_fch"] == "YYYY-MM-DD HH:mm:ss"

    def test_guarda_el_formato_de_fecha_como_strptime(self, client, db_session, tecnico_editor, parametros):
        # El motor (parser._parsear_fecha) usa strptime: lo que se persiste
        # tiene que ser directamente consumible por resolver_formato().
        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros))
        id_mp = resp.json()["mapeo"]["id_mp"]

        formato = db_session.query(MapeoFormato).filter(MapeoFormato.id_mp == id_mp).first()
        assert formato.frmt_fch == "%Y-%m-%d %H:%M:%S"

    def test_crea_las_filas_de_mp_clmn(self, client, db_session, tecnico_editor, parametros):
        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros))
        id_mp = resp.json()["mapeo"]["id_mp"]

        columnas = db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == id_mp).all()
        assert sorted(c.indc_clmn for c in columnas) == [9, 16]

    def test_duplicado_devuelve_409(self, client, db_session, tecnico_editor, parametros):
        # Clave única (id_sd, mrc, tp_trm).
        assert client.post("/mapeos", json=cuerpo_mapeo(parametros)).status_code == 201
        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros))
        assert resp.status_code == 409
        assert "Ya existe un mapeo" in resp.json()["detail"]

    def test_misma_marca_distinto_tipo_de_trama_si_se_permite(self, client, tecnico_editor, parametros):
        # Un datalogger manda H_ y E_ con distinto formato: la clave única
        # incluye tp_trm justamente para poder guardar ambos.
        assert client.post("/mapeos", json=cuerpo_mapeo(parametros, tp_trm="H")).status_code == 201
        assert client.post("/mapeos", json=cuerpo_mapeo(parametros, tp_trm="E")).status_code == 201

    def test_delimitador_invalido_devuelve_422(self, client, tecnico_editor, parametros):
        # Regla de negocio: solo coma, punto y coma, tabulador o espacio.
        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros, dlmtdr="|"))
        assert resp.status_code == 422

    def test_tipo_de_trama_invalido_devuelve_422(self, client, tecnico_editor, parametros):
        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros, tp_trm="X"))
        assert resp.status_code == 422

    def test_parametro_inexistente_devuelve_422(self, client, tecnico_editor, parametros):
        cuerpo = cuerpo_mapeo(parametros, columnas=[{"indc_clmn": 0, "id_prmtr": 999999}])
        resp = client.post("/mapeos", json=cuerpo)
        assert resp.status_code == 422
        assert "no existen" in resp.json()["detail"]

    def test_dos_parametros_en_el_mismo_indice_devuelve_422(self, client, tecnico_editor, parametros):
        cuerpo = cuerpo_mapeo(
            parametros,
            columnas=[
                {"indc_clmn": 3, "id_prmtr": parametros[0].id_prmtr},
                {"indc_clmn": 3, "id_prmtr": parametros[1].id_prmtr},
            ],
        )
        assert client.post("/mapeos", json=cuerpo).status_code == 422

    def test_denegado_con_permiso_de_solo_lectura(self, client, db_session, fabrica, parametros):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Ingesta", "Lectura", rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.post("/mapeos", json=cuerpo_mapeo(parametros))
        assert resp.status_code == 403


class TestListarYObtenerMapeos:
    """CA5 (listado) y CA4 (detalle al abrir uno existente)."""

    def test_el_mapeo_nuevo_aparece_asociado_a_su_marca(self, client, tecnico_editor, parametros):
        client.post("/mapeos", json=cuerpo_mapeo(parametros, marca="Marca Listada"))

        resp = client.get("/mapeos")
        assert resp.status_code == 200
        marcas = [m["mrc"] for m in resp.json()["items"]]
        assert "Marca Listada" in marcas

    def test_filtro_por_marca(self, client, tecnico_editor, parametros):
        client.post("/mapeos", json=cuerpo_mapeo(parametros, marca="Marca A"))
        client.post("/mapeos", json=cuerpo_mapeo(parametros, marca="Marca B"))

        resp = client.get("/mapeos", params={"marca": "Marca A"})
        assert [m["mrc"] for m in resp.json()["items"]] == ["Marca A"]

    def test_detalle_incluye_la_tabla_de_asignacion(self, client, tecnico_editor, parametros):
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros)).json()["mapeo"]["id_mp"]

        resp = client.get(f"/mapeos/{id_mp}")
        assert resp.status_code == 200
        columnas = resp.json()["columnas"]
        assert [c["indc_clmn"] for c in columnas] == [9, 16]
        # El nombre del parámetro viene resuelto para no obligar al frontend
        # a cruzar contra GET /parametros.
        assert columnas[0]["parametro_nombre"] == "Temperatura HU06"

    def test_mapeo_inexistente_devuelve_404(self, client, tecnico_editor):
        assert client.get("/mapeos/999999").status_code == 404

    def test_usuario_de_otra_sede_no_ve_el_mapeo(self, client, db_session, tecnico_editor, fabrica, parametros):
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros)).json()["mapeo"]["id_mp"]

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

    def test_actualiza_un_campo_y_devuelve_el_mensaje_de_la_hu(self, client, tecnico_editor, parametros):
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros)).json()["mapeo"]["id_mp"]

        resp = client.put(f"/mapeos/{id_mp}", json={"dlmtdr": ";"})
        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "Mapeo actualizado correctamente"
        assert resp.json()["mapeo"]["dlmtdr"] == ";"

    def test_omitir_columnas_conserva_la_asignacion(self, client, db_session, tecnico_editor, parametros):
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros)).json()["mapeo"]["id_mp"]

        client.put(f"/mapeos/{id_mp}", json={"mrc": "Marca Renombrada"})

        columnas = db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == id_mp).all()
        assert len(columnas) == 2

    def test_enviar_columnas_reemplaza_la_asignacion(self, client, db_session, tecnico_editor, parametros):
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros)).json()["mapeo"]["id_mp"]

        resp = client.put(
            f"/mapeos/{id_mp}",
            json={"columnas": [{"indc_clmn": 4, "id_prmtr": parametros[2].id_prmtr}]},
        )
        assert resp.status_code == 200

        columnas = db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == id_mp).all()
        assert [c.indc_clmn for c in columnas] == [4]

    def test_delimitador_invalido_devuelve_422(self, client, tecnico_editor, parametros):
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros)).json()["mapeo"]["id_mp"]
        assert client.put(f"/mapeos/{id_mp}", json={"dlmtdr": "|"}).status_code == 422

    def test_mapeo_inexistente_devuelve_404(self, client, tecnico_editor):
        assert client.put("/mapeos/999999", json={"dlmtdr": ";"}).status_code == 404

    def test_denegado_con_permiso_de_solo_lectura(self, client, db_session, tecnico_editor, fabrica, parametros):
        id_mp = client.post("/mapeos", json=cuerpo_mapeo(parametros)).json()["mapeo"]["id_mp"]
        sede, _ = tecnico_editor

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

    def test_denegado_sin_permiso(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )
        assert self._subir(client, "ejemplo_estado_gabinete.dat").status_code == 403
