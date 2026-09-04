"""
HU 17 - Semáforo de estado de una estación en el mapa.

#############################################################################
##                                                                         ##
##   ATENCIÓN: UMBRALES TEMPORALES - REEMPLAZAR AL IMPLEMENTAR HU 28       ##
##                                                                         ##
##   Los umbrales de UMBRALES_TEMPORALES (más abajo en este mismo módulo)  ##
##   están HARDCODEADOS y son una simulación provisional. HU 28            ##
##   ("Establecer condiciones de alarma", Sprint 4) es la que define los   ##
##   umbrales reales, configurables por el usuario.                        ##
##                                                                         ##
##   Las tablas de HU 28 YA EXISTEN en el modelo (app/models/alarma.py):   ##
##       alrm       -> Alarma          (id_prmtr, id_ubccn, estd)          ##
##       cndcn_alrm -> CondicionAlarma (oprdr, vlr_umbrl)                  ##
##   pero NO tienen ninguna lógica ni endpoint asociado todavía            ##
##   (verificado en la Fase 0 de HU 17: cero referencias fuera de models). ##
##                                                                         ##
##   PUNTO EXACTO A REEMPLAZAR: la función _condiciones_de_parametro().    ##
##   Está aislada a propósito para que la migración a HU 28 sea cambiar    ##
##   SOLO la FUENTE de los datos (dict en memoria -> SELECT sobre          ##
##   cndcn_alrm), sin tocar evaluar_semaforo() ni _cumple_condicion(),     ##
##   que ya trabajan con la misma forma que la tabla real:                 ##
##   (operador, valor_umbral) con oprdr IN ('>','<','>=','<=','=').        ##
##                                                                         ##
#############################################################################
"""

from decimal import Decimal, InvalidOperation

# Los tres estados del semáforo (CA de HU 17: verde / amarillo / rojo).
VERDE = "verde"
AMARILLO = "amarillo"
ROJO = "rojo"

# El orden de gravedad ES la precedencia al combinar los parámetros de una
# estación: gana el más grave (ver evaluar_semaforo).
_GRAVEDAD = {VERDE: 0, AMARILLO: 1, ROJO: 2}


# ---------------------------------------------------------------------------
# INICIO DEL BLOQUE TEMPORAL (HU 28)
# ---------------------------------------------------------------------------
# Forma idéntica a cndcn_alrm: por cada parámetro, una lista de
# (operador, valor_umbral) para cada nivel. Se evalúa ROJO primero y luego
# AMARILLO; si no cumple ninguna condición, la estación queda en VERDE.
#
# La clave es el NOMBRE del parámetro (prmtr.nmbr) y no su id_prmtr a
# propósito: los ids son distintos entre la base local, la de test y la de
# Lightsail, así que hardcodear ids haría que el semáforo se viera bien en
# una y quedara todo verde en otra. HU 28 real usará id_prmtr, que ahí sí
# viene de una fila que el usuario creó explícitamente.
#
# Los nombres están en minúscula y con guion bajo porque así es como los
# escribe el estandarizador de la ingesta (ver services/ingesta/
# estandarizador.py) y como están en prmtr en la BD real: 'temperatura',
# no 'Temperatura'. La comparación se hace normalizada de todas formas
# (ver _condiciones_de_parametro) para que un mapeo con otra grafía no
# deje la estación en verde por un detalle de mayúsculas.
#
# Los parámetros cubiertos son los de calidad de agua que efectivamente
# reporta la instalación (sonda multiparamétrica + estado de gabinete).
# Los valores son RANGOS DE REFERENCIA GENÉRICOS de calidad de agua, NO
# están validados con CENERIS ni con normativa: sirven para que el mapa
# muestre los tres colores de forma verosímil, nada más. HU 28 los
# reemplaza por los que configure el usuario.
UMBRALES_TEMPORALES: dict[str, dict[str, list[tuple[str, Decimal]]]] = {
    # pH: el rango típico de agua natural es 6.5-8.5.
    "ph": {
        ROJO: [("<", Decimal("6")), (">", Decimal("9"))],
        AMARILLO: [("<", Decimal("6.5")), (">", Decimal("8.5"))],
    },
    # Oxígeno disuelto: por debajo de 4 mg/L la vida acuática sufre.
    "oxigeno_disuelto": {
        ROJO: [("<", Decimal("4"))],
        AMARILLO: [("<", Decimal("6"))],
    },
    "porcentaje_oxigeno_disuelto": {
        ROJO: [("<", Decimal("50")), (">", Decimal("130"))],
        AMARILLO: [("<", Decimal("70")), (">", Decimal("110"))],
    },
    "temperatura": {
        ROJO: [(">", Decimal("32")), ("<", Decimal("2"))],
        AMARILLO: [(">", Decimal("28")), ("<", Decimal("5"))],
    },
    # Temperatura del panel del datalogger: es salud del EQUIPO, no del
    # agua. Un gabinete por encima de 60 °C es una falla real.
    "temperatura_panel": {
        ROJO: [(">", Decimal("60"))],
        AMARILLO: [(">", Decimal("45"))],
    },
    # Batería del datalogger: 12 V nominal. Por debajo de 11.5 V el
    # equipo está por quedarse sin energía.
    "bateria_v": {
        ROJO: [("<", Decimal("11.5"))],
        AMARILLO: [("<", Decimal("12.2"))],
    },
    "conductividad": {
        ROJO: [(">", Decimal("2000"))],
        AMARILLO: [(">", Decimal("1500"))],
    },
    "orp": {
        ROJO: [("<", Decimal("100")), (">", Decimal("800"))],
        AMARILLO: [("<", Decimal("200")), (">", Decimal("700"))],
    },
}


