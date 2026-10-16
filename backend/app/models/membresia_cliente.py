from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base


class UsuarioCliente(Base):
    """Rol de una persona dentro de una empresa; no otorga acceso global."""

    __tablename__ = "usr_clnt"
    __table_args__ = (
        UniqueConstraint("id_usr", "id_clnt", name="uq_usrclnt_usr_clnt"),
        CheckConstraint("rol_emp IN ('Administrador','Tecnico','Lector')", name="usrclnt_rol_check"),
        CheckConstraint("estd IN ('Activo','Inactivo')", name="usrclnt_estd_check"),
    )

    id_mmb = Column(Integer, primary_key=True, autoincrement=True)
    id_usr = Column(Integer, ForeignKey("usr.id_usr"), nullable=False)
    id_clnt = Column(Integer, ForeignKey("clnt.id_clnt"), nullable=False)
    rol_emp = Column(String(20), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Activo")


class UsuarioProyecto(Base):
    """Acceso directo al proyecto geográfico, sin agrupador intermedio."""

    __tablename__ = "usr_pryct_ubccn"
    __table_args__ = (UniqueConstraint("id_mmb", "id_ubccn", name="uq_usrpryctubccn_mmb_ubccn"),)

    id_usr_pryct = Column(Integer, primary_key=True, autoincrement=True)
    id_mmb = Column(Integer, ForeignKey("usr_clnt.id_mmb", ondelete="CASCADE"), nullable=False)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)
