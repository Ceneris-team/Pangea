"""
HU 28 - Crear alarma.

  CA1  el formulario ofrece Nombre, Parámetro a monitorear y Ubicación
       asociada; el selector de parámetros solo muestra los disponibles en
       las ubicaciones asignadas al usuario (HU21)
  CA2  "SIGUIENTE" es navegación de UI (paso de condiciones, HU29): no
       toca el backend y por eso no tiene test acá
  CA3  "GUARDAR" crea la alarma con estado Activa, la agrega al listado
       (el de HU27, que filtra por dueño) y devuelve "Alarma creada
       correctamente"
  CA4  "CANCELAR" no crea ningún registro. Tampoco tiene endpoint -nada se
       escribe hasta el GUARDAR final-, así que lo que se verifica acá es
       la premisa que lo hace cierto: el alta es UNA sola escritura
       (test_el_listado_arranca_vacio_sin_guardar)

Corre contra la Postgres real de test (ver conftest.py).
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    Alarma,
    CondicionAlarma,
    ConexionFTP,
    Dispositivo,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    PermisoUbicacion,
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
    ubicacion = Ubicacion(id_sd=sede.id_sd, nmbr=nombre, lttd=0, lngtd=0, plgn_gjsn=POLIGONO_DUMMY)
    db_session.add(ubicacion)
    db_session.flush()
    return ubicacion


def crear_conexion(db_session, sede, nombre="Datalogger de prueba"):
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


def crear_dispositivo(db_session, ubicacion, conexion, nombre="CR1000-HU28"):
    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=nombre,
        mrc="Campbell",
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
    """DEC-09: el mapeo cuelga del dispositivo (mp_frmt.id_dspstv) y la
    columna se enlaza al parámetro vía mp_clmn. Un dispositivo admite un
    solo mp_frmt activo por tipo de trama, así que un segundo parámetro se
    agrega como otra columna del mismo mapeo."""
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
    db_session.add(MapeoColumna(id_mp=mapeo.id_mp, indc_clmn=indice, id_prmtr=parametro.id_prmtr))
    db_session.flush()
    return mapeo


@pytest.fixture()
def escenario(db_session, fabrica):
    """Cliente Final con Edición sobre "Alarmas", UNA ubicación asignada y
    un parámetro numérico mapeado en un dispositivo de esa ubicación."""
    rol_cliente = fabrica.rol("Cliente Final")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol_cliente)
    agregar_permiso(db_session, usuario, sede, "Alarmas", "Edición", rol_cliente)

    ubicacion = crear_ubicacion(db_session, sede, nombre="Estación Asignada")
    asignar_ubicacion(db_session, usuario, ubicacion)

    conexion = crear_conexion(db_session, sede)
    dispositivo = crear_dispositivo(db_session, ubicacion, conexion)
    parametro = crear_parametro(db_session, "Nivel HU28", unidad="m")
    mapear_parametro(db_session, dispositivo, parametro)

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
    }


def cuerpo_valido(escenario, **overrides):
    cuerpo = {
        "nmbr": "Crecida del río",
        "id_prmtr": escenario["parametro"].id_prmtr,
        "id_ubccn": escenario["ubicacion"].id_ubccn,
        "condiciones": [{"oprdr": ">", "vlr_umbrl": 3.5}],
    }
    cuerpo.update(overrides)
    return cuerpo


class TestCA1CamposDelFormulario:
    """CA1: los dos selectores del formulario se pueblan con lo que el
    usuario tiene asignado (HU21) y mapeado (HU06)."""

    def test_selector_de_ubicaciones_solo_trae_las_asignadas(self, client, db_session, escenario):
        crear_ubicacion(db_session, escenario["sede"], nombre="Estación No Asignada")

        resp = client.get("/alarmas/ubicaciones")
        assert resp.status_code == 200
        assert [u["nmbr"] for u in resp.json()["items"]] == ["Estación Asignada"]

    def test_selector_de_parametros_de_la_ubicacion_elegida(self, client, escenario):
        resp = client.get(
            "/alarmas/parametros", params={"ubicacion_id": escenario["ubicacion"].id_ubccn}
        )
        assert resp.status_code == 200
        assert [p["nmbr"] for p in resp.json()["items"]] == ["Nivel HU28"]

    def test_parametro_del_catalogo_sin_mapear_no_aparece(self, client, db_session, escenario):
        crear_parametro(db_session, "pH Sin Mapear HU28", unidad="pH")

        resp = client.get("/alarmas/parametros")
        assert [p["nmbr"] for p in resp.json()["items"]] == ["Nivel HU28"]

    def test_parametro_de_ubicacion_ajena_no_aparece(self, client, db_session, escenario):
        ajena = crear_ubicacion(db_session, escenario["sede"], nombre="Estación Ajena")
        conexion = crear_conexion(db_session, escenario["sede"], nombre="Datalogger Ajeno")
        dispositivo = crear_dispositivo(db_session, ajena, conexion, nombre="CR1000-Ajeno")
        parametro = crear_parametro(db_session, "Conductividad Ajena HU28", unidad="uS/cm")
        mapear_parametro(db_session, dispositivo, parametro)

        resp = client.get("/alarmas/parametros")
        assert [p["nmbr"] for p in resp.json()["items"]] == ["Nivel HU28"]

    def test_parametro_de_texto_no_es_monitoreable(self, client, db_session, escenario):
        """Una condición de alarma compara contra un umbral numérico
        (cndcn_alrm.vlr_umbrl), así que un parámetro de texto -"Puerta
        Abierta"- no puede ofrecerse: la alarma nunca podría dispararse."""
        parametro_texto = crear_parametro(
            db_session, "Mensaje Puerta HU28", unidad="N/A", tipo_dato="texto"
        )
        mapear_parametro(db_session, escenario["dispositivo"], parametro_texto, indice=2)

        resp = client.get("/alarmas/parametros")
        assert [p["nmbr"] for p in resp.json()["items"]] == ["Nivel HU28"]

    def test_ubicacion_ajena_en_el_filtro_devuelve_lista_vacia(self, client, db_session, escenario):
        ajena = crear_ubicacion(db_session, escenario["sede"], nombre="Estación Ajena Filtro")

        resp = client.get("/alarmas/parametros", params={"ubicacion_id": ajena.id_ubccn})
        assert resp.status_code == 200
        assert resp.json()["items"] == []


