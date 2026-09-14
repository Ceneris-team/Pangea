"""
HT-10 punto 3 / CA2 - Invalidación de caché al llegar telemetría nueva.

Hay DOS caminos por los que entra una lectura a la base, y los dos tienen
que invalidar:

1. El pipeline automático de ingesta: services/ingesta/persistencia.py
   ::guardar_lecturas, llamado desde el worker de Celery
   (tasks/ingesta.py::procesar_archivo_dat).
2. La carga manual: routers/dispositivos.py, POST
   /dispositivos/{id}/carga-manual, que escribe directo en tlmtr sin
   pasar por el pipeline.

Este módulo existe para que la REGLA de invalidación (qué índices se
tocan cuando llega una lectura de tal dispositivo) se defina UNA sola
vez. Si cada camino la implementara por su cuenta, arreglar uno dejaría
el otro sirviendo datos viejos -exactamente el tipo de desincronización
que ya motivó extraer security/ubicaciones_permitidas.py-.

QUE SE INVALIDA, Y POR QUE ESO Y NO MAS
---------------------------------------
Una lectura pertenece a un dispositivo, que cuelga de una ubicación, que
cuelga de una sede. Se invalidan los dos índices:

- el de la UBICACION, porque es el eje de /mapa-cliente (un marcador por
  ubicación) y del filtro de HU21;
- el de la SEDE, porque es el eje de /mediciones (tlmtr.id_sd) y el
  ámbito con el que se construye la clave de caché.

No se invalida nada más. Vaciar la caché entera en cada lectura -que es
lo fácil- haría que, con el pipeline corriendo cada minuto sobre varias
sedes, la caché nunca llegara viva al segundo request y la HT no
serviría para nada.

CUANDO SE LLAMA
---------------
SIEMPRE después del commit, nunca antes. Invalidar antes del commit abre
una ventana en la que otro request puede repoblar la caché leyendo el
estado ANTERIOR (la transacción de escritura todavía no es visible) y
dejar esa entrada vieja viva durante todo su TTL. Es el mismo criterio
con el que HU17 publica sus eventos de mapa recién después del commit
(ver el comentario en tasks/ingesta.py).
"""

import logging

from app.services.cache import consultas

logger = logging.getLogger(__name__)


def invalidar_por_lectura(id_sd: int | None = None, id_ubccn: int | None = None) -> int:
    """Invalida lo afectado por una lectura nueva. Devuelve cuántas
    entradas se borraron (0 también si Redis está caído: ver consultas
    .invalidar, que degrada en silencio y deja que el TTL haga el resto).

    Los dos argumentos son opcionales por separado para que cada llamador
    pase lo que realmente tiene a la mano sin consultas extra: el
    pipeline conoce la ubicación (ResultadoPersistencia.id_ubccn) y la
    sede; la carga manual conoce ambas por la ficha del dispositivo.
    """
    if id_sd is None and id_ubccn is None:
        return 0

    borradas = consultas.invalidar_sede(id_sd=id_sd, id_ubccn=id_ubccn)
    if borradas:
        logger.info(
            "HT-10: invalidadas %s entrada(s) de cache por lectura nueva (sede=%s ubicacion=%s)",
            borradas,
            id_sd,
            id_ubccn,
        )
    return borradas
