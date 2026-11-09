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

Base: tests de la rama `fabio` (commit ca9e795). Al integrarlos a dev se
agregó la suscripción vigente de la empresa (dev exige una para dar de
alta configuración operativa) y el caso de empresa en modo consulta.
"""

from datetime import timedelta

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
    PlanSuscripcion,
    Suscripcion,
    Ubicacion,
)
from app.models.suscripcion import PermisoUsuarioSede
from app.security.dependencies import get_current_user
from app.services.limites_plan import fecha_comercial

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


def dar_suscripcion_vigente(db, sede):
    """La empresa dueña de la sede con un contrato vigente y sus límites:
    sin él, dev la deja en modo consulta (services/contratos.exigir_operacion)."""
    plan = PlanSuscripcion(nmbr=f"Plan alarmas {sede.id_sd}", prc_mnsl=100)
    db.add(plan)
    db.flush()
    hoy = fecha_comercial()
    db.add(
        Suscripcion(
            id_clnt=sede.id_clnt,
            id_pln=plan.id_pln,
            fch_inc=hoy,
            fch_vncmnt=hoy + timedelta(days=30),
            estd="Activa",
            condiciones={
                "plan_nombre": plan.nmbr,
                "dias_gracia": 0,
                "limites": {"ubicaciones": 0, "dispositivos": 0, "usuarios": 0},
                "funcionalidades": [],
            },
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
    dar_suscripcion_vigente(db_session, sede)
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

    def test_empresa_sin_suscripcion_vigente_no_crea_alarmas(self, client, db_session, escenario):
        """Regla de dev: sin contrato vigente la empresa queda en modo
        consulta y no da de alta configuración operativa."""
        db_session.query(Suscripcion).filter(
            Suscripcion.id_clnt == escenario["sede"].id_clnt
        ).update({"estd": "Suspendida"})
        db_session.flush()

        resp = client.post("/alarmas", json=cuerpo_valido(escenario))
        assert resp.status_code == 409
        assert "modo consulta" in resp.json()["detail"]
        assert db_session.query(Alarma).filter(Alarma.nmbr == "Crecida del río").count() == 0


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


class TestNotificacionesHT14:
    def crear(self, client, escenario, **extra):
        resp = client.post("/alarmas", json=cuerpo_valido(escenario, **extra))
        assert resp.status_code == 201, resp.text
        return resp.json()["alarma"]["id_alrm"]

    def test_crea_varios_destinatarios_y_normaliza_correo(self, client, escenario):
        id_alarma = self.crear(
            client, escenario, destinatarios=["UNO@example.com", "dos@example.com"]
        )
        respuesta = client.get(f"/alarmas/{id_alarma}/destinatarios")
        assert respuesta.status_code == 200
        assert {d["correo"] for d in respuesta.json()["items"]} == {
            "uno@example.com",
            "dos@example.com",
        }

    def test_agrega_rechaza_duplicado_y_quita_destinatario(self, client, escenario):
        id_alarma = self.crear(client, escenario)
        ruta = f"/alarmas/{id_alarma}/destinatarios"
        agregado = client.post(ruta, json={"correo": "UNO@example.com"})
        assert agregado.status_code == 201
        assert client.post(ruta, json={"correo": "uno@example.com"}).status_code == 409
        assert client.delete(f"{ruta}/{agregado.json()['id']}").status_code == 204
        assert client.get(ruta).json()["items"] == []

    def test_rechaza_correo_invalido_y_duplicados_en_alta(self, client, escenario):
        for correos in (["invalido"], ["uno@example.com", "UNO@example.com"]):
            assert (
                client.post(
                    "/alarmas", json=cuerpo_valido(escenario, destinatarios=correos)
                ).status_code
                == 422
            )

    def test_no_gestiona_destinatarios_de_otro_usuario(
        self, client, escenario, db_session, fabrica
    ):
        id_alarma = self.crear(client, escenario)
        otro = fabrica.usuario(rol=escenario["rol"])
        agregar_permiso(db_session, otro, escenario["sede"], "Alarmas", "Edición", escenario["rol"])
        asignar_ubicacion(db_session, otro, escenario["ubicacion"])
        app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
            otro, escenario["rol"].nmbr, sede_id=escenario["sede"].id_sd
        )
        assert client.get(f"/alarmas/{id_alarma}/destinatarios").status_code == 404
        assert (
            client.post(
                f"/alarmas/{id_alarma}/destinatarios", json={"correo": "uno@example.com"}
            ).status_code
            == 404
        )
        assert (
            client.get("/alarmas/notificaciones", params={"alarma_id": id_alarma}).status_code
            == 404
        )

    def test_puede_consultar_historial_con_intentos_y_filtros(self, client, escenario, db_session):
        from app.models import IntentoNotificacion, NotificacionEnviada
        from app.services.notificaciones import crear_notificacion

        id_alarma = self.crear(client, escenario)
        for estado in ("Enviado", "Fallido"):
            n = crear_notificacion(
                db_session,
                destinatario="uno@example.com",
                tipo="alarma_activada",
                contexto={},
                id_usr=escenario["usuario"].id_usr,
                id_alrm=id_alarma,
                id_sd=escenario["sede"].id_sd,
            )
            n.estd = estado
            db_session.flush()
            db_session.add(IntentoNotificacion(id_ntfccn=n.id_ntfccn, numero=1, resultado=estado))
        db_session.flush()
        res = client.get(
            "/alarmas/notificaciones",
            params={"alarma_id": id_alarma, "estado": "Fallido", "destinatario": "UNO@example.com"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["total"] == 1
        assert res.json()["items"][0]["intentos"][0]["resultado"] == "Fallido"
        assert db_session.query(NotificacionEnviada).count() == 2
        assert (
            client.get("/alarmas/notificaciones", params={"desde": "2026-11-01"}).status_code == 422
        )

    def test_historial_no_expone_avisos_ajenos(self, client, escenario, db_session, fabrica):
        from app.services.notificaciones import crear_notificacion

        otro = fabrica.usuario()
        crear_notificacion(
            db_session,
            destinatario="otro@example.com",
            tipo="generica",
            contexto={},
            id_usr=otro.id_usr,
        )
        db_session.flush()
        assert client.get("/alarmas/notificaciones").json()["total"] == 0

    def test_pausa_alarma_y_actualiza_condicion(self, client, escenario, db_session):
        id_alarma = self.crear(client, escenario)
        res = client.patch(
            f"/alarmas/{id_alarma}",
            json={"estado": "Inactiva", "condiciones": [{"oprdr": ">=", "vlr_umbrl": 10}]},
        )
        assert res.status_code == 200
        assert res.json()["estado"] == "Inactiva"
        condicion = db_session.query(CondicionAlarma).filter_by(id_alrm=id_alarma).one()
        assert condicion.oprdr == ">=" and condicion.vlr_umbrl == 10

    def test_sin_operacion_no_puede_agregar_destinatarios(self, client, escenario, db_session):
        id_alarma = self.crear(client, escenario)
        db_session.query(Suscripcion).filter_by(id_clnt=escenario["sede"].id_clnt).update(
            {"estd": "Cancelada"}
        )
        db_session.flush()
        assert (
            client.post(
                f"/alarmas/{id_alarma}/destinatarios", json={"correo": "uno@example.com"}
            ).status_code
            == 409
        )

    def test_sin_asignacion_no_ve_historial_ni_destinatarios(self, client, escenario, db_session):
        id_alarma = self.crear(client, escenario)
        db_session.query(PermisoUbicacion).filter_by(id_usr=escenario["usuario"].id_usr).delete()
        db_session.flush()
        assert client.get(f"/alarmas/{id_alarma}/destinatarios").status_code == 404
        assert client.get("/alarmas").json()["total"] == 0

    def test_permiso_solo_lectura_no_modifica(self, client, escenario, db_session):
        id_alarma = self.crear(client, escenario)
        db_session.query(PermisoUsuarioSede).filter_by(
            id_usr=escenario["usuario"].id_usr, mdl="Alarmas"
        ).update({"nvl": "Lectura"})
        db_session.flush()
        assert client.get(f"/alarmas/{id_alarma}/destinatarios").status_code == 200
        assert (
            client.post(
                f"/alarmas/{id_alarma}/destinatarios", json={"correo": "uno@example.com"}
            ).status_code
            == 403
        )


# ---------------------------------------------------------------------------
# PP-72 - HU 27 Listar alarmas (GET /alarmas)
#
# CA1: tabla con nombre de la alarma, parámetro asociado, condición y estado
# (las acciones las arma el frontend). CA2: filtro por estado. CA3: búsqueda
# por nombre. Detalles: estados Activa e Inactiva; 10 registros por página;
# cada usuario solo ve sus propias alarmas; sin alarmas, total 0 (el mensaje
# y el botón son del frontend).
# ---------------------------------------------------------------------------
def crear_alarma(db, escenario, nombre, estado="Activa", condicion=(">", 3.5), usuario=None):
    alarma = Alarma(
        id_usr=(usuario or escenario["usuario"]).id_usr,
        id_sd=escenario["sede"].id_sd,
        nmbr=nombre,
        id_prmtr=escenario["parametro"].id_prmtr,
        id_ubccn=escenario["ubicacion"].id_ubccn,
        estd=estado,
    )
    db.add(alarma)
    db.flush()
    if condicion:
        db.add(CondicionAlarma(id_alrm=alarma.id_alrm, oprdr=condicion[0], vlr_umbrl=condicion[1]))
        db.flush()
    return alarma


def nombres(respuesta):
    return [a["nmbr"] for a in respuesta.json()["items"]]


# --- CA1 -----------------------------------------------------------------------


def test_listado_trae_nombre_parametro_condicion_y_estado(client, db_session, escenario):
    crear_alarma(db_session, escenario, "Crecida del río", condicion=(">=", 30.0))

    resp = client.get("/alarmas")

    assert resp.status_code == 200
    [fila] = resp.json()["items"]
    assert fila["nmbr"] == "Crecida del río"
    assert fila["parametro_nombre"] == "Nivel HU28"
    assert fila["condicion"] == ">= 30 m"
    assert fila["estd"] == "Activa"
    assert isinstance(fila["id_alrm"], int)


def test_alarma_sin_condicion_viaja_con_condicion_nula(client, db_session, escenario):
    crear_alarma(db_session, escenario, "Sin condición", condicion=None)
    assert client.get("/alarmas").json()["items"][0]["condicion"] is None


def test_listado_ordenado_por_nombre(client, db_session, escenario):
    for nombre in ["Gamma", "alfa", "Beta"]:
        crear_alarma(db_session, escenario, nombre)
    # Orden de la base (por nmbr): mayúsculas antes que minúsculas en C;
    # se verifica que sea estable y determinado por el nombre.
    primera = nombres(client.get("/alarmas"))
    assert sorted(primera) == sorted(["Gamma", "alfa", "Beta"])
    assert primera == nombres(client.get("/alarmas"))


def test_sin_alarmas_devuelve_lista_vacia(client, escenario):
    cuerpo = client.get("/alarmas").json()
    assert cuerpo["total"] == 0
    assert cuerpo["items"] == []


# --- PP-223: cada usuario solo ve las suyas ---------------------------------------


def test_cada_usuario_solo_ve_sus_alarmas(client, db_session, fabrica, escenario):
    crear_alarma(db_session, escenario, "Mía")
    rol = escenario["rol"]
    otro = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, otro, escenario["sede"], "Alarmas", "Edición", rol)
    asignar_ubicacion(db_session, otro, escenario["ubicacion"])
    crear_alarma(db_session, escenario, "Del otro usuario", usuario=otro)

    assert nombres(client.get("/alarmas")) == ["Mía"]

    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        otro, rol.nmbr, sede_id=escenario["sede"].id_sd
    )
    assert nombres(client.get("/alarmas")) == ["Del otro usuario"]


# --- PP-224: filtro por estado -------------------------------------------------------


@pytest.mark.parametrize(
    ("estado", "esperado"),
    [
        ("Activa", ["Activa 1", "Activa 2"]),
        ("Inactiva", ["Inactiva 1"]),
        (None, ["Activa 1", "Activa 2", "Inactiva 1"]),
    ],
)
def test_filtro_por_estado(client, db_session, escenario, estado, esperado):
    crear_alarma(db_session, escenario, "Activa 1")
    crear_alarma(db_session, escenario, "Activa 2")
    crear_alarma(db_session, escenario, "Inactiva 1", estado="Inactiva")

    params = {"estado": estado} if estado else {}
    resp = client.get("/alarmas", params=params)

    assert sorted(nombres(resp)) == esperado
    assert resp.json()["total"] == len(esperado)


# --- CA3: búsqueda por nombre ---------------------------------------------------------


def test_busqueda_parcial_sin_distinguir_mayusculas(client, db_session, escenario):
    crear_alarma(db_session, escenario, "Crecida del Río Rímac")
    crear_alarma(db_session, escenario, "pH alto Planta")

    assert nombres(client.get("/alarmas", params={"busqueda": "río"})) == ["Crecida del Río Rímac"]
    assert nombres(client.get("/alarmas", params={"busqueda": "PH ALTO"})) == ["pH alto Planta"]
    assert nombres(client.get("/alarmas", params={"busqueda": "no existe"})) == []


@pytest.mark.parametrize("texto", ["_", "%", "50%"])
def test_busqueda_trata_comodines_como_texto(client, db_session, escenario, texto):
    """Con LIKE a mano, "_" y "%" eran comodines y devolvían todo."""
    crear_alarma(db_session, escenario, "Nivel 50% del cauce")
    crear_alarma(db_session, escenario, "Caudal alto")

    encontradas = nombres(client.get("/alarmas", params={"busqueda": texto}))

    assert "Caudal alto" not in encontradas
    if texto != "_":
        assert encontradas == ["Nivel 50% del cauce"]
    else:
        assert encontradas == []


def test_busqueda_y_estado_se_combinan(client, db_session, escenario):
    crear_alarma(db_session, escenario, "Crecida norte")
    crear_alarma(db_session, escenario, "Crecida sur", estado="Inactiva")

    resp = client.get("/alarmas", params={"busqueda": "crecida", "estado": "Inactiva"})
    assert nombres(resp) == ["Crecida sur"]


# --- Paginación de 10 -----------------------------------------------------------------


def test_pagina_de_10_por_defecto(client, db_session, escenario):
    for n in range(12):
        crear_alarma(db_session, escenario, f"Alarma {n:02d}")

    primera = client.get("/alarmas").json()
    segunda = client.get("/alarmas", params={"pagina": 2}).json()

    assert primera["por_pagina"] == 10
    assert primera["total"] == 12
    assert len(primera["items"]) == 10
    assert len(segunda["items"]) == 2
    assert not set(nombres_de(primera)) & set(nombres_de(segunda))


def nombres_de(cuerpo):
    return [a["nmbr"] for a in cuerpo["items"]]
