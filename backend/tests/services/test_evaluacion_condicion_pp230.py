"""
HU 29 - Establecer condiciones de la alarma (PP-74). PP-230: evaluar la
condición contra las lecturas nuevas de telemetría.

La evaluación vive en app/services/notificaciones.evaluar_alarmas (PP-424):
se llama desde la ingesta con las lecturas del archivo, avisa en la
transición normal -> alarma por dispositivo y rearma al volver al rango.
Acá se fija lo que PP-230 agrega a esa base:

  - los bordes exactos de cada uno de los 5 operadores;
  - que ACTUALIZAR la condición (PUT /alarmas/{id}/condicion) hace que la
    lectura siguiente se evalúe con la regla nueva, desde cero;
  - que el aviso lleva la condición vigente.

Reutiliza el escenario de tests/services/test_notificaciones_ses.py
(alarma "Temperatura alta" > 30 con dos destinatarios).
"""

from decimal import Decimal

import pytest

from app.models import CondicionAlarma, EstadoAlarma, NotificacionEnviada
from app.routers.alarmas import _reemplazar_condicion, _reiniciar_evaluacion
from app.schemas_alarmas import CondicionAlarmaCrear
from tests.services import test_notificaciones_ses as base

caso = base.caso
aislar_destinatario_pruebas = base.aislar_destinatario_pruebas
evaluar = base.evaluar

DESTINATARIOS = 2  # el escenario base tiene dos correos


def avisos(db):
    return db.query(NotificacionEnviada).filter_by(tipo="alarma_activada").count()


def fijar_condicion(db, caso, operador, umbral):
    db.query(CondicionAlarma).filter_by(id_alrm=caso["alarma"].id_alrm).update(
        {"oprdr": operador, "vlr_umbrl": Decimal(str(umbral))}
    )
    db.flush()


def actualizar_condicion(db, caso, operador, umbral):
    """Lo mismo que hace PUT /alarmas/{id}/condicion."""
    id_alarma = caso["alarma"].id_alrm
    if _reemplazar_condicion(db, id_alarma, CondicionAlarmaCrear(oprdr=operador, vlr_umbrl=umbral)):
        _reiniciar_evaluacion(db, id_alarma)
    db.flush()


@pytest.mark.parametrize(
    "operador, valor, notifica",
    [
        (">", "30", False),
        (">", "30.0001", True),
        (">=", "30", True),
        (">=", "29.9999", False),
        ("<", "30", False),
        ("<", "29.9999", True),
        ("<=", "30", True),
        ("<=", "30.0001", False),
        ("=", "30", True),
        ("=", "30.0001", False),
    ],
)
def test_bordes_de_cada_operador_con_lecturas_reales(db_session, caso, operador, valor, notifica):
    fijar_condicion(db_session, caso, operador, 30)
    evaluar(db_session, caso, [Decimal(valor)])
    assert avisos(db_session) == (DESTINATARIOS if notifica else 0)


def test_el_aviso_lleva_la_condicion_vigente(db_session, caso):
    evaluar(db_session, caso, [Decimal("35")])
    contexto = db_session.query(NotificacionEnviada).first().contexto
    assert contexto["condicion"] == "> 30.0000"
    assert contexto["valor"] == "35"


def test_actualizar_la_condicion_cambia_la_regla_de_la_lectura_siguiente(db_session, caso):
    """En alarma con > 30; se sube a > 50: 45 ya no es alarma y no avisa;
    55 sí, con la condición nueva en el aviso."""
    evaluar(db_session, caso, [Decimal("35")], inicio=0)
    assert avisos(db_session) == DESTINATARIOS

    actualizar_condicion(db_session, caso, ">", 50)
    estado = db_session.query(EstadoAlarma).one()
    db_session.refresh(estado)
    assert estado.en_alarma is False

    evaluar(db_session, caso, [Decimal("45")], inicio=10)
    assert avisos(db_session) == DESTINATARIOS

    evaluar(db_session, caso, [Decimal("55")], inicio=20)
    assert avisos(db_session) == 2 * DESTINATARIOS
    ultimo = (
        db_session.query(NotificacionEnviada).order_by(NotificacionEnviada.id_ntfccn.desc()).first()
    )
    assert ultimo.contexto["condicion"] == "> 50.0000"


def test_con_la_regla_nueva_vuelve_a_avisar_aunque_ya_estuviera_en_alarma(db_session, caso):
    """En alarma con > 30 (35). Se cambia a > 20: la evaluación arranca de
    cero, así que la lectura siguiente (25) avisa bajo la regla nueva."""
    evaluar(db_session, caso, [Decimal("35")], inicio=0)
    actualizar_condicion(db_session, caso, ">", 20)
    evaluar(db_session, caso, [Decimal("25")], inicio=10)
    assert avisos(db_session) == 2 * DESTINATARIOS


def test_misma_condicion_no_reinicia_ni_repite_el_aviso(db_session, caso):
    evaluar(db_session, caso, [Decimal("35")], inicio=0)
    actualizar_condicion(db_session, caso, ">", 30)  # sin cambios
    evaluar(db_session, caso, [Decimal("36")], inicio=10)
    assert avisos(db_session) == DESTINATARIOS


def test_alarma_antigua_con_dos_condiciones_sigue_evaluando(db_session, caso):
    """Alarmas creadas antes de PP-74: basta que se cumpla una (O)."""
    db_session.add(CondicionAlarma(id_alrm=caso["alarma"].id_alrm, oprdr="<", vlr_umbrl=5))
    db_session.flush()
    evaluar(db_session, caso, [Decimal("2")])
    assert avisos(db_session) == DESTINATARIOS
