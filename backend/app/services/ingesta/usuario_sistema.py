"""
HU49 CA5: resuelve el id_usr del usuario "Sistema" sembrado por migración
(ver alembic/versions/a070693e2870_...), para que la auditoría de una
creación automática de mp_frmt (que ocurre dentro de una tarea de Celery,
sin request HTTP ni JWT) tenga un id_usr válido -lg_adtr.id_usr es NOT
NULL, así que no hay forma de auditar "nadie" sin este usuario fijo.
"""

from sqlalchemy.orm import Session

from app.models import Usuario

# Debe coincidir exactamente con el correo sembrado en la migración
# a070693e2870_hu49_seed_usuario_sistema_para_. Un solo lugar (esta
# constante) define el contrato entre la migración y este módulo.
CORREO_USUARIO_SISTEMA = "sistema.ingesta@pangea.internal"


def resolver_id_usuario_sistema(db: Session) -> int:
    """Busca por correo (índice único) en vez de cachear el id: es una
    consulta barata, y evita servir un id obsoleto si alguna vez se
    resiembra el usuario Sistema en otro entorno con un id distinto."""
    usuario = db.query(Usuario).filter(Usuario.crr == CORREO_USUARIO_SISTEMA).first()
    if usuario is None:
        raise RuntimeError(
            f"No existe el usuario Sistema ('{CORREO_USUARIO_SISTEMA}'); "
            f"falta correr la migración de seed (HU49, "
            f"a070693e2870_hu49_seed_usuario_sistema_para_)."
        )
    return usuario.id_usr