class TestCA3Guardar:
    """CA3: GUARDAR crea la alarma en estado Activa, la agrega al listado y
    devuelve el mensaje de éxito."""

    def test_crea_la_alarma_activa_con_el_mensaje_de_exito(self, client, escenario):
        resp = client.post("/alarmas", json=cuerpo_valido(escenario))

        assert resp.status_code == 201
        cuerpo = resp.json()
        assert cuerpo["mensaje"] == "Alarma creada correctamente"
        assert cuerpo["alarma"]["estd"] == "Activa"
        assert cuerpo["alarma"]["nmbr"] == "Crecida del río"
        assert cuerpo["alarma"]["parametro_nombre"] == "Nivel HU28"
        # La alarma vuelve con la misma forma que en el listado de HU27,
        # condición ya formateada incluida.
        assert cuerpo["alarma"]["condicion"] == "> 3.5 m"

    def test_la_alarma_creada_aparece_en_el_listado(self, client, escenario):
        client.post("/alarmas", json=cuerpo_valido(escenario))

        resp = client.get("/alarmas")
        assert resp.status_code == 200
        assert [a["nmbr"] for a in resp.json()["items"]] == ["Crecida del río"]

    def test_persiste_las_condiciones_del_paso_2(self, client, db_session, escenario):
        """El alta es de dos pasos pero una sola escritura: las
        condiciones de HU29 llegan en el mismo POST del GUARDAR.

        Se comprueban en cndcn_alrm y no en la respuesta: la fila de HU27
        resume la alarma con UNA condición formateada, así que por la
        respuesta sola no se vería que se guardaron las dos."""
        resp = client.post(
            "/alarmas",
            json=cuerpo_valido(
                escenario,
                condiciones=[{"oprdr": ">=", "vlr_umbrl": 3.5}, {"oprdr": "<", "vlr_umbrl": 0.2}],
            ),
        )
        assert resp.status_code == 201

        alarma = db_session.query(Alarma).filter(Alarma.nmbr == "Crecida del río").first()
        condiciones = (
            db_session.query(CondicionAlarma)
            .filter(CondicionAlarma.id_alrm == alarma.id_alrm)
            .order_by(CondicionAlarma.id_cndcn)
            .all()
        )
        assert [(c.oprdr, float(c.vlr_umbrl)) for c in condiciones] == [(">=", 3.5), ("<", 0.2)]

    def test_la_sede_sale_de_la_ubicacion_no_del_jwt(self, client, db_session, escenario):
        """alrm.id_sd es NOT NULL y tiene que ser la sede del recurso: un
        usuario 'global' no tiene sede propia que poner ahí."""
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            escenario["usuario"], escenario["rol"].nmbr, sede_id=None, scope="global"
        )

        resp = client.post("/alarmas", json=cuerpo_valido(escenario))
        assert resp.status_code == 201

        alarma = db_session.query(Alarma).filter(Alarma.nmbr == "Crecida del río").first()
        assert alarma.id_sd == escenario["sede"].id_sd