def _condiciones_de_parametro(nombre_parametro: str) -> dict[str, list[tuple[str, Decimal]]]:
    """>>> ESTA ES LA FUNCIÓN A REEMPLAZAR CUANDO EXISTA HU 28. <<<

    Devuelve las condiciones de alarma aplicables a un parámetro, en la
    forma {nivel: [(operador, umbral), ...]}.

    Implementación TEMPORAL: lee del dict en memoria UMBRALES_TEMPORALES.

    Implementación DEFINITIVA (HU 28), aproximadamente:

        def _condiciones_de_parametro(db, id_prmtr, id_ubccn):
            filas = (
                db.query(CondicionAlarma.oprdr, CondicionAlarma.vlr_umbrl)
                .join(Alarma, Alarma.id_alrm == CondicionAlarma.id_alrm)
                .filter(Alarma.id_prmtr == id_prmtr,
                        Alarma.id_ubccn == id_ubccn,
                        Alarma.estd == "Activa")
                .all()
            )
            ...

    La firma cambiará (necesita db y los ids), pero el RESULTADO conserva
    la forma, así que evaluar_semaforo() y _cumple_condicion() siguen
    sirviendo sin cambios.

    La búsqueda normaliza el nombre (minúsculas, espacios -> guion bajo)
    porque el nombre del parámetro depende de cómo se cargó el mapeo de
    HU 06 y ha aparecido en ambas grafías. Sin esto, un 'Temperatura'
    mapeado a mano no encontraría los umbrales de 'temperatura' y la
    estación quedaría en verde sin que nadie note por qué. Esta
    normalización deja de hacer falta con HU 28, donde el vínculo es por
    id_prmtr y no por nombre.
    """
    clave = nombre_parametro.strip().lower().replace(" ", "_")
    return UMBRALES_TEMPORALES.get(clave, {})


# ---------------------------------------------------------------------------
# FIN DEL BLOQUE TEMPORAL (HU 28)
# ---------------------------------------------------------------------------


def _cumple_condicion(valor: Decimal, operador: str, umbral: Decimal) -> bool:
    """Evalúa un valor contra una condición (operador, umbral).

    Los operadores son exactamente los que admite el CHECK constraint de
    cndcn_alrm. Un operador fuera de esa lista devuelve False en vez de
    reventar: cuando HU 28 sea real los datos vienen de la BD, y una fila
    corrupta no debe tumbar el mapa entero.
    """
    if operador == ">":
        return valor > umbral
    if operador == "<":
        return valor < umbral
    if operador == ">=":
        return valor >= umbral
    if operador == "<=":
        return valor <= umbral
    if operador == "=":
        return valor == umbral
    return False


def evaluar_parametro(nombre_parametro: str, valor) -> str:
    """Color de UN parámetro según su último valor.

    Un parámetro sin umbrales configurados (o un valor no numérico, como
    los de evnt_txt) es VERDE: "sin condición de alarma definida" no es lo
    mismo que "en alarma". Los eventos de texto se muestran igual en el
    panel de CA2, pero no pintan el marcador.
    """
    if valor is None:
        return VERDE
    try:
        valor_decimal = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        # Parámetro de texto (evnt_txt): se muestra, no se semaforiza.
        return VERDE

    condiciones = _condiciones_de_parametro(nombre_parametro)

    # ROJO primero: si un valor cumple a la vez la condición de rojo y la
    # de amarillo (ej. 45 grados cumple ">40" y ">32"), gana el más grave.
    for nivel in (ROJO, AMARILLO):
        for operador, umbral in condiciones.get(nivel, []):
            if _cumple_condicion(valor_decimal, operador, umbral):
                return nivel
    return VERDE


def evaluar_semaforo(valores_por_parametro: dict) -> str:
    """Color de UNA ESTACIÓN a partir del último valor de cada uno de sus
    parámetros: {nombre_parametro: valor}.

    Criterio: gana el parámetro MÁS GRAVE. Una estación con nueve
    parámetros en verde y uno en rojo se pinta roja; es lo que hace útil
    el mapa de un vistazo (CA1/CA3).

    Una estación sin ningún valor conocido queda VERDE. Es discutible
    -podría justificarse un cuarto color "sin datos"-, pero los CA de
    HU 17 solo definen tres colores, así que no se inventa un estado que
    la HU no pide. Anotado como decisión a revisar junto con HU 28.
    """
    peor = VERDE
    for nombre_parametro, valor in valores_por_parametro.items():
        color = evaluar_parametro(nombre_parametro, valor)
        if _GRAVEDAD[color] > _GRAVEDAD[peor]:
            peor = color
    return peor
