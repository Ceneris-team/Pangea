"""
PP-96 (HU06): resuelve, para un archivo .dat concreto, qué formato aplica
y cómo se traduce cada columna a un parámetro estándar.

Es la pieza que reemplaza el mapeo mock de estandarizador.py. Dos
decisiones de negocio la definen:

1. El TIPO DE TRAMA sale del PREFIJO del nombre del archivo: todo el
   texto antes del primer '_' (ver extraer_prefijo más abajo). H_*.dat,
   E_*.dat, P_*.dat son los primeros ejemplos que existieron -datos
   periódicos, estados/eventos, puerta/acceso-, pero el prefijo ya NO es
   un catálogo fijo en código ni está limitado a una letra: el técnico de
   telemetría lo define al crear el mapeo (ver _validar_tipo_trama en
   routers/mapeos.py), y detectar_tipo_trama resuelve contra los tp_trm
   que el DISPOSITIVO tiene realmente configurados en mp_frmt.

   HU49: si el prefijo de un archivo entrante no coincide con NINGÚN
   tp_trm activo de ese dispositivo, resolver_formato crea automática-
   mente un mp_frmt nuevo para ese prefijo (ver
   _crear_mapeo_formato_automatico), en vez de rechazar el archivo. Solo
   se rechaza (MapeoNoEncontradoError) si el nombre no tiene NINGÚN '_'
   -sin eso no hay forma de aislar qué prefijo probar-.

2. El MAPEO columna->parámetro sale de mp_clmn, que referencia la columna
   por su ÍNDICE (indc_clmn), no por su nombre. Es a propósito: los
   archivos de campo traen headers con nombres inconsistentes o
   repetidos, y el índice es estable frente a eso.

   HU50: construir_mapeo además intenta auto-completar mp_clmn para las
   columnas del header que todavía no tienen fila ahí, comparando el
   nombre de columna (normalizado) contra prmtr.nmbr (normalizado). Las
   que no matchean quedan registradas en mp_clmn_pendiente para
   resolución manual, una sola vez por columna (ver docstring de
   construir_mapeo).
"""

import dataclasses
import logging
import os

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.mapeo_dispositivo import (
    MapeoColumna,
    MapeoColumnaPendiente,
    MapeoFormato,
    Parametro,
)
from app.services.ingesta.parser import ConfiguracionParseo

logger = logging.getLogger(__name__)

# HU49: valores de parseo por defecto para una trama recién auto-creada.
# resolver_formato corre ANTES de descargar el archivo (ver
# tasks/ingesta.py), así que no hay forma de conocer el delimitador o el
# formato de fecha reales del datalogger todavía -son los mismos valores
# que ya usa server_default en MapeoFormato para dlmtdr/dlmtdr_dcml/
# fl_inc_dts, y un formato de fecha ISO razonable como punto de partida-.
# Si el datalogger real usa otra convención, el archivo falla en el
# parseo/validación (queda 'Fallido' en la Cola de Ingesta, HU09) y el
# Técnico ajusta el Formato a mano desde la pestaña correspondiente,
# igual que ya hace hoy con cualquier mp_frmt creado manualmente.
_DELIMITADOR_DEFECTO_AUTO = ","
_DELIMITADOR_DECIMAL_DEFECTO_AUTO = "."
# 1, no 2: fila_inicio_datos es un OFFSET desde la fila de header (ver
# parser.py, indice_inicio = indice_header + fila_inicio_datos), así que
# 1 es "la fila justo después del header" -exactamente el caso de 1 fila
# de header seguida de datos-. Con 2 se saltaría la primera fila de datos
# real (bug encontrado en la verificación funcional de HU49: un archivo
# de header + 1 sola fila de dato daba 'guardadas: 0' en vez de 1).
_FILA_INICIO_DATOS_DEFECTO_AUTO = 1
_FORMATO_FECHA_DEFECTO_AUTO = "%Y-%m-%d %H:%M:%S"


class MapeoNoEncontradoError(Exception):
    """No hay un mp_frmt activo para ese dispositivo + tipo de trama.

    Es un error de configuración, no transitorio: reintentar no lo
    resuelve. El llamador debe tratarlo como error de datos (ver
    app.tasks.ingesta)."""


