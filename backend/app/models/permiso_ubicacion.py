from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint

from app.database import Base


class PermisoUbicacion(Base):
    """HU 21: ubicaciones específicas a las que un usuario Cliente tiene acceso.
    Se usa ya en HU 07 para filtrar el listado cuando el rol es 'Cliente'."""

    __tablename__ = "prms_ubccn"
    __table_args__ = (UniqueConstraint("id_usr", "id_ubccn", name="uq_prmsubccn_usr_ubccn"),)

    id_prms_ubc = Column(Integer, primary_key=True, autoincrement=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)
