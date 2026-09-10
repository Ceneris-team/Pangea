"""
HT-10 - Tests de la capa de caché en sí (claves, ámbito, downsampling).

Estos tests NO tocan Redis ni Postgres: verifican la construcción de la
clave y el criterio de muestreo, que es lógica pura. El comportamiento
extremo a extremo (cachear una respuesta real, invalidarla al llegar una
lectura, y el aislamiento entre sedes de CA4) vive en
tests/routers/test_cache_ht10.py, que sí levanta la app y Redis.

La separación es a propósito: la garantía de CA4 empieza acá -si dos
ámbitos distintos produjeran la misma clave, ninguna cantidad de tests de
endpoint lo salvaría- y se confirma allá.
"""

import datetime as dt

from app.services.cache import consultas as cache
from app.services.cache.downsampling import muestrear, rango_es_amplio


class TestAmbitoDeUsuario:
    """CA4: el ámbito es lo que separa a un usuario de otro en la clave."""

    def test_sedes_distintas_dan_ambitos_distintos(self):
        a = cache.ambito_de_usuario({"sede_id": 1}, [10, 11])
        b = cache.ambito_de_usuario({"sede_id": 2}, [10, 11])
        assert a != b

    def test_misma_sede_con_ubicaciones_distintas_da_ambitos_distintos(self):
        """Dos Clientes Finales de la MISMA sede con asignaciones de
        prms_ubccn distintas (HU21) ven datos distintos: no pueden
        compartir entrada de caché."""
        a = cache.ambito_de_usuario({"sede_id": 1}, [10, 11])
        b = cache.ambito_de_usuario({"sede_id": 1}, [10])
        assert a != b

    def test_mismo_usuario_es_estable_aunque_cambie_el_orden(self):
        """ubicaciones_permitidas() no garantiza orden (SELECT sin ORDER
        BY). Si el orden cambiara la clave, la caché nunca acertaría."""
        a = cache.ambito_de_usuario({"sede_id": 1}, [11, 10, 12])
        b = cache.ambito_de_usuario({"sede_id": 1}, [10, 12, 11])
        assert a == b

    def test_scope_global_sin_sede_no_colisiona_con_otro_global(self):
        """Un usuario con scope 'global' trae sede_id=None (ver
        security/permisos.py). Con una clave basada SOLO en sede_id, todos
        los globales caerían en el mismo cubo; el conjunto de ubicaciones
        los desambigua."""
        a = cache.ambito_de_usuario({"sede_id": None, "scope": "global"}, [1, 2])
        b = cache.ambito_de_usuario({"sede_id": None, "scope": "global"}, [3, 4])
        assert a != b


class TestClave:
    def test_parametros_distintos_dan_claves_distintas(self):
        ambito = cache.ambito_de_usuario({"sede_id": 1}, [10])
        a = cache.clave("mediciones", ambito, parametro_ids=[1])
        b = cache.clave("mediciones", ambito, parametro_ids=[2])
        assert a != b

    def test_rango_de_fechas_entra_en_la_clave(self):
        ambito = cache.ambito_de_usuario({"sede_id": 1}, [10])
        base = dt.datetime(2026, 1, 1)
        a = cache.clave("mediciones", ambito, fecha_inicio=base, fecha_fin=base)
        b = cache.clave(
            "mediciones", ambito, fecha_inicio=base, fecha_fin=base + dt.timedelta(days=7)
        )
        assert a != b

    def test_listas_en_distinto_orden_comparten_clave(self):
        """?parametro_ids=3&parametro_ids=1 pide lo mismo que al revés."""
        ambito = cache.ambito_de_usuario({"sede_id": 1}, [10])
        a = cache.clave("mediciones", ambito, parametro_ids=[3, 1])
        b = cache.clave("mediciones", ambito, parametro_ids=[1, 3])
        assert a == b

    def test_recursos_distintos_no_colisionan(self):
        ambito = cache.ambito_de_usuario({"sede_id": 1}, [10])
        assert cache.clave("mediciones", ambito) != cache.clave("mapa-cliente", ambito)

    def test_la_sede_queda_legible_en_la_clave(self):
        """Poder hacer `KEYS pangea:cache:mediciones:sd7:*` es lo que
        permite auditar a mano si algo se está cacheando fuera de sede."""
        clave = cache.clave("mediciones", cache.ambito_de_usuario({"sede_id": 7}, [10]))
        assert clave.startswith("pangea:cache:mediciones:sd7:")


class TestRangoAmplio:
    """CA3: >30 días es rango amplio."""

    def test_rango_corto_no_es_amplio(self):
        inicio = dt.datetime(2026, 1, 1)
        assert not rango_es_amplio(inicio, inicio + dt.timedelta(days=7))

    def test_treinta_dias_exactos_no_es_amplio(self):
        """El umbral es ESTRICTO (>30), así que 30 justos no muestrean."""
        inicio = dt.datetime(2026, 1, 1)
        assert not rango_es_amplio(inicio, inicio + dt.timedelta(days=30))

    def test_mas_de_treinta_dias_es_amplio(self):
        inicio = dt.datetime(2026, 1, 1)
        assert rango_es_amplio(inicio, inicio + dt.timedelta(days=31))

    def test_rango_abierto_cuenta_como_amplio(self):
        """Sin fechas se pide toda la historia: el caso más pesado de
        todos, no puede quedar fuera del downsampling."""
        assert rango_es_amplio(None, None)
        assert rango_es_amplio(dt.datetime(2026, 1, 1), None)
        assert rango_es_amplio(None, dt.datetime(2026, 1, 1))


class TestMuestreo:
    """CA3: máximo configurable de puntos, muestreo uniforme."""

    def test_por_debajo_del_maximo_no_toca_la_lista(self):
        items = list(range(10))
        assert muestrear(items, 100) == items

    def test_respeta_el_maximo(self):
        assert len(muestrear(list(range(10000)), 500)) <= 500

    def test_conserva_los_extremos(self):
        """Que la gráfica empiece o termine en un punto arbitrario se ve
        como un dato faltante, no como una muestra."""
        items = list(range(10000))
        muestra = muestrear(items, 500)
        assert muestra[0] == items[0]
        assert muestra[-1] == items[-1]

    def test_es_determinista(self):
        """Importa porque la respuesta se CACHEA: dos peticiones iguales
        tienen que dar exactamente los mismos puntos."""
        items = list(range(10000))
        assert muestrear(items, 500) == muestrear(items, 500)

    def test_mantiene_el_orden(self):
        muestra = muestrear(list(range(10000)), 500)
        assert muestra == sorted(muestra)