@dataclasses.dataclass
class FormatoResuelto:
    """El formato aplicable a un archivo, resuelto ANTES de parsearlo.

    El mapeo columna->parámetro no va aquí: mp_clmn referencia columnas
    por índice, así que hace falta el header ya leído para traducirlo a
    nombres. Se obtiene después con construir_mapeo()."""

    id_mp: int
    tipo_trama: str
    config: ConfiguracionParseo
    # Va aparte de `config` porque no interviene en el parseo (el parser
    # devuelve el valor crudo sin castear): lo consume la validación, que
    # es quien convierte a float. Ver validador.validar_lecturas.
    delimitador_decimal: str = "."


def extraer_prefijo(nombre_archivo: str) -> str | None:
    """HU49 CA1-CA2/CA4: el prefijo de tipo de trama es todo el texto
    antes del PRIMER '_' del nombre base del archivo, en mayúsculas. None
    si no hay ningún '_' (o el archivo empieza con '_', prefijo vacío) -
    sin separador no hay forma de aislar un prefijo, y resolver_formato
    trata esto como CA4: se rechaza el archivo, no se inventa nada.

    Se compara sobre el nombre base (sin la ruta) y en mayúsculas: los
    dataloggers no son consistentes con el case ni con la ruta que
    antecede al archivo.
    """
    base = os.path.basename(nombre_archivo).upper()
    indice_guion_bajo = base.find("_")
    if indice_guion_bajo <= 0:
        return None
    return base[:indice_guion_bajo]


def detectar_tipo_trama(db: Session, id_dspstv: int, nombre_archivo: str) -> str | None:
    """Devuelve el tipo de trama que matchea el prefijo del archivo (p.
    ej. 'H' para "H_datos.dat"), o None si ninguna calza.

    Ya no compara contra un diccionario fijo (H/E/P hardcodeados) ni exige
    que el prefijo sea una sola letra (HU49): el tipo de trama lo define
    el técnico de telemetría al crear el mp_frmt (ver _validar_tipo_trama
    en routers/mapeos.py) o lo crea automáticamente resolver_formato
    cuando llega un prefijo nunca visto, así que acá se resuelve contra
    los tp_trm que ESTE dispositivo tiene realmente configurados -no
    contra los de otros dispositivos, que podrían usar el mismo prefijo
    con otro significado-.
    """
    prefijo = extraer_prefijo(nombre_archivo)
    if prefijo is None:
        return None
    letras = (
        db.query(MapeoFormato.tp_trm)
        .filter(MapeoFormato.id_dspstv == id_dspstv, MapeoFormato.estd == "Activo")
        .distinct()
        .all()
    )
    for (letra,) in letras:
        if prefijo == letra:
            return letra
    return None


def _crear_mapeo_formato_automatico(
    db: Session, id_dspstv: int, prefijo: str
) -> MapeoFormato:
    """HU49 CA1-CA2: crea el mp_frmt para un prefijo nunca visto en este
    dispositivo, con valores de parseo por defecto (ver constantes al
    inicio del módulo) y SIN ninguna columna mapeada -HU50 se encarga de
    poblarlas cuando llegue el header real-.

    HACE SU PROPIO COMMIT (no un simple flush) -cambio de contrato
    deliberado respecto al resto del pipeline de ingesta, que nunca
    comitea y deja esa decisión al llamador (ver tasks/ingesta.py). Se
    encontró en la verificación funcional que sin esto, HU49 no converge:
    si el archivo que disparó la creación automática después falla (ej.
    HU50 no matchea ninguna columna, ErrorDatosNoRecuperable), el
    `db.rollback()` del llamador se llevaba puesta la trama recién creada
    -y con ella, cualquier columna/pendiente que HU50 hubiera alcanzado a
    registrar en esa misma corrida-, así que el PRÓXIMO archivo repetía
    el ciclo completo de creación desde cero, indefinidamente, si nunca
    llegaba un archivo que matcheara alguna columna en soledad. Esto se
    volvía especialmente visible con varios archivos del mismo prefijo
    llegando casi simultáneamente (sondeo FTP con archivos atrasados):
    cada worker de Celery creaba y perdía su propia trama en paralelo, sin
    que el sistema converegiera nunca solo.

    Con el commit acá, la EXISTENCIA de la trama (y su auditoría, HU49
    CA5, que se dispara en este mismo flush) queda confirmada de
    inmediato, independientemente de si el archivo que la disparó logra
    interpretarse. El auto-mapeo de columnas de HU50 (construir_mapeo,
    más abajo en el pipeline) sigue sin comitear nada por su cuenta -esa
    parte del progreso sí puede perderse si el archivo falla del todo, y
    se re-intenta en el próximo archivo, lo cual es aceptable porque no
    bloquea la convergencia: la trama en sí ya no desaparece.

    El commit también es lo que permite detectar y recuperarse de la
    carrera de dos workers creando casi al mismo tiempo un archivo con el
    mismo prefijo nuevo: el índice único parcial (id_dspstv, tp_trm)
    WHERE estd='Activo' la previene a nivel de base de datos, y ante ese
    choque se relee la fila que ganó la carrera en vez de fallar el
    archivo por una condición que no es un error de negocio.
    """
    formato = MapeoFormato(
        id_dspstv=id_dspstv,
        tp_trm=prefijo,
        orgn_crcn="Automatico",
        dscrpcn=(
            "Trama auto-detectada (HU49): sin configurar. Revisa el formato "
            "y las columnas antes de dar por buena la interpretación."
        ),
        dlmtdr=_DELIMITADOR_DEFECTO_AUTO,
        dlmtdr_dcml=_DELIMITADOR_DECIMAL_DEFECTO_AUTO,
        fl_inc_dts=_FILA_INICIO_DATOS_DEFECTO_AUTO,
        frmt_fch=_FORMATO_FECHA_DEFECTO_AUTO,
        estd="Activo",
    )
    db.add(formato)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        formato = (
            db.query(MapeoFormato)
            .filter(
                MapeoFormato.id_dspstv == id_dspstv,
                MapeoFormato.tp_trm == prefijo,
                MapeoFormato.estd == "Activo",
            )
            .first()
        )
        if formato is None:
            # No debería pasar: si el commit chocó por el índice único
            # parcial, tiene que existir la fila que ganó. Si no está,
            # es un estado inesperado real y hay que propagar el error
            # original en vez de esconderlo.
            raise
    return formato


