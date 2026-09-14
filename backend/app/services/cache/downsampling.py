"""
HT-10 punto 5 / CA3 - Downsampling de series largas en el backend.

PROBLEMA
--------
Un datalogger produce una lectura cada ~15 minutos (ver frcnc_mnts). Un
rango de 90 días de un solo parámetro son ~8.600 puntos; con varios
parámetros y varias ubicaciones seleccionadas, la respuesta de
GET /mediciones se va a decenas de miles de filas. Ninguna gráfica de
1.000 px de ancho puede dibujar más puntos que píxeles tiene: el costo
extra se paga entero en serialización JSON, red y parseo en el navegador,
sin que el usuario vea un solo pixel más de información.

CRITERIO DE MUESTREO ELEGIDO: UNIFORME (cada n-ésimo punto)
-----------------------------------------------------------
Se recorre la serie ya ordenada y se toma un punto de cada
paso = ceil(total / maximo), conservando SIEMPRE el primero y el último.

Por qué uniforme y no algo más sofisticado:

- Es O(n) sin memoria extra y sin dependencias, y el resultado es
  determinista: dos peticiones iguales devuelven exactamente los mismos
  puntos, lo cual importa porque esta respuesta se CACHEA (si el muestreo
  fuese aleatorio, dos entradas de caché de la misma consulta mostrarían
  gráficas distintas).
- Conserva la forma general de una serie de telemetría ambiental, que es
  suave y sin transitorios de un solo punto.
- El repo NO tiene hoy ninguna implementación de LTTB ni de agregación
  por ventana (se verificó antes de escribir esto), así que introducir
  una sería alcance nuevo, no reutilización. La HT dice explícitamente
  que no hace falta un algoritmo sofisticado.

LIMITACION CONOCIDA, ANOTADA A PROPOSITO
-----------------------------------------
El muestreo uniforme puede SALTARSE un pico aislado (un máximo que dura
una sola lectura), porque no mira los valores, solo las posiciones. Para
la vista de gráficos de HU15 -tendencia sobre un rango amplio- es
aceptable: el dato exacto sigue estando en la BD y se ve al acotar el
rango, momento en el que el downsampling deja de aplicar. Si alguna vez
hace falta que los extremos sobrevivan al muestreo (p. ej. para HU28,
umbrales/alarmas), el reemplazo correcto es LTTB o un min/max por
ventana, y el punto de cambio es esta función y nada más.
"""

import math
import os

# CA3: máximo configurable de puntos devueltos. 2.000 es holgado para
# cualquier gráfica de pantalla (más del doble de píxeles de ancho de un
# monitor típico) y a la vez ~4x menos que los ~8.600 puntos de un
# trimestre de un solo parámetro.
MAXIMO_PUNTOS_DEFECTO = int(os.environ.get("MEDICIONES_MAX_PUNTOS", "2000"))

# CA3: a partir de cuántos días de rango se considera "amplio" y se
# aplica downsampling. La HT fija el umbral en 30 días.
DIAS_RANGO_AMPLIO = int(os.environ.get("MEDICIONES_DIAS_RANGO_AMPLIO", "30"))


def rango_es_amplio(fecha_inicio, fecha_fin, dias_umbral: int = DIAS_RANGO_AMPLIO) -> bool:
    """True si el rango pedido supera el umbral (por defecto 30 días).

    Sin fecha_inicio o sin fecha_fin el rango es ABIERTO: pide toda la
    historia disponible de ese lado, que es por definición el caso más
    amplio posible. Tratarlo como "no amplio" dejaría justo a la consulta
    más pesada de todas fuera del downsampling.
    """
    if fecha_inicio is None or fecha_fin is None:
        return True
    return (fecha_fin - fecha_inicio).days > dias_umbral


def muestrear(items: list, maximo: int = MAXIMO_PUNTOS_DEFECTO) -> list:
    """Reduce la lista a como mucho `maximo` elementos, muestreo uniforme.

    Conserva el primero y el último elemento siempre: son los extremos
    del rango que el usuario pidió, y que la gráfica empiece o termine en
    un punto arbitrario se ve como un dato faltante.

    La lista se asume YA ORDENADA por fecha (lo está: el endpoint ordena
    antes de llamar). No se reordena acá para no pagar un segundo sort
    sobre decenas de miles de elementos.
    """
    total = len(items)
    if maximo <= 0 or total <= maximo:
        return items

    paso = math.ceil(total / maximo)
    muestreados = items[::paso]

    # items[::paso] no incluye el último elemento salvo que la longitud
    # caiga justo en el paso. Se agrega a mano para preservar el extremo
    # derecho del rango, PERO reemplazando el último muestreado en vez de
    # apilarse detrás: con maximo=500 y 10.000 puntos, paso=20 da
    # exactamente 500 elementos, y hacer append devolvería 501 -es decir,
    # el "máximo configurable" de CA3 se pasaría por uno-. Reemplazar
    # mantiene el tope exacto y conserva igual el extremo, que es lo que
    # se quería; el punto que se pierde es su vecino inmediato.
    if muestreados[-1] is not items[-1]:
        if len(muestreados) >= maximo:
            muestreados[-1] = items[-1]
        else:
            muestreados.append(items[-1])
    return muestreados
