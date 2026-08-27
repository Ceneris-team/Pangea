"""
HU 21 - Filtro de visibilidad de ubicaciones por usuario.

Regla única: Administrador y Técnico CENERIS ven TODAS las ubicaciones;
cualquier otro rol (en la práctica, Cliente Final) ve solo las que le
fueron asignadas explícitamente en prms_ubccn.

Este módulo existe porque esa regla la necesitan varios routers a la vez
(mediciones/HU13, mapa del cliente/HU17, y el mismo criterio está
replicado en ubicaciones/HU07 y dispositivos/HU10 sobre otras entidades).
Vivía como función privada `_ubicaciones_permitidas` dentro de
routers/mediciones.py; se movió acá tal cual -mismo comportamiento- para
que HU 17 la REUTILICE en vez de copiarla, que era la vía directa a que
las dos se desincronizaran y el mapa terminara mostrando ubicaciones que
la consulta de datos no muestra (o al revés).

Vive en security/ y no en services/ a propósito: es una regla de ACCESO,
vecina de permisos.py, no de presentación.
"""

from sqlalchemy.orm import Session

from app.models import PermisoUbicacion, Ubicacion

# Incluye "Tecnico CENERIS" sin tilde además de "Técnico CENERIS": el rol
# viaja en el JWT como texto y ambas grafías han aparecido en datos
# sembrados. Se conserva tal como estaba en mediciones.py -corregir la
# fuente de los datos es otra tarea, y quitar la variante sin tilde acá
# dejaría a esos usuarios sin acceso de golpe.
ROLES_CON_ACCESO_TOTAL = {"Administrador", "Tecnico CENERIS", "Técnico CENERIS"}


def ubicaciones_permitidas(db: Session, usuario: dict) -> list:
    """Ids de las ubicaciones que este usuario puede ver (HU 21).

    `usuario` es el payload del JWT (ver security/jwt_auth.py), así que
    esta función sirve igual desde una dependencia HTTP normal y desde el
    endpoint WebSocket de HU 17, que valida el token a mano.
    """
    query = db.query(Ubicacion.id_ubccn)
    if usuario.get("rol") not in ROLES_CON_ACCESO_TOTAL:
        id_usr = int(usuario["sub"])
        query = query.join(
            PermisoUbicacion, PermisoUbicacion.id_ubccn == Ubicacion.id_ubccn
        ).filter(PermisoUbicacion.id_usr == id_usr)
    return [row[0] for row in query.all()]
