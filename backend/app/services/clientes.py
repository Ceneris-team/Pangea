"""
HU 65 - Registrar cliente (PP-305, PP-306, PP-307)

Alta de un cliente (empresa minera) compartida por los dos lugares que la
ofrecen: «Gestión de Planes y Suscripciones» (Administrador Comercial,
POST /comercial/clientes) y «Empresas y proyectos» (administración CENERIS,
POST /empresas). Cada router decide quién puede registrar y audita; acá
solo vive la regla de negocio del registro, para que las dos pantallas no
validen distinto.

Detalles de la conversación de HU65:
  - Obligatorios: Razón social, RUC y Correo de contacto. Teléfono opcional.
  - El RUC tiene exactamente 11 dígitos numéricos y es único en el sistema.
  - El correo tiene formato usuario@dominio.com.

Las validaciones devuelven un 422 con un mensaje en español (no la lista de
errores de Pydantic) porque el formulario lo muestra tal cual.
"""

import re

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Cliente

RUC = re.compile(r"\d{11}")
# usuario@dominio.tld: sin espacios, una sola arroba y al menos un punto en
# el dominio. Es la regla de la HU, no la RFC completa.
CORREO = re.compile(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+")
# La HU no fija un formato. Se aceptan los separadores habituales de un
# teléfono peruano o internacional (+51 999 999 999, 01-555-1234) y se exige
# al menos un dígito. 20 es el largo de clnt.tlfn_cntct.
TELEFONO = re.compile(r"[0-9+\- ]{1,20}")

MSG_RAZON_SOCIAL = "La razón social es obligatoria"
MSG_RAZON_SOCIAL_LARGA = "La razón social admite como máximo 200 caracteres"
MSG_RUC = "El RUC debe tener exactamente 11 dígitos numéricos"
MSG_RUC_DUPLICADO = "Ya existe un cliente con ese RUC"
MSG_CORREO = "El correo de contacto debe tener el formato usuario@dominio.com"
MSG_TELEFONO = "El teléfono de contacto solo admite números, espacios, + y - (máximo 20 caracteres)"


def _validar(razon_social: str, ruc: str, correo: str, telefono: str | None) -> tuple:
    razon_social = (razon_social or "").strip()
    if not razon_social:
        raise HTTPException(status_code=422, detail=MSG_RAZON_SOCIAL)
    if len(razon_social) > 200:
        raise HTTPException(status_code=422, detail=MSG_RAZON_SOCIAL_LARGA)

    ruc = (ruc or "").strip()
    if not RUC.fullmatch(ruc):
        raise HTTPException(status_code=422, detail=MSG_RUC)

    correo = (correo or "").strip().lower()
    if len(correo) > 150 or not CORREO.fullmatch(correo):
        raise HTTPException(status_code=422, detail=MSG_CORREO)

    telefono = (telefono or "").strip() or None
    if telefono is not None and not (
        TELEFONO.fullmatch(telefono) and any(c.isdigit() for c in telefono)
    ):
        raise HTTPException(status_code=422, detail=MSG_TELEFONO)

    return razon_social, ruc, correo, telefono


def registrar_cliente(
    db: Session, *, razon_social: str, ruc: str, correo: str, telefono: str | None = None
) -> Cliente:
    """Valida y agrega el cliente a la sesión (flush, sin commit).

    El commit lo hace el router después de auditar, para que el cliente y
    su registro de auditoría entren juntos o no entre ninguno.
    """
    razon_social, ruc, correo, telefono = _validar(razon_social, ruc, correo, telefono)

    # Se consulta antes de insertar para dar el 409 con el mensaje de la HU
    # en el caso normal; el UNIQUE de clnt.rc sigue cubriendo dos altas
    # simultáneas con el mismo RUC (IntegrityError, abajo).
    if db.query(Cliente.id_clnt).filter(Cliente.rc == ruc).first() is not None:
        raise HTTPException(status_code=409, detail=MSG_RUC_DUPLICADO)

    cliente = Cliente(rzn_scl=razon_social, rc=ruc, crr_cntct=correo, tlfn_cntct=telefono)
    db.add(cliente)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=MSG_RUC_DUPLICADO) from None
    return cliente
