"""
PP-68 - Consultar vencimientos (PP-314, PP-315, PP-316)

Tabla de vencimientos del Administrador Comercial para anticiparse a las
renovaciones. Lee los contratos con el mismo criterio que el resto del
módulo comercial (services/contratos.ultimo_contrato y estado_contrato).

"Clientes que tienen suscripción activa" (CA1): el contrato actual del
cliente en estado Vigente, En gracia o Vencida (vencido y todavía no
renovado). Si se excluyeran los vencidos, el filtro "vencidos" de la
conversación nunca mostraría nada. Quedan fuera los clientes sin plan, los
que solo tienen un plan programado a futuro y los contratos suspendidos o
cancelados.

Rangos de la conversación (días restantes = vencimiento - hoy en Lima):
  vencidos       días < 0
  hoy            días == 0
  7              0 <= días <= 7   (incluye hoy, excluye vencidos)
  30             0 <= días <= 30
  todos          sin filtro
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Cliente
from app.services.contratos import condiciones_de, estado_contrato, ultimo_contrato

ESTADOS_INCLUIDOS = {"Vigente", "En gracia", "Vencida"}
RANGOS = {
    "todos": lambda dias: True,
    "vencidos": lambda dias: dias < 0,
    "hoy": lambda dias: dias == 0,
    "7": lambda dias: 0 <= dias <= 7,
    "30": lambda dias: 0 <= dias <= 30,
}
MSG_RANGO = "Rango no válido. Usa: todos, vencidos, hoy, 7 o 30"


def vencimientos(db: Session, hoy: date, rango: str = "todos") -> list[dict]:
    if rango not in RANGOS:
        raise HTTPException(status_code=422, detail=MSG_RANGO)
    incluir = RANGOS[rango]
    filas = []
    for cliente in db.query(Cliente).filter(Cliente.estd == "Activo").all():
        contrato = ultimo_contrato(db, cliente.id_clnt, hoy)
        if contrato is None:
            continue
        estado = estado_contrato(db, contrato, hoy)
        if estado not in ESTADOS_INCLUIDOS:
            continue
        dias = (contrato.fch_vncmnt - hoy).days
        if not incluir(dias):
            continue
        filas.append(
            {
                "id_clnt": cliente.id_clnt,
                "razon_social": cliente.rzn_scl,
                "ruc": cliente.rc,
                "suscripcion_id": contrato.id_sscrpcn,
                "plan_nombre": condiciones_de(db, contrato).get("plan_nombre"),
                "fecha_inicio": contrato.fch_inc,
                "fecha_vencimiento": contrato.fch_vncmnt,
                "dias_restantes": dias,
                "estado": estado,
                # PP-316: la pantalla resalta estas filas.
                "vencida": dias < 0,
            }
        )
    # "Se ordena por fecha de vencimiento de forma ascendente mostrando
    # primero los más próximos a vencer." A igual fecha, por razón social.
    filas.sort(key=lambda fila: (fila["fecha_vencimiento"], fila["razon_social"].casefold()))
    return filas