def resolver_formato(
    db: Session,
    id_dspstv: int,
    nombre_archivo: str,
    *,
    permitir_creacion_automatica: bool = True,
) -> FormatoResuelto:
    """Resuelve el formato y el mapeo real para un archivo dado.

    DEC-09: el formato se busca por DISPOSITIVO + tipo de trama, no por
    sede + marca. Dos dataloggers de la misma marca en la misma sede
    pueden tener sensores distintos conectados; con el criterio anterior
    compartían mapeo y las lecturas del segundo se guardaban bajo el
    parámetro equivocado sin ningún error visible. El dispositivo ya viene
    resuelto por resolver_dispositivo() a partir de la conexión FTP
    entrante, que es exclusiva de un solo datalogger físico.

    HU49 CA1-CA2: si el prefijo del archivo no matchea ningún mp_frmt
    activo de este dispositivo, se crea uno automáticamente (ver
    _crear_mapeo_formato_automatico) en vez de fallar -antes esto era
    directamente un MapeoNoEncontradoError; ahora solo lo es si el nombre
    no tiene NINGÚN '_' (CA4: sin separador no hay prefijo que probar ni
    crear).

    permitir_creacion_automatica=False desactiva ESA parte para
    llamadores de solo lectura (ej. GET /ingesta/cola/{id}/registros, que
    vuelve a resolver el formato de un archivo YA procesado solo para
    mostrar su contenido crudo): una consulta no debe tener el efecto
    secundario de crear un mp_frmt nuevo -con su entrada de auditoría-
    nada más por haber sido llamada. En ese caso, la ausencia de mapeo
    sigue siendo MapeoNoEncontradoError, igual que antes de HU49.

    CAMBIO DE CONTRATO TRANSACCIONAL (HU49): a diferencia del resto del
    pipeline de ingesta (que nunca comitea, dejándolo al llamador),
    resolver_formato SÍ hace un db.commit() cuando crea una trama
    automática nueva (ver _crear_mapeo_formato_automatico). Es
    deliberado: sin esto, un archivo que falla después de crear la trama
    (ej. ninguna columna matchea) revertía la trama junto con el resto de
    la transacción, y el sistema nunca convergía -el próximo archivo
    repetía el ciclo de creación desde cero indefinidamente, visible
    sobre todo con varios archivos del mismo prefijo llegando casi
    simultáneamente-. Si el prefijo YA tiene una trama activa (caso
    normal, sin HU49 de por medio), esta función sigue sin comitear nada,
    igual que siempre.
    """
    prefijo = extraer_prefijo(nombre_archivo)
    if prefijo is None:
        raise MapeoNoEncontradoError(
            f"El archivo '{nombre_archivo}' no tiene un separador '_' que "
            f"permita aislar un prefijo de tipo de trama; no se puede "
            f"determinar qué formato aplica ni crear uno automáticamente. "
            f"Nombra el archivo como '<PREFIJO>_...' (ej. 'H_datos.dat')."
        )

    tipo_trama = detectar_tipo_trama(db, id_dspstv, nombre_archivo)
    if tipo_trama is None:
        if not permitir_creacion_automatica:
            raise MapeoNoEncontradoError(
                f"El archivo '{nombre_archivo}' no coincide con el prefijo de "
                f"ningún tipo de trama configurado (mp_frmt activo) para el "
                f"dispositivo id={id_dspstv}; no se puede determinar qué "
                f"formato aplica. Verifica que exista un mapeo para ese "
                f"prefijo."
            )
        formato = _crear_mapeo_formato_automatico(db, id_dspstv, prefijo)
        tipo_trama = formato.tp_trm
    else:
        formato = (
            db.query(MapeoFormato)
            .filter(
                MapeoFormato.id_dspstv == id_dspstv,
                MapeoFormato.tp_trm == tipo_trama,
                MapeoFormato.estd == "Activo",
            )
            .first()
        )
        if formato is None:
            raise MapeoNoEncontradoError(
                f"No hay un formato activo (mp_frmt) para el dispositivo "
                f"id={id_dspstv} y el tipo de trama='{tipo_trama}'. Cárgalo "
                f"antes de procesar archivos de este datalogger."
            )

    config = ConfiguracionParseo(
        delimitador=formato.dlmtdr,
        fila_inicio_datos=formato.fl_inc_dts,
        formato_fecha=formato.frmt_fch,
    )

    return FormatoResuelto(
        id_mp=formato.id_mp,
        tipo_trama=tipo_trama,
        config=config,
        delimitador_decimal=formato.dlmtdr_dcml,
    )


