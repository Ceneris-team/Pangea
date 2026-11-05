"""
QA - Reprueba PP-185 (RG-37 y CA-08) sobre 67a8309.

Complementa test_hu21_qa.py: sus 5 casos CA-08 buscan el formato de auditoría
anterior a 2392be3 (MiembroEmpresa, empresa_ids). Aquí se comprueba el formato
actual, escrito por triggers en la misma transacción.
"""

from app.models import LogAuditoria

from test_hu21_qa import api, mundo, patch_miembro, put_anterior  # noqa: F401
from tests.conftest import _engine, db_session, fabrica  # noqa: F401


def _filas(m, prefijo):
    # origen API: la preparación del caso también dispara los triggers.
    return (m.db.query(LogAuditoria).filter(LogAuditoria.entdd.like(f"{prefijo}%"), LogAuditoria.origen == "API")
            .order_by(LogAuditoria.id_evnt).all())


def test_rg37_proyecto_inactivo_propio_explica_el_motivo(api, mundo):
    m = mundo
    m.p2.estd = "Inactiva"
    m.db.flush()
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p1.id_ubccn, m.p2.id_ubccn])
    assert r.status_code == 422
    assert r.json()["detail"] == f"Hay proyectos inactivos: {m.p2.nmbr}"
    assert m.proyectos_miembro(m.m_lector) == {m.p1.id_ubccn}


def test_rg37_conservar_marcado_un_proyecto_que_paso_a_inactivo(api, mundo):
    m = mundo
    m.p1.estd = "Inactiva"
    m.db.flush()
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p1.id_ubccn])
    assert r.status_code == 422 and "inactivos" in r.json()["detail"]
    assert "no pertenecen" not in r.json()["detail"]


def test_rg37_reactivar_lector_con_proyecto_inactivo(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Inactivo", [m.p1.id_ubccn]).status_code == 200
    m.p1.estd = "Inactiva"
    m.db.flush()
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p1.id_ubccn])
    assert r.status_code == 422 and "inactivos" in r.json()["detail"]
    m.db.refresh(m.m_lector)
    assert m.m_lector.estd == "Inactivo"


def test_rg37_proyecto_ajeno_e_inactivo_no_revela_nombres(api, mundo):
    m = mundo
    m.p2.estd = "Inactiva"
    m.db.flush()
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn, m.pb.id_ubccn])
    assert r.status_code == 422
    assert r.json()["detail"] == "Hay proyectos que no pertenecen a esta empresa"


def test_riesgo_proyecto_activo_en_sede_inactiva(api, mundo):
    """El flujo anterior rechaza este caso. CA-03: «estado de los proyectos»."""
    m = mundo
    m.s1.estd = "Inactiva"
    m.db.flush()
    r = patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Activo", [m.p2.id_ubccn])
    print("RESULTADO_SEDE_INACTIVA", r.status_code, r.text)
    assert r.status_code == 422


def test_ca08_cambio_de_rol_y_proyectos_con_antes_y_despues(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Tecnico", "Activo", []).status_code == 200
    fila = _filas(m, f"miembro_empresa:{m.m_lector.id_mmb}")[-1]
    assert fila.id_usr == m.admin_a.id_usr and fila.fch_evnt is not None and fila.id_clnt == m.a.id_clnt
    assert fila.vlrs_antrrs["rol"] == "Lector" and fila.vlrs_nvs["rol"] == "Tecnico"
    assert fila.vlrs_nvs["usuario_id"] == m.lector.id_usr and fila.vlrs_nvs["cliente_id"] == m.a.id_clnt
    proyectos = _filas(m, f"proyectos_miembro:{m.m_lector.id_mmb}")
    assert proyectos[0].vlrs_antrrs["proyecto_ids"] == [m.p1.id_ubccn]
    assert proyectos[-1].vlrs_nvs["proyecto_ids"] == []


def test_ca08_flujo_anterior_conserva_conjunto_inicial_y_final(api, mundo):
    m = mundo
    assert put_anterior(api, m, m.admin, m.cf, [m.p2.id_ubccn]).status_code == 200
    filas = _filas(m, f"permisos_ubicacion:{m.cf.id_usr}")
    assert filas[0].vlrs_antrrs["ubicacion_ids"] == [m.p1.id_ubccn]
    assert filas[-1].vlrs_nvs["ubicacion_ids"] == [m.p2.id_ubccn]
    assert all(f.id_usr == m.admin.id_usr and f.id_clnt == m.a.id_clnt for f in filas)
    assert filas[-1].vlrs_nvs["rol"] == "Cliente Final"


def test_ca08_retirar_todo_el_acceso_anterior(api, mundo):
    m = mundo
    assert put_anterior(api, m, m.admin, m.cf, []).status_code == 200
    assert _filas(m, f"permisos_ubicacion:{m.cf.id_usr}")[-1].vlrs_nvs["ubicacion_ids"] == []


def test_ca08_desactivacion_registra_estado(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Lector", "Inactivo", [m.p1.id_ubccn]).status_code == 200
    fila = _filas(m, f"miembro_empresa:{m.m_lector.id_mmb}")[-1]
    assert fila.vlrs_antrrs["estado"] == "Activo" and fila.vlrs_nvs["estado"] == "Inactivo"


def test_ca08_el_cambio_se_ve_en_la_consulta_de_auditoria(api, mundo):
    m = mundo
    assert patch_miembro(api, m, m.admin_a, m.a, m.m_lector, "Tecnico", "Activo", []).status_code == 200
    r = api.get("/auditoria", headers=m.h(m.admin), params={"usuario_id": m.admin_a.id_usr})
    assert r.status_code == 200, r.text
    assert f"miembro_empresa:{m.m_lector.id_mmb}" in r.text
