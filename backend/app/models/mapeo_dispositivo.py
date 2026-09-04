from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)

from app.database import Base


class MapeoFormato(Base):
    """HU 06: mini-ETL por DISPOSITIVO (DEC-09).

    Un datalogger manda varios formatos distintos de archivo, con distinto
    número y significado de columnas, y por eso el formato se identifica
    por dispositivo + tipo de trama (PP-96):

      tp_trm='H' -> archivos H_*.dat: datos periódicos (lectura real)
      tp_trm='E' -> archivos E_*.dat: estados y eventos del equipo
      tp_trm='P' -> archivos P_*.dat: eventos de puerta/acceso

    tp_trm YA NO es un catálogo cerrado: el equipo de telemetría configura
    dataloggers con prefijos de archivo distintos según el proyecto, y
    exigir una migración + deploy por cada letra nueva no escala. H/E/P de
    arriba son simplemente los primeros valores cargados -no reciben trato
    especial en el modelo ni en el motor de ingesta-; el único chequeo de
    formato (una letra A-Z) vive en _validar_tipo_trama (routers/mapeos.py),
    y services/ingesta/mapeo.py resuelve el prefijo del archivo consultando
    los mp_frmt activos del dispositivo en vez de un diccionario fijo.

    DEC-09: antes el formato colgaba de (id_sd, mrc). Dos dataloggers de
    la misma marca en la misma sede, pero con sensores distintos
    conectados, compartían mapeo y las lecturas del segundo se guardaban
    bajo el parámetro equivocado, sin ningún error visible. Cada
    datalogger tiene su propia carpeta FTP exclusiva (cnxn_ftp, HU05) y
    un único dispositivo activo asociado (HU11), así que el dispositivo
    es la unidad correcta para colgar el mapeo. La marca y la sede se
    derivan del dispositivo (Dispositivo.mrc, Ubicacion.id_sd) en vez de
    duplicarse acá.
    """

    __tablename__ = "mp_frmt"
    __table_args__ = (
        # Sin CHECK de valores fijos: tp_trm es una letra libre validada en
        # el router (_validar_tipo_trama), no un catálogo cerrado en la BD.
        CheckConstraint("dlmtdr_dcml IN ('.', ',')", name="mpfrmt_dlmtdrdcml_check"),
        CheckConstraint("orgn_crcn IN ('Manual','Automatico')", name="mpfrmt_orgncrcn_check"),
        # Un dispositivo puede tener como máximo un mapeo ACTIVO por tipo
        # de trama (uno H y uno E). El parcial sobre estd deja convivir
        # versiones anteriores desactivadas del mismo mapeo; se declara
        # como Index con postgresql_where porque UniqueConstraint no
        # admite condición.
        Index(
            "uq_mpfrmt_dspstv_tptrm_activo",
            "id_dspstv",
            "tp_trm",
            unique=True,
            postgresql_where=text("estd = 'Activo'"),
        ),
        Index("idx_mpfrmt_dspstv", "id_dspstv"),
    )

    id_mp = Column(Integer, primary_key=True, autoincrement=True)
    id_dspstv = Column(Integer, ForeignKey("dspstv.id_dspstv"), nullable=False)
    # HU49: el prefijo real es "todo antes del primer '_' del nombre de
    # archivo" (ver extraer_prefijo en services/ingesta/mapeo.py), no una
    # sola letra - String(50) da margen sobre nombres de datalogger reales.
    tp_trm = Column(String(50), nullable=False, server_default="H")
    # Descripción corta y libre de qué es esta trama (p. ej. "Nivel de
    # napa" para una letra que el técnico de telemetría definió). Antes
    # de que tp_trm fuera libre no hacía falta -H/E/P se explicaban solos
    # en la UI-; con letras arbitrarias, sin esto nadie sabe qué es "X"
    # sin abrir el mapeo.
    dscrpcn = Column(String(200))
    dlmtdr = Column(String(5), nullable=False, server_default=",")
    # Separador decimal del propio dato numérico, independiente del
    # delimitador de columna: un datalogger en locale europeo manda
    # "23,5" con ';' de separador. El motor lo normaliza antes de float()
    # (ver services/ingesta/validador.py).
    dlmtdr_dcml = Column(String(1), nullable=False, server_default=".")
    fl_inc_dts = Column(Integer, nullable=False, server_default="1")
    frmt_fch = Column(String(50), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Activo")
    # HU49 CA3: distingue una trama que un Técnico configuró a mano de una
    # que el pipeline creó solo porque llegó un prefijo nunca visto (ver
    # resolver_formato/_crear_mapeo_formato_automatico en
    # services/ingesta/mapeo.py). server_default='Manual' porque toda
    # trama configurada ANTES de HU49 lo fue a mano.
    orgn_crcn = Column(String(20), nullable=False, server_default="Manual")


class Parametro(Base):
    """tipo_dato distingue una MEDICIÓN numérica (tlmtr.vlr es
    Numeric(14,4) NOT NULL, no admite texto) de un EVENTO de texto (ej.
    "MensajeP"/"MensajeA" de una trama de puerta: "Puerta Abierta", "Llave
    No Encontrada"). Antes de esto todo parámetro se validaba como
    número (validador._parsear_numero); un parámetro de texto perdía cada
    fila en silencio porque float("Puerta Abierta") siempre falla.

    Un parámetro de tipo 'texto' se persiste en evnt_txt (ver
    EventoTexto), no en tlmtr -no se puede simplemente volver tlmtr.vlr
    texto/nullable: es una tabla particionada con datos reales, y
    mezclar mediciones numéricas con mensajes de texto en la misma
    columna rompería las consultas/alarmas que asumen vlr numérico."""

    __tablename__ = "prmtr"
    __table_args__ = (
        CheckConstraint("tipo_dato IN ('numerico','texto')", name="prmtr_tipodato_check"),
        CheckConstraint(
            "estd IN ('Activo','Pendiente de revision','Fusionado')",
            name="prmtr_estd_check",
        ),
        CheckConstraint(
            "orgn_crcn IN ('Manual','Automatico')", name="prmtr_orgncrcn_check"
        ),
    )

    id_prmtr = Column(Integer, primary_key=True, autoincrement=True)
    nmbr = Column(String(100), nullable=False, unique=True)
    undd = Column(String(30), nullable=False)
    dscrpcn = Column(String(200))
    tipo_dato = Column(String(10), nullable=False, server_default="numerico")

    # HU51. 'Pendiente de revision' = auto-creado por el motor de ingesta a
    # partir de una columna sin match (CA1), a la espera de que un
    # Administrador le ponga nombre/unidad de verdad y lo Active (CA4).
    # 'Fusionado' = soft delete de CA5: sus datos ya se reasignaron a
    # id_prmtr_fusionado_en y NUNCA debe volver a aparecer en un selector
    # ni ser reutilizado por el auto-mapeo. Se guarda en vez de borrar la
    # fila para no perder el rastro de que ese texto de header existió y
    # qué decidió el Administrador con él.
    # Sin acento en 'revision' a propósito: el resto de los estados del
    # proyecto (Activo/Inactivo/Pendiente/Resuelta/Ignorada) no usan
    # acentos, y así se evita depender del encoding en comparaciones.
    estd = Column(String(30), nullable=False, server_default="Activo")
    orgn_crcn = Column(String(20), nullable=False, server_default="Manual")
    id_prmtr_fusionado_en = Column(Integer, ForeignKey("prmtr.id_prmtr"), nullable=True)


class MapeoColumna(Base):
    """Columna del archivo -> parámetro (HU 06)."""

    __tablename__ = "mp_clmn"
    __table_args__ = (UniqueConstraint("id_mp", "indc_clmn", name="uq_mpclmn_mp_indccolmn"),)

    id_mp_cl = Column(Integer, primary_key=True, autoincrement=True)
    id_mp = Column(Integer, ForeignKey("mp_frmt.id_mp"), nullable=False)
    indc_clmn = Column(Integer, nullable=False)
    id_prmtr = Column(Integer, ForeignKey("prmtr.id_prmtr"), nullable=False)


class MapeoColumnaPendiente(Base):
    """HU50 CA3/CA6: columna del header de un archivo que el auto-mapeo
    (construir_mapeo, services/ingesta/mapeo.py) no pudo asociar a ningún
    prmtr.nmbr por coincidencia exacta de nombre normalizado.

    Separada de MapeoColumna (no un id_prmtr nullable ahí) para no
    introducir nulidad en la tabla que el pipeline de ingesta consulta en
    caliente en cada archivo (construir_mapeo, tipos_de_parametro): una
    fila acá NUNCA es un mapeo válido, así que cualquier código que
    itere/joinee MapeoColumna sigue pudiendo asumir id_prmtr siempre
    presente.

    El UNIQUE(id_mp, indc_clmn) es la pieza que garantiza CA6: una vez que
    existe una fila para esa columna, nunca se vuelve a evaluar
    automáticamente, sea cual sea su estd."""

    __tablename__ = "mp_clmn_pendiente"
    __table_args__ = (
        CheckConstraint(
            "estd IN ('Pendiente','Resuelta','Ignorada')", name="mpclmnpnd_estd_check"
        ),
        UniqueConstraint("id_mp", "indc_clmn", name="uq_mpclmnpnd_mp_indccolmn"),
        Index("idx_mpclmnpnd_mp_estd", "id_mp", "estd"),
    )

    id_mp_cl_pnd = Column(Integer, primary_key=True, autoincrement=True)
    id_mp = Column(Integer, ForeignKey("mp_frmt.id_mp"), nullable=False)
    indc_clmn = Column(Integer, nullable=False)
    nmbr_clmn_orgn = Column(String(200), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Pendiente")
    fch_dtccn = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    fch_resolucion = Column(TIMESTAMP(timezone=True), nullable=True)
    id_usr_resolvio = Column(Integer, ForeignKey("usr.id_usr"), nullable=True)


class Dispositivo(Base):
    """HU 10-11, HU 18-19, HU 36.

    DEC-09: ya no lleva id_mp. Un dispositivo puede tener 0, 1 o 2 mapeos
    de formato (uno por tipo de trama), así que la relación no cabe en una
    sola FK; vive del lado de MapeoFormato.id_dspstv.
    """

    __tablename__ = "dspstv"
    __table_args__ = (
        CheckConstraint("lttd BETWEEN -90 AND 90", name="dspstv_lttd_check"),
        CheckConstraint("lngtd BETWEEN -180 AND 180", name="dspstv_lngtd_check"),
        Index("idx_dspstv_ubccn", "id_ubccn"),
    )

    id_dspstv = Column(Integer, primary_key=True, autoincrement=True)
    id_ubccn = Column(Integer, ForeignKey("ubccn.id_ubccn"), nullable=False)
    id_cnxn = Column(Integer, ForeignKey("cnxn_ftp.id_cnxn"), nullable=False)
    nmbr = Column(String(150), nullable=False)
    mrc = Column(String(100), nullable=False)
    mdl = Column(String(100))
    lttd = Column(Numeric(9, 6), nullable=False)
    lngtd = Column(Numeric(9, 6), nullable=False)
    estd = Column(String(20), nullable=False, server_default="Activo")
    fch_rgstr = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