def _normalizar_nombre_columna(nombre: str) -> str:
    """HU50 CA1-CA2: normalización EXACTA (mayúsculas + trim), nada de
    distancia de edición ni similaridad difusa -decisión de negocio
    explícita para evitar falsos positivos entre columnas parecidas pero
    semánticamente distintas (ej. 'Presion_kPa' vs 'Presion_Bar' NUNCA
    deben confundirse entre sí)."""
    return nombre.strip().upper()


# HU51: prmtr.nmbr es String(100). Un header más largo que esto no se
# puede auto-crear y se deriva al flujo manual de HU50 (ver
# construir_mapeo); no se trunca a propósito, para no fusionar en un
# mismo nombre dos columnas distintas que compartan los primeros 100
# caracteres.
_LARGO_MAXIMO_NOMBRE_PARAMETRO = 100


class _NombreYaFusionadoError(Exception):
    """El nombre de la columna coincide con el de un parámetro que ya fue
    fusionado (HU51 CA5). No se puede auto-crear -el UNIQUE de prmtr.nmbr
    es global- ni reutilizar el fusionado -lo resucitaría-, así que la
    columna se deriva al flujo de resolución manual de HU50."""


def _inferir_tipo_dato(muestras: list, delimitador_decimal: str) -> str:
    """HU51: decide prmtr.tipo_dato mirando los valores REALES que trae la
    columna en el archivo que disparó la creación automática.

    Es la diferencia entre que el dato se guarde o se pierda en silencio:
    un parámetro 'numerico' manda sus lecturas a tlmtr (vlr es
    Numeric(14,4) NOT NULL) y uno 'texto' a evnt_txt. Si se auto-creara
    todo como 'numerico', una columna de mensajes -"Puerta Abierta"-
    perdería cada fila, que es exactamente el bug que documenta el
    docstring de Parametro; si se creara todo como 'texto', las
    mediciones reales no entrarían nunca a tlmtr y no serían graficables
    ni alarmables. CA2 pide que el dato se guarde bien desde el PRIMER
    archivo, así que hay que acertar sin intervención humana.

    Criterio: 'numerico' solo si TODAS las muestras no vacías parsean
    como número con el mismo criterio que usa la ingesta real
    (es_valor_numerico, de validador.py -no se reimplementa acá para que
    no puedan divergir-). Cualquier valor no numérico fuerza 'texto',
    que es la opción segura: evnt_txt acepta cualquier string, así que
    ante la duda no se pierde nada y el Administrador puede corregirlo
    al activar el parámetro (CA4).

    Sin muestras (columna presente en el header pero sin ninguna fila de
    datos todavía) cae a 'texto' por el mismo motivo: no hay evidencia
    para afirmar que es numérica, y equivocarse hacia 'texto' no pierde
    datos.
    """
    from app.services.ingesta.validador import es_valor_numerico

    hubo_muestra = False
    for valor in muestras:
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            continue
        hubo_muestra = True
        if not es_valor_numerico(valor, delimitador_decimal):
            return "texto"
    return "numerico" if hubo_muestra else "texto"


