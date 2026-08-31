"""
HT-11 CA2/CA3/CA4 - Consulta de auditoría, de solo lectura.

Expone ÚNICAMENTE un GET: no existe (ni existirá, ver CA3) ningún
PUT/PATCH/DELETE sobre `lg_adtr` en este router ni en ningún otro. La
inmutabilidad a nivel de aplicación que pide CA3 es, literalmente, la
ausencia de esos endpoints -no hay nada que "bloquear", basta con no
escribirlos-; el resto de la garantía (que tampoco se pueda hacer un
UPDATE/DELETE por fuera de un endpoint, vía ORM directo) se documenta en
backend/README.md junto con el script de GRANT/REVOKE a nivel de base de
datos (punto 6 de HT-11).

Módulo elegido para require_permiso: "Usuarios", con nivel EDICIÓN -no
LECTURA-. El CHECK constraint de prms_usr_sd (HT-03) no tiene un módulo
"Auditoría"; entre los 7 válidos, "Usuarios" es el que more corresponde,
porque todo lo auditado hoy (HU20 edición de usuario, HU21 permisos,
accesos denegados de HT-09) son operaciones DEL módulo Usuarios. Se exige
EDICIÓN y no LECTURA a propósito: en el seed de PERMISOS_POR_ROL, Técnico
CENERIS tiene "Usuarios: Lectura" (para ver el listado de HU03), y el CA2
de esta HT dice explícitamente "accesible ÚNICAMENTE para Administrador".
Hoy edición en Usuarios = Administrador, exactamente el conjunto pedido,
sin hardcodear el nombre del rol (mismo criterio que ya usan
crear_usuario/actualizar_usuario en routers/usuarios.py).
"""

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogAuditoria, Usuario
from app.schemas import AuditoriaListItem
from app.security.permisos import EDICION, require_permiso

router = APIRouter(prefix="/auditoria", tags=["Auditoría"])


@router.get("")
def listar_auditoria(
    sede_id: int | None = Query(default=None, description="Filtra por id de sede"),
    usuario_id: int | None = Query(default=None, description="Filtra por id del usuario ejecutor"),
    fecha_inicio: dt.datetime | None = Query(default=None),
    fecha_fin: dt.datetime | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),  # mismo default que HU03/HU07
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Usuarios", EDICION)),
):
    """CA2: filtra por sede, usuario y rango de fechas; accesible
    únicamente para Administrador (ver el módulo elegido arriba).

    CA4 + advertencia de HT-04 sobre sede_id=None en el JWT: un
    Administrador con scope "global" (el caso normal, ver seed) ve TODO el
    histórico, igual que ya hace verificar_sede() para cualquier otro
    recurso con scope global. Un Administrador con scope "por_sede" -el
    esquema lo permite aunque el seed no siembre ninguno así- queda
    restringido a su propia sede, mismo criterio que tiene_permiso().

    Decisión explícita sobre id_sd IS NULL (puede ocurrir si HT-04 emite un
    token sin sede_id, o en cualquier evento de un usuario con scope
    "global" -ver security/auditoria.py-): un registro con id_sd NULL
    representa "sin sede asociada", no "cualquier sede". Por eso:
      - Un Administrador con scope "global" SÍ los ve (junto con todo lo
        demás: no hay restricción de sede que aplicarle).
      - Un Administrador con scope "por_sede" NUNCA los ve: su sede propia,
        sea cual sea, no es "ninguna sede", así que NULL no matchea.
      - Si se filtra explícitamente por `sede_id=<n>`, los NULL quedan
        excluidos también para el Administrador global: pidió una sede
        concreta, y NULL no es esa sede.
    No se corrige acá el bug de HT-04 que puede producir sede_id=None en el
    JWT -queda fuera de alcance de esta HT-; esto solo fija qué hace la
    auditoría cuando ese caso ya ocurrió.
    """
    query = db.query(LogAuditoria).join(Usuario, LogAuditoria.id_usr == Usuario.id_usr)

    if usuario.get("scope") != "global":
        # CA4: aislamiento por sede para un Administrador "por_sede". NULL
        # no matchea ninguna sede propia (ver docstring de arriba).
        query = query.filter(LogAuditoria.id_sd == usuario.get("sede_id"))

    if sede_id is not None:
        query = query.filter(LogAuditoria.id_sd == sede_id)
    if usuario_id is not None:
        query = query.filter(LogAuditoria.id_usr == usuario_id)
    if fecha_inicio is not None:
        query = query.filter(LogAuditoria.fch_evnt >= fecha_inicio)
    if fecha_fin is not None:
        query = query.filter(LogAuditoria.fch_evnt <= fecha_fin)

    total = query.count()
    # LogAuditoria no declara una relationship a Usuario -el modelo, ya
    # existente antes de esta HT, solo tiene el ForeignKey (ver
    # models/varios.py)-, así que el nombre se trae con .add_columns() en
    # vez de asumir un atributo .usuario que no existe.
    registros = (
        query.add_columns(Usuario.nmbr_cmplt)
        .order_by(LogAuditoria.fch_evnt.desc(), LogAuditoria.id_evnt.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    items = [
        AuditoriaListItem(
            id_evnt=r.id_evnt,
            id_usr=r.id_usr,
            usuario_nombre=nombre,
            id_sd=r.id_sd,
            accn=r.accn,
            entdd=r.entdd,
            vlrs_antrrs=r.vlrs_antrrs,
            vlrs_nvs=r.vlrs_nvs,
            fch_evnt=r.fch_evnt,
        )
        for r, nombre in registros
    ]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}
