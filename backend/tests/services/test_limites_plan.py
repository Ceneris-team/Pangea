"""Reglas de cupos que afectan las altas de recursos de un cliente."""

from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.models import (
    Dispositivo,
    LimitePlan,
    PermisoUbicacion,
    PermisoUsuarioSede,
    PlanSuscripcion,
    Suscripcion,
    Ubicacion,
)
from app.services.limites_plan import comprobar_cupo, consumo_cliente


def plan_activo(db, cliente, ubicaciones=1, dispositivos=1, usuarios=1):
    plan = PlanSuscripcion(nmbr=f"Plan test {cliente.id_clnt}", prc_mnsl=100)
    db.add(plan)
    db.flush()
    db.add(
        LimitePlan(
            id_pln=plan.id_pln,
            mx_sds=0,
            mx_ubccns=ubicaciones,
            mx_dspstvs=dispositivos,
            mx_usrs=usuarios,
        )
    )
    db.add(
        Suscripcion(
            id_clnt=cliente.id_clnt,
            id_pln=plan.id_pln,
            fch_inc=date.today(),
            fch_vncmnt=date.today() + timedelta(days=30),
            estd="Activa",
        )
    )
    db.flush()
    return plan


def ubicacion(db, sede, nombre):
    fila = Ubicacion(
        id_sd=sede.id_sd,
        nmbr=nombre,
        lttd=-12,
        lngtd=-77,
        plgn_gjsn={"type": "Polygon", "coordinates": [[[-77, -12], [-77.1, -12], [-77, -12.1], [-77, -12]]]},
        estd="Activa",
    )
    db.add(fila)
    db.flush()
    return fila


def test_cupo_ubicaciones_suma_todas_las_sedes_y_cero_es_ilimitado(db_session, fabrica):
    cliente = fabrica.cliente()
    sede_a = fabrica.sede(cliente)
    sede_b = fabrica.sede(cliente)
    plan = plan_activo(db_session, cliente, ubicaciones=1)
    comprobar_cupo(db_session, cliente.id_clnt, "ubicaciones")
    ubicacion(db_session, sede_a, "Primera")

    with pytest.raises(HTTPException) as exc:
        comprobar_cupo(db_session, cliente.id_clnt, "ubicaciones")
    assert exc.value.status_code == 409
    assert consumo_cliente(db_session, cliente.id_clnt)["ubicaciones"] == 1

    limites = db_session.query(LimitePlan).filter(LimitePlan.id_pln == plan.id_pln).one()
    limites.mx_ubccns = 0
    db_session.flush()
    comprobar_cupo(db_session, cliente.id_clnt, "ubicaciones")
    ubicacion(db_session, sede_b, "Segunda")
    assert consumo_cliente(db_session, cliente.id_clnt)["ubicaciones"] == 2


def test_usuario_cliente_final_cuenta_una_vez_por_cliente(db_session, fabrica):
    cliente = fabrica.cliente()
    sede = fabrica.sede(cliente)
    una = ubicacion(db_session, sede, "Una")
    otra = ubicacion(db_session, sede, "Otra")
    rol_cliente = fabrica.rol("Cliente Final")
    final = fabrica.usuario(rol_cliente)
    interno = fabrica.usuario(fabrica.rol("Administrador"))
    db_session.add_all(
        [
            PermisoUbicacion(id_usr=final.id_usr, id_ubccn=una.id_ubccn),
            PermisoUbicacion(id_usr=final.id_usr, id_ubccn=otra.id_ubccn),
            PermisoUbicacion(id_usr=interno.id_usr, id_ubccn=una.id_ubccn),
            PermisoUsuarioSede(
                id_usr=final.id_usr,
                id_sd=sede.id_sd,
                id_rl=rol_cliente.id_rl,
                mdl="Tableros",
                nvl="Lectura",
            ),
        ]
    )
    db_session.flush()
    assert consumo_cliente(db_session, cliente.id_clnt)["usuarios"] == 1

    final.estd = "Inactivo"
    db_session.flush()
    assert consumo_cliente(db_session, cliente.id_clnt)["usuarios"] == 0


def test_dispositivo_inactivo_no_consume_cupo(db_session, fabrica):
    from app.models import ConexionFTP

    cliente = fabrica.cliente()
    sede = fabrica.sede(cliente)
    zona = ubicacion(db_session, sede, "Zona")
    # ConexionFTP exige los campos de conexión definidos en el modelo.
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr="TCP prueba",
        prtcl="TCP",
        hst="127.0.0.1",
        prt=21,
        crdncl_cfrd="no usada en test",
    )
    db_session.add(conexion)
    db_session.flush()
    dispositivo = Dispositivo(
        id_ubccn=zona.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr="Equipo",
        mrc="Prueba",
        lttd=-12,
        lngtd=-77,
        estd="Inactivo",
    )
    db_session.add(dispositivo)
    db_session.flush()
    assert consumo_cliente(db_session, cliente.id_clnt)["dispositivos"] == 0
    dispositivo.estd = "Activo"
    db_session.flush()
    assert consumo_cliente(db_session, cliente.id_clnt)["dispositivos"] == 1


def test_suscripcion_vencida_bloquea_altas(db_session, fabrica):
    cliente = fabrica.cliente()
    # Los clientes anteriores a la activación del módulo siguen operando
    # mientras Comercial les asigna un plan.
    comprobar_cupo(db_session, cliente.id_clnt, "ubicaciones")
    plan_activo(db_session, cliente)
    suscripcion = db_session.query(Suscripcion).filter(Suscripcion.id_clnt == cliente.id_clnt).one()
    suscripcion.fch_vncmnt = date.today() - timedelta(days=1)
    db_session.flush()
    with pytest.raises(HTTPException) as exc:
        comprobar_cupo(db_session, cliente.id_clnt, "ubicaciones")
    assert exc.value.status_code == 409
    assert "plan vigente" in exc.value.detail