class TestValidacionesDelFormulario:
    """Reglas de los "detalles de la conversación" de la HU: campos
    obligatorios, nombre alfanumérico de hasta 100 caracteres, y parámetro
    dentro de lo que ofrece el selector."""

    def test_nombre_vacio_es_rechazado(self, client, escenario):
        assert client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="   ")).status_code == 422

    def test_nombre_de_mas_de_100_caracteres_es_rechazado(self, client, escenario):
        resp = client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="A" * 101))
        assert resp.status_code == 422

    def test_nombre_de_100_caracteres_es_aceptado(self, client, escenario):
        resp = client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="A" * 100))
        assert resp.status_code == 201

    def test_nombre_sin_ningun_alfanumerico_es_rechazado(self, client, escenario):
        assert client.post("/alarmas", json=cuerpo_valido(escenario, nmbr="###")).status_code == 422

    def test_falta_un_campo_obligatorio(self, client, escenario):
        cuerpo = cuerpo_valido(escenario)
        del cuerpo["id_prmtr"]
        assert client.post("/alarmas", json=cuerpo).status_code == 422

    def test_operador_fuera_del_check_es_rechazado(self, client, escenario):
        resp = client.post(
            "/alarmas",
            json=cuerpo_valido(escenario, condiciones=[{"oprdr": "!=", "vlr_umbrl": 1}]),
        )
        assert resp.status_code == 422

    def test_parametro_no_disponible_en_la_ubicacion(self, client, db_session, escenario):
        suelto = crear_parametro(db_session, "Caudal Sin Mapear HU28", unidad="m3/s")

        resp = client.post("/alarmas", json=cuerpo_valido(escenario, id_prmtr=suelto.id_prmtr))
        assert resp.status_code == 422
        assert "no está disponible" in resp.json()["detail"]

    def test_ubicacion_no_asignada_es_403(self, client, db_session, escenario):
        ajena = crear_ubicacion(db_session, escenario["sede"], nombre="Estación Prohibida")

        resp = client.post("/alarmas", json=cuerpo_valido(escenario, id_ubccn=ajena.id_ubccn))
        assert resp.status_code == 403


class TestCA4Cancelar:
    def test_el_listado_arranca_vacio_sin_guardar(self, client, escenario):
        """CA4: recorrer el formulario sin llegar al GUARDAR no deja
        ningún registro. El backend lo garantiza porque no hay escritura
        hasta el POST final -no existe un endpoint de "paso 1"-."""
        resp = client.get("/alarmas")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestAislamientoYPermisos:
    def test_sin_permiso_de_edicion_no_puede_crear(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Alarmas", "Lectura", rol)
        ubicacion = crear_ubicacion(db_session, sede, nombre="Estación Solo Lectura")
        asignar_ubicacion(db_session, usuario, ubicacion)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        resp = client.post(
            "/alarmas",
            json={"nmbr": "Intento", "id_prmtr": 1, "id_ubccn": ubicacion.id_ubccn},
        )
        assert resp.status_code == 403

    def test_sin_permiso_de_lectura_no_puede_listar(self, client, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Tableros", "Lectura", rol)

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            usuario, rol.nmbr, sede_id=sede.id_sd
        )

        assert client.get("/alarmas").status_code == 403

    def test_la_alarma_creada_queda_a_nombre_de_quien_la_crea(
        self, client, db_session, fabrica, escenario
    ):
        """El listado de HU27 filtra por dueño ("cada usuario solo ve y
        gestiona sus propias alarmas"), así que el alta tiene que dejar
        id_usr apuntando a quien guardó: otro usuario, aunque tenga la
        misma ubicación asignada, no ve esa alarma."""
        client.post("/alarmas", json=cuerpo_valido(escenario))

        rol = escenario["rol"]
        otro = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, otro, escenario["sede"], "Alarmas", "Edición", rol)
        asignar_ubicacion(db_session, otro, escenario["ubicacion"])

        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro, rol.nmbr, sede_id=escenario["sede"].id_sd
        )

        assert client.get("/alarmas").json()["total"] == 0

        alarma = db_session.query(Alarma).filter(Alarma.nmbr == "Crecida del río").first()
        assert alarma.id_usr == escenario["usuario"].id_usr
