"""Flujo comercial real: plan, límites y suscripción por cliente."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import PermisoUbicacion, PermisoUsuarioSede, PlanSuscripcion, Suscripcion, Ubicacion
from app.security.dependencies import get_current_user
from app.services.limites_plan import fecha_comercial


@pytest.fixture()
def comercial(db_session, fabrica):
    rol = fabrica.rol("Administrador Comercial")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol, scp="global")
    db_session.add(
        PermisoUsuarioSede(
            id_usr=usuario.id_usr,
            id_sd=sede.id_sd,
            id_rl=rol.id_rl,
            mdl="Comercial",
            nvl="Edición",
        )
    )
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(usuario.id_usr),
        "sede_id": None,
        "scope": "global",
        "rol": rol.nmbr,
    }
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_crear_limitar_y_asignar_plan(comercial, fabrica):
    cliente = fabrica.cliente()
    creado = comercial.post(
        "/comercial/planes",
        json={"nombre": f"Plan cliente {cliente.id_clnt}", "precio_mensual": "299.00"},
    )
    assert creado.status_code == 201, creado.text
    plan_id = creado.json()["plan"]["id_pln"]
    assert creado.json()["plan"]["limites"] is None

    fechas = {
        "plan_id": plan_id,
        "fecha_inicio": date.today().isoformat(),
        "fecha_vencimiento": (date.today() + timedelta(days=30)).isoformat(),
    }
    sin_limites = comercial.put(f"/comercial/clientes/{cliente.id_clnt}/suscripcion", json=fechas)
    assert sin_limites.status_code == 409

    limites = comercial.put(
        f"/comercial/planes/{plan_id}/limites",
        json={"ubicaciones": 3, "dispositivos": 10, "usuarios": 5},
    )
    assert limites.status_code == 200, limites.text
    assert limites.json()["mensaje"] == "Niveles y límites configurados correctamente"

    asignada = comercial.put(f"/comercial/clientes/{cliente.id_clnt}/suscripcion", json=fechas)
    assert asignada.status_code == 200, asignada.text
    assert asignada.json()["cliente"]["plan_id"] == plan_id
    assert asignada.json()["cliente"]["estado_suscripcion"] == "Vigente"

    fechas["fecha_vencimiento"] = (date.today() + timedelta(days=60)).isoformat()
    reemplazada = comercial.put(f"/comercial/clientes/{cliente.id_clnt}/suscripcion", json=fechas)
    assert reemplazada.status_code == 200, reemplazada.text
    assert reemplazada.json()["cliente"]["fecha_vencimiento"] == fechas["fecha_vencimiento"]

    listado = comercial.get("/comercial/planes")
    assert listado.status_code == 200
    assert any(p["id_pln"] == plan_id for p in listado.json())


def test_nombre_duplicado_y_limites_negativos(comercial, fabrica):
    nombre = f"Plan único {fabrica.cliente().id_clnt}"
    primero = comercial.post("/comercial/planes", json={"nombre": nombre, "precio_mensual": "0.00"})
    assert primero.status_code == 201
    repetido = comercial.post("/comercial/planes", json={"nombre": nombre.lower(), "precio_mensual": "1.00"})
    assert repetido.status_code == 409
    plan_id = primero.json()["plan"]["id_pln"]
    invalidos = comercial.put(
        f"/comercial/planes/{plan_id}/limites",
        json={"ubicaciones": -1, "dispositivos": 1, "usuarios": 1},
    )
    assert invalidos.status_code == 422


def test_mi_plan_solo_expone_cliente_de_su_sede(comercial, fabrica):
    assert comercial.get("/comercial/mi-plan").status_code == 403
    cliente = fabrica.cliente()
    sede = fabrica.sede(cliente)
    otra_sede = fabrica.sede(cliente)
    usuario = fabrica.usuario(fabrica.rol("Cliente Final"))
    poligono = {"type": "Polygon", "coordinates": [[[-77, -12], [-77.1, -12], [-77, -12.1], [-77, -12]]]}
    asignada = Ubicacion(id_sd=sede.id_sd, nmbr="Asignada", lttd=-12, lngtd=-77, plgn_gjsn=poligono)
    no_asignada = Ubicacion(id_sd=otra_sede.id_sd, nmbr="Otra sede", lttd=-12, lngtd=-77, plgn_gjsn=poligono)
    fabrica.db.add_all([asignada, no_asignada])
    fabrica.db.flush()
    fabrica.db.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=asignada.id_ubccn))
    fabrica.db.flush()
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(usuario.id_usr),
        "sede_id": sede.id_sd,
        "scope": "por_sede",
        "rol": "Cliente Final",
    }
    respuesta = comercial.get("/comercial/mi-plan")
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["id_clnt"] == cliente.id_clnt
    assert respuesta.json()["consumo"]["ubicaciones"] == 2
    assert respuesta.json()["ubicaciones_visibles"] == 1


def test_listado_comercial_muestra_plan_vencido(comercial, fabrica):
    cliente = fabrica.cliente()
    plan = PlanSuscripcion(nmbr=f"Plan vencido {cliente.id_clnt}", prc_mnsl=99)
    fabrica.db.add(plan)
    fabrica.db.flush()
    fabrica.db.add(Suscripcion(
        id_clnt=cliente.id_clnt,
        id_pln=plan.id_pln,
        fch_inc=fecha_comercial() - timedelta(days=40),
        fch_vncmnt=fecha_comercial() - timedelta(days=1),
        estd="Activa",
    ))
    fabrica.db.flush()

    respuesta = comercial.get("/comercial/clientes")
    assert respuesta.status_code == 200, respuesta.text
    resumen = next(item for item in respuesta.json() if item["id_clnt"] == cliente.id_clnt)
    assert resumen["plan_nombre"] == plan.nmbr
    assert resumen["estado_suscripcion"] == "Vencida"


def test_administrador_ceneris_consulta_y_crea_planes(comercial, fabrica):
    rol = fabrica.rol("Administrador")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol, scp="global")
    fabrica.db.add(PermisoUsuarioSede(
        id_usr=usuario.id_usr,
        id_sd=sede.id_sd,
        id_rl=rol.id_rl,
        mdl="Comercial",
        nvl="Lectura",
    ))
    fabrica.db.flush()
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(usuario.id_usr), "sede_id": None, "scope": "global", "rol": "Administrador"
    }

    assert comercial.get("/comercial/clientes").status_code == 200
    assert comercial.get("/comercial/planes").status_code == 200
    respuesta = comercial.post("/comercial/planes", json={"nombre": "Plan CENERIS", "precio_mensual": "99"})
    assert respuesta.status_code == 201, respuesta.text
