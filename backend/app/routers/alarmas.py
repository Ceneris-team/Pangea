"""
HU 27 - Listar alarmas

CA1: al cargar el módulo "Gestión de Alarmas y Notificaciones", se muestra
una tabla con todas las alarmas configuradas por el usuario, indicando
nombre de la alarma, parámetro asociado, condición, estado y acciones
(las acciones las arma el frontend a partir de id_alrm/estd, no viajan
como dato).

CA2: filtro por estado (Activa/Inactiva) que refresca la tabla.

CA3: búsqueda por nombre (insensible a mayúsculas) que refresca la tabla.

Detalle de la conversación:
  - Paginado de 10 registros por defecto -mismo criterio y misma forma de
    respuesta (total/pagina/por_pagina/items) que listar_dispositivos en
    routers/dispositivos.py-.
  - "Cada usuario solo puede ver y gestionar sus propias alarmas": a
    diferencia de Dispositivos/Ubicaciones, acá NO hay una vista
    "administrador ve todo" -Alarma.id_usr es el dueño, y el listado
    siempre filtra por el id_usr del token, para cualquier rol-. Por eso
    tampoco hace falta verificar_sede: el filtro por dueño ya aísla el
    recurso.
  - El caso "sin alarmas configuradas" (mensaje + botón 'Crear alarma'
    visible) es responsabilidad del frontend: este endpoint solo
    devuelve total=0 igual que cualquier listado vacío.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.alarma import Alarma, CondicionAlarma
from app.models.mapeo_dispositivo import Parametro
from app.schemas import AlarmaListItem
from app.security.permisos import LECTURA, require_permiso

router = APIRouter(prefix="/alarmas", tags=["Alarmas"])


def _formatear_condicion(condicion: CondicionAlarma | None, unidad: str) -> str | None:
    """'> 30 °C' a partir de oprdr/vlr_umbrl -la HU29 (configurar
    condición) es la que arma cndcn_alrm; acá solo se muestra.

    vlr_umbrl es Numeric(14,4): se formatea con 'g' para no arrastrar los
    ceros de relleno del tipo (30.0000 -> '30', 30.5000 -> '30.5')."""
    if condicion is None:
        return None
    valor = f"{float(condicion.vlr_umbrl):g}"
    return f"{condicion.oprdr} {valor} {unidad}".strip()


@router.get("")
def listar_alarmas(
    busqueda: str | None = Query(default=None, description="Nombre de la alarma, parcial"),
    estado: str | None = Query(default=None, description="Activa / Inactiva"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),  # CA: 10 por defecto
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Alarmas", LECTURA)),
):
    id_usr = int(usuario["sub"])

    query = (
        db.query(Alarma, Parametro.nmbr, Parametro.undd)
        .join(Parametro, Parametro.id_prmtr == Alarma.id_prmtr)
        .filter(Alarma.id_usr == id_usr)
    )

    if busqueda:
        query = query.filter(func.lower(Alarma.nmbr).like(f"%{busqueda.lower()}%"))
    if estado:
        query = query.filter(Alarma.estd == estado)

    total = query.count()
    filas = (
        query.order_by(Alarma.nmbr).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    )

    # Las condiciones de esta página, en una sola consulta (evita N+1).
    ids_alarma = [alarma.id_alrm for alarma, _nombre, _undd in filas]
    condiciones_por_alarma: dict[int, CondicionAlarma] = {}
    if ids_alarma:
        for condicion in (
            db.query(CondicionAlarma)
            .filter(CondicionAlarma.id_alrm.in_(ids_alarma))
            .order_by(CondicionAlarma.id_cndcn)
            .all()
        ):
            # Una alarma puede tener más de una condición (HU29); el
            # listado solo necesita una referencia rápida, así que se
            # queda con la primera encontrada.
            condiciones_por_alarma.setdefault(condicion.id_alrm, condicion)

    items = [
        AlarmaListItem(
            id_alrm=alarma.id_alrm,
            nmbr=alarma.nmbr,
            parametro_nombre=nombre_parametro,
            condicion=_formatear_condicion(condiciones_por_alarma.get(alarma.id_alrm), unidad),
            estd=alarma.estd,
        )
        for alarma, nombre_parametro, unidad in filas
    ]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}