def _crear_parametro_automatico(
    db: Session, nombre_columna: str, tipo_dato: str
) -> Parametro:
    """HU51 CA1: da de alta en el catálogo un parámetro para una columna
    que no matcheó ninguno existente.

    El nombre se guarda EXACTAMENTE como viene en el header, sin
    normalizar ni limpiar (CA1): es el dato crudo que el Administrador
    necesita ver para decidir cómo llamarlo de verdad. La normalización
    solo se usa para COMPARAR (_normalizar_nombre_columna), nunca para
    persistir.

    El alta se confirma de inmediato y de forma INDEPENDIENTE del archivo
    que la disparó, por la misma razón exacta que
    _crear_mapeo_formato_automatico en HU49 (ver su docstring, y la
    regresión en TestConvergenciaDeHU49TrasArchivoFallido): si el archivo
    que disparó la creación falla después, el db.rollback() del llamador
    se llevaría puesto el parámetro recién creado y el sistema nunca
    convergería -cada archivo nuevo volvería a intentar crearlo desde
    cero-. Es el mismo problema en otra tabla, así que se aplica el mismo
    patrón, no uno nuevo: commit inmediato + IntegrityError contra el
    índice único + relectura de la fila que ganó la carrera.

    Pero a diferencia de HU49 -donde la trama se crea una sola vez, al
    principio del pipeline y antes de tocar nada más- acá NO se puede
    comitear sobre la sesión del pipeline: construir_mapeo va agregando
    MapeoColumna a esa misma sesión mientras recorre el header, y un
    db.commit() acá adentro confirmaría también esas filas a medio hacer,
    ampliando el cambio de contrato transaccional mucho más allá de lo
    que HU49 necesitó. Por eso el INSERT va en una SESIÓN PROPIA, con su
    propia conexión y transacción: el parámetro queda firme pase lo que
    pase con el archivo, y la transacción del pipeline sigue siendo
    responsabilidad exclusiva de su llamador, exactamente igual que
    antes de HU51.

    La carrera la previene el UNIQUE ya existente sobre prmtr.nmbr (no
    hizo falta crear un índice nuevo): dos workers de Celery procesando
    en paralelo dos archivos con la misma columna sin match chocan en el
    INSERT, y el perdedor relee y reutiliza el parámetro del ganador en
    vez de fallar el archivo por algo que no es un error de negocio.

    Devuelve el Parametro adjuntado a la sesión del pipeline (`db`), no
    el de la sesión efímera: el llamador necesita usar su id_prmtr para
    crear la MapeoColumna dentro de su propia transacción.
    """
    from sqlalchemy.orm import Session as SesionSQLAlchemy

    # bind=db.get_bind() devuelve el Engine en producción (conexión y
    # transacción propias, que es lo que se busca) pero la CONEXIÓN en
    # los tests, donde la sesión está atada a una conexión con una
    # transacción externa que el fixture revierte al final. Heredar esa
    # conexión es justamente lo correcto ahí: si se abriera una conexión
    # nueva, el parámetro auto-creado se comitearía de verdad, escaparía
    # al rollback del fixture y contaminaría los tests siguientes -el
    # UNIQUE de prmtr.nmbr los haría chocar entre sí-.
    sesion_propia = SesionSQLAlchemy(bind=db.get_bind())
    try:
        parametro = Parametro(
            nmbr=nombre_columna,
            # undd es NOT NULL y todavía no se conoce la unidad real -la
            # pone el Administrador al activar (CA4)-. Se usa un guion en
            # vez de cadena vacía para que en la UI se lea como "sin
            # definir" en vez de parecer un campo roto.
            undd="-",
            dscrpcn=(
                "Parametro auto-creado (HU51) desde una columna sin match en el "
                "catalogo. Revisa el nombre y asignale una unidad antes de darlo "
                "por bueno."
            ),
            tipo_dato=tipo_dato,
            estd="Pendiente de revision",
            orgn_crcn="Automatico",
        )
        sesion_propia.add(parametro)
        try:
            sesion_propia.commit()
            id_creado = parametro.id_prmtr
        except IntegrityError:
            sesion_propia.rollback()
            ganador = (
                sesion_propia.query(Parametro)
                .filter(Parametro.nmbr == nombre_columna)
                .first()
            )
            if ganador is None:
                # Si el INSERT chocó contra el UNIQUE de nmbr, la fila
                # tiene que existir. Si no está, es un estado inesperado
                # real y hay que propagar el error en vez de esconderlo.
                raise
            if ganador.estd == "Fusionado":
                # El UNIQUE de prmtr.nmbr es global e incluye a los
                # fusionados, así que un header cuyo nombre coincide con
                # uno ya fusionado no se puede volver a dar de alta con
                # ese mismo texto. Devolver el fusionado sería lo peor
                # posible: resucitaría en los selectores y deshría la
                # fusión que el Administrador acababa de hacer. Se avisa
                # al llamador, que lo deriva al flujo pendiente de HU50
                # para que un humano decida.
                raise _NombreYaFusionadoError(nombre_columna)
            id_creado = ganador.id_prmtr
    finally:
        sesion_propia.close()

    # Se relee desde la sesión del pipeline para devolver una instancia
    # adjuntada a ELLA (la de la sesión efímera queda detached al
    # cerrarla, y usarla para armar la MapeoColumna daría DetachedInstanceError).
    return db.query(Parametro).filter(Parametro.id_prmtr == id_creado).one()


