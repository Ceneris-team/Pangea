from sqlalchemy import BigInteger, Column, Integer, ForeignKey, Index, Numeric, TIMESTAMP

from app.database import Base


class Telemetria(Base):
    """HT-08: lectura de sensor. Particionada por rango mensual de fch_hr
    (las particiones mensuales se crean a mano en la migración, ya que
    Alembic no las genera automáticamente). La PK compuesta (id_lctr,
    fch_hr) es requisito de Postgres: la columna de partición debe formar
    parte de toda unique/primary key de la tabla particionada."""
    __tablename__ = "tlmtr"
    __table_args__ = (
        Index("idx_tlmtr_fchhr_brin", "fch_hr", postgresql_using="brin"),
        Index("idx_tlmtr_dspstv_prmtr", "id_dspstv", "id_prmtr", "fch_hr"),
        Index("idx_tlmtr_sd", "id_sd", "fch_hr"),
        {"postgresql_partition_by": "RANGE (fch_hr)"},
    )

    id_lctr = Column(BigInteger, primary_key=True, autoincrement=True)
    fch_hr = Column(TIMESTAMP(timezone=True), primary_key=True, nullable=False)
    id_dspstv = Column(Integer, ForeignKey("dspstv.id_dspstv"), nullable=False)
    id_prmtr = Column(Integer, ForeignKey("prmtr.id_prmtr"), nullable=False)
    id_sd = Column(Integer, ForeignKey("sd.id_sd"), nullable=False)
    vlr = Column(Numeric(14, 4), nullable=False)
    id_archv = Column(BigInteger, ForeignKey("archv_ingst.id_archv"))
