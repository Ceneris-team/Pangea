"""
PP-67 - Registrar cobro (PP-312, PP-313)

Registro manual de los pagos que hace un cliente por su suscripción, para
la trazabilidad financiera. No genera cobros ni cambia el contrato: el
motor de contratos (services/contratos.py) sigue tratando los importes
como condiciones comerciales.

Detalles de la conversación:
  - Obligatorios: Monto cobrado, Fecha de cobro y Método de pago.
  - El monto es un valor numérico decimal.
  - Métodos de pago en v1.0: transferencia bancaria, efectivo y cheque.
  - La fecha de cobro no puede ser futura.

"Asociado al cliente y al período correspondiente" (CA2): cbr cuelga de
sscrpcn, que es el período contratado. El cobro se asocia al contrato
actual del cliente (el que muestra su tarjeta); el formulario de la HU no
pide elegir período.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Cobro, Suscripcion
from app.services.contratos import condiciones_de, ultimo_contrato

METODOS_PAGO = ("Transferencia bancaria", "Efectivo", "Cheque")
# cbr.mnt es Numeric(12, 2): hasta 10 enteros y 2 decimales.
MONTO_MAXIMO = Decimal("9999999999.99")

MSG_MONTO = "El monto cobrado debe ser un número mayor que 0 con hasta 2 decimales"
MSG_MONTO_MAXIMO = "El monto cobrado no puede superar 9 999 999 999.99"
MSG_FECHA = "Indica la fecha de cobro en formato AAAA-MM-DD"
MSG_FECHA_FUTURA = "La fecha de cobro no puede ser futura"
MSG_METODO = "Elige un método de pago: Transferencia bancaria, Efectivo o Cheque"
MSG_SIN_PLAN = "El cliente no tiene un plan asignado"
MSG_COBRO_REGISTRADO = "Cobro registrado correctamente"


def _monto(valor) -> Decimal:
    if valor is None or isinstance(valor, bool) or str(valor).strip() == "":
        raise HTTPException(status_code=422, detail=MSG_MONTO)
    try:
        monto = Decimal(str(valor).strip())
    except InvalidOperation:
        raise HTTPException(status_code=422, detail=MSG_MONTO) from None
    if not monto.is_finite() or monto <= 0 or monto.as_tuple().exponent < -2:
        raise HTTPException(status_code=422, detail=MSG_MONTO)
    if monto > MONTO_MAXIMO:
        raise HTTPException(status_code=422, detail=MSG_MONTO_MAXIMO)
    return monto.quantize(Decimal("0.01"))


def _fecha(valor, hoy: date) -> date:
    try:
        fecha = date.fromisoformat(str(valor or "").strip())
    except ValueError:
        raise HTTPException(status_code=422, detail=MSG_FECHA) from None
    # Se compara con el día comercial de Lima (fecha_comercial), no con el
    # reloj del servidor; el CHECK de cbr queda como respaldo en la base.
    if fecha > hoy:
        raise HTTPException(status_code=422, detail=MSG_FECHA_FUTURA)
    return fecha


def _metodo(valor) -> str:
    texto = str(valor or "").strip()
    for metodo in METODOS_PAGO:
        if texto.casefold() == metodo.casefold():
            return metodo
    raise HTTPException(status_code=422, detail=MSG_METODO)


def registrar_cobro(
    db: Session, id_clnt: int, *, monto, fecha_cobro, metodo_pago, hoy: date
) -> Cobro:
    """Valida y agrega el cobro a la sesión (flush, sin commit)."""
    monto = _monto(monto)
    fecha = _fecha(fecha_cobro, hoy)
    metodo = _metodo(metodo_pago)
    contrato = ultimo_contrato(db, id_clnt, hoy)
    if contrato is None:
        raise HTTPException(status_code=409, detail=MSG_SIN_PLAN)
    cobro = Cobro(id_sscrpcn=contrato.id_sscrpcn, mnt=monto, fch_cbr=fecha, mtd_pg=metodo)
    db.add(cobro)
    db.flush()
    return cobro


def cobro_dict(db: Session, cobro: Cobro, contrato: Suscripcion) -> dict:
    return {
        "id": cobro.id_cbr,
        "monto": str(cobro.mnt),
        "moneda": condiciones_de(db, contrato).get("moneda", "PEN"),
        "fecha_cobro": cobro.fch_cbr,
        "metodo_pago": cobro.mtd_pg,
        "fecha_registro": cobro.fch_rgstr,
        "suscripcion_id": contrato.id_sscrpcn,
        "plan_nombre": condiciones_de(db, contrato).get("plan_nombre"),
        "periodo_inicio": contrato.fch_inc,
        "periodo_fin": contrato.fch_vncmnt,
    }


def historial_cobros(db: Session, id_clnt: int) -> list[dict]:
    """HU CA3: cobros del cliente, el más reciente primero."""
    filas = (
        db.query(Cobro, Suscripcion)
        .join(Suscripcion, Suscripcion.id_sscrpcn == Cobro.id_sscrpcn)
        .filter(Suscripcion.id_clnt == id_clnt)
        .order_by(Cobro.fch_cbr.desc(), Cobro.id_cbr.desc())
        .all()
    )
    return [cobro_dict(db, cobro, contrato) for cobro, contrato in filas]