def construir_mapeo(
    db: Session,
    id_mp: int,
    columnas: list,
    # No se llama `filas` a secas: más abajo esta función ya usa ese
    # nombre para las filas de mp_clmn traídas de la BD, y pisarlo hacía
    # que las muestras del archivo llegaran siempre vacías (y por lo
    # tanto TODO parámetro auto-creado quedara como 'texto').
    filas_archivo: list | None = None,
    delimitador_decimal: str = ".",
    columna_fecha: str | None = None,
) -> dict:
    """columna_original -> nombre de parámetro, a partir de mp_clmn.

    mp_clmn referencia la columna por índice; `columnas` son los nombres
    leídos del header del archivo, en orden. El índice se interpreta
    como 0-based sobre ese header.

    HU50: además de traducir lo ya mapeado (comportamiento sin cambios),
    intenta auto-mapear cada columna del header que todavía no tiene fila
    en mp_clmn NI en mp_clmn_pendiente, comparando su nombre normalizado
    contra prmtr.nmbr normalizado (match exacto, ver
    _normalizar_nombre_columna). Si matchea, crea la MapeoColumna real
    (mismo mecanismo que el mapeo manual).

    HU51: si NO matchea, en vez de dejarla pendiente de asignación manual
    se da de alta un parámetro nuevo en el catálogo -en estado 'Pendiente
    de revision', ver _crear_parametro_automatico- y la columna se mapea
    contra él en el acto (CA1-CA2), así que sus datos empiezan a
    guardarse desde este mismo archivo sin ningún estado intermedio donde
    se pierdan. `filas_archivo` y `delimitador_decimal` son opcionales solo por
    compatibilidad con los llamadores que no las tienen a mano (y con los
    tests de HU50 previos a esta HU): sin ellas no se puede inferir el
    tipo de dato mirando los valores reales, y el auto-creado cae a
    'texto', que es la opción que no pierde datos (ver
    _inferir_tipo_dato).

    Dos columnas quedan FUERA del auto-alta:
    - `columna_fecha` (mp_frmt.columna_fecha): es la marca temporal de la
      lectura, no una medición; crearle un parámetro guardaría la fecha
      como si fuera un dato medido. Se saltea del todo (ni auto-creada ni
      pendiente: no hay nada que un humano deba resolver ahí).
    - Un header de más de 100 caracteres, que no entra en prmtr.nmbr. No
      se trunca a propósito -truncar dos headers largos distintos podría
      colisionar en el mismo nombre y fusionar dos columnas que no son la
      misma-, así que ese caso sí se deriva a mp_clmn_pendiente, que es
      exactamente lo que HU50 ya sabía hacer.

    A partir de HU50 esta función puede hacer INSERT (mp_clmn y
    mp_clmn_pendiente) además de leer, y a partir de HU51 también puede
    COMITEAR -pero solo el alta del parámetro auto-creado, por dentro de
    _crear_parametro_automatico y por el mismo motivo de convergencia que
    HU49; el resto sigue sin comitear, el llamador sigue controlando su
    transacción (ver interpretar_y_guardar en tasks/ingesta.py)-.

    CA6: una columna con fila en mp_clmn_pendiente (sea cual sea su estd)
    nunca se vuelve a evaluar automáticamente, ni siquiera si después se
    da de alta en prmtr un parámetro que ahora coincidiría por nombre.
    Evita reabrir algo ya resuelto o descartado a mano por un cambio
    accidental de texto en el datalogger.
    """
    filas = (
        db.query(MapeoColumna, Parametro)
        .join(Parametro, Parametro.id_prmtr == MapeoColumna.id_prmtr)
        .filter(MapeoColumna.id_mp == id_mp)
        .all()
    )

    mapeo = {}
    indices_ya_mapeados: set[int] = set()
    fuera_de_rango = []
    for mp_columna, parametro in filas:
        indice = mp_columna.indc_clmn
        indices_ya_mapeados.add(indice)
        if indice < 0 or indice >= len(columnas):
            fuera_de_rango.append(indice)
            continue
        mapeo[columnas[indice]] = parametro.nmbr

    if fuera_de_rango:
        logger.warning(
            "mp_frmt id=%s: los índices %s de mp_clmn quedan fuera del header "
            "del archivo (%s columnas); esas columnas se ignoran.",
            id_mp,
            sorted(fuera_de_rango),
            len(columnas),
        )

    # HU50 CA6: índices que YA pasaron por el auto-mapeo alguna vez (en
    # cualquier estado: Pendiente/Resuelta/Ignorada) no se re-evalúan.
    indices_pendientes_existentes = {
        indice
        for (indice,) in db.query(MapeoColumnaPendiente.indc_clmn).filter(
            MapeoColumnaPendiente.id_mp == id_mp
        )
    }
    indices_ya_evaluados = indices_ya_mapeados | indices_pendientes_existentes

    candidatos = [
        (indice, nombre_columna)
        for indice, nombre_columna in enumerate(columnas)
        if indice not in indices_ya_evaluados
    ]

    if candidatos:
        # HU51: un parámetro 'Fusionado' (CA5) quedó vacío de datos a
        # propósito y NO debe volver a matchear nada -si no se excluyera,
        # el auto-mapeo lo resucitaría en el próximo archivo y desharía
        # la fusión que el Administrador acababa de hacer-.
        catalogo_por_nombre_normalizado = {
            _normalizar_nombre_columna(parametro.nmbr): parametro
            for parametro in db.query(Parametro).filter(Parametro.estd != "Fusionado")
        }
        for indice, nombre_columna in candidatos:
            parametro = catalogo_por_nombre_normalizado.get(
                _normalizar_nombre_columna(nombre_columna)
            )
            if parametro is not None:
                db.add(
                    MapeoColumna(id_mp=id_mp, indc_clmn=indice, id_prmtr=parametro.id_prmtr)
                )
                mapeo[nombre_columna] = parametro.nmbr
                logger.info(
                    "HU50: columna '%s' (índice %s) de mp_frmt id=%s auto-mapeada "
                    "al parámetro '%s' por coincidencia exacta de nombre.",
                    nombre_columna,
                    indice,
                    id_mp,
                    parametro.nmbr,
                )
            elif columna_fecha and _normalizar_nombre_columna(
                nombre_columna
            ) == _normalizar_nombre_columna(columna_fecha):
                # La columna de fecha es la marca temporal de la lectura
                # (mp_frmt.columna_fecha, la consume el parser para armar
                # fch_hr), NO una medición: auto-crearle un parámetro
                # guardaría la fecha como si fuera un dato medido. Se
                # saltea sin dejarla pendiente tampoco -no hay nada que
                # un humano tenga que resolver acá-.
                logger.debug(
                    "HU51: columna '%s' (índice %s) de mp_frmt id=%s es la columna "
                    "de fecha; no se auto-crea parámetro para ella.",
                    nombre_columna,
                    indice,
                    id_mp,
                )
            elif len(nombre_columna) > _LARGO_MAXIMO_NOMBRE_PARAMETRO:
                # No se puede auto-crear (no entra en prmtr.nmbr) y no se
                # trunca a propósito: dos headers largos distintos podrían
                # truncar al mismo nombre y terminar fusionando columnas
                # que no son la misma. Se deriva al flujo manual de HU50.
                db.add(
                    MapeoColumnaPendiente(
                        id_mp=id_mp,
                        indc_clmn=indice,
                        nmbr_clmn_orgn=nombre_columna[:200],
                        estd="Pendiente",
                    )
                )
                logger.info(
                    "HU51: columna '%s' (índice %s) de mp_frmt id=%s excede los "
                    "%s caracteres que admite prmtr.nmbr; no se auto-crea el "
                    "parámetro y queda pendiente de asignación manual.",
                    nombre_columna,
                    indice,
                    id_mp,
                    _LARGO_MAXIMO_NOMBRE_PARAMETRO,
                )
            else:
                # HU51 CA1-CA2: no hay parámetro que matchee -> se crea uno
                # nuevo en 'Pendiente de revision' y la columna se mapea
                # contra él ya mismo, así el dato se guarda desde este
                # primer archivo.
                muestras = []
                if filas_archivo:
                    for fila in filas_archivo:
                        valores = getattr(fila, "valores", None) or {}
                        if nombre_columna in valores:
                            muestras.append(valores[nombre_columna])
                tipo_dato = _inferir_tipo_dato(muestras, delimitador_decimal)

                try:
                    parametro_nuevo = _crear_parametro_automatico(
                        db, nombre_columna, tipo_dato
                    )
                except _NombreYaFusionadoError:
                    db.add(
                        MapeoColumnaPendiente(
                            id_mp=id_mp,
                            indc_clmn=indice,
                            nmbr_clmn_orgn=nombre_columna[:200],
                            estd="Pendiente",
                        )
                    )
                    logger.info(
                        "HU51: la columna '%s' (índice %s) de mp_frmt id=%s coincide con "
                        "un parámetro ya fusionado; no se auto-crea (resucitaría la "
                        "fusión) y queda pendiente de asignación manual.",
                        nombre_columna,
                        indice,
                        id_mp,
                    )
                    continue

                db.add(
                    MapeoColumna(
                        id_mp=id_mp, indc_clmn=indice, id_prmtr=parametro_nuevo.id_prmtr
                    )
                )
                mapeo[nombre_columna] = parametro_nuevo.nmbr
                logger.info(
                    "HU51: columna '%s' (índice %s) de mp_frmt id=%s sin parámetro "
                    "que la matchee; se auto-creó el parámetro id=%s "
                    "(tipo_dato='%s', estado 'Pendiente de revision') y la columna "
                    "quedó mapeada contra él.",
                    nombre_columna,
                    indice,
                    id_mp,
                    parametro_nuevo.id_prmtr,
                    tipo_dato,
                )
        # Las MapeoColumna/MapeoColumnaPendiente recién creadas deben
        # existir YA: tipos_de_parametro() se llama después en el mismo
        # pipeline (ver interpretar_y_guardar en tasks/ingesta.py) y
        # necesita ver las columnas auto-mapeadas en esta misma corrida.
        try:
            db.flush()
        except IntegrityError:
            # Carrera entre dos workers procesando archivos del mismo
            # dispositivo y trama a la vez: ambos vieron el mismo índice
            # sin mapear y ambos insertaron su MapeoColumna, chocando
            # contra UNIQUE(id_mp, indc_clmn). No es un error de negocio
            # -el otro worker ya dejó el mapeo que corresponde-, así que
            # se descarta lo propio y se relee el estado ganador en vez
            # de fallar el archivo. Antes de HU51 esta carrera casi no se
            # daba porque las columnas sin match no llegaban a insertar
            # nada; ahora sí.
            db.rollback()
            logger.info(
                "mp_frmt id=%s: otro proceso mapeó las mismas columnas primero; "
                "se reutiliza su resultado.",
                id_mp,
            )
            return construir_mapeo(
                db,
                id_mp,
                columnas,
                filas_archivo=filas_archivo,
                delimitador_decimal=delimitador_decimal,
                columna_fecha=columna_fecha,
            )

    return mapeo


def tipos_de_parametro(db: Session, id_mp: int) -> dict:
    """nombre_parametro -> prmtr.tipo_dato, para los parámetros usados por
    este mapeo. Lo consume validar_lecturas (tipos_parametro) para saber
    qué columnas exigen float() y cuáles se aceptan como texto tal cual
    (ej. "MensajeP"/"MensajeA" de la trama de puerta). Separada de
    construir_mapeo -que ya hace el mismo join- para no romper su
    contrato de retorno (columna_original -> nombre_parametro) donde ya
    se usa."""
    filas = (
        db.query(Parametro.nmbr, Parametro.tipo_dato)
        .join(MapeoColumna, MapeoColumna.id_prmtr == Parametro.id_prmtr)
        .filter(MapeoColumna.id_mp == id_mp)
        .all()
    )
    return {nmbr: tipo_dato for nmbr, tipo_dato in filas}
