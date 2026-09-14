"""
HT-10 CA1/CA5: mide el tiempo de respuesta ANTES y DESPUES de la caché
sobre un set de consultas de referencia, y verifica de paso que las
consultas siguen aprovechando el partition pruning de HT-08 (punto 4).

Mismo patrón que app/scripts/medir_pruning_ht08.py, y por la misma razón:
la medición que va al README tiene que ser REPRODUCIBLE. Siembra sus
propios datos sintéticos bajo un cliente identificado por nombre, es
idempotente (limpia la corrida anterior antes de sembrar) y no toca datos
de otros clientes/sedes.

QUE MIDE
--------
Para cada consulta de referencia, ejecuta N repeticiones y reporta media
y p95 en dos modos:

  ANTES   = sin caché: cada repetición golpea Postgres (es el camino que
            recorría el endpoint antes de HT-10).
  DESPUES = con caché: la primera repetición es un MISS -consulta la BD y
            guarda-, y las siguientes son HIT desde Redis.

El p95 es el que pide CA1. Se calcula sobre las repeticiones del modo
DESPUES, que es el comportamiento real del endpoint una vez desplegado.

ADVERTENCIA SOBRE EL ALCANCE DE ESTA MEDICION
----------------------------------------------
Esto NO es una medición de staging. Corre contra la Postgres y el Redis
LOCALES (docker compose) y con un dataset sintético; sirve para comparar
el antes y el después en igualdad de condiciones, no para predecir la
latencia real en Lightsail -donde la BD es managed, la red no es
localhost y compiten otros procesos-. Los números del README están
etiquetados como tales.

Uso (contra una BD de dev/test, NUNCA producción):
    python -m app.scripts.medir_cache_ht10
    python -m app.scripts.medir_cache_ht10 --meses 6 --minutos 15 --repeticiones 30
"""

import argparse
import datetime as dt
import statistics
import time

from sqlalchemy import text

from app.database import SessionLocal
from app.models import Cliente, ConexionFTP, Dispositivo, MapeoFormato, Parametro, Sede, Ubicacion
from app.services.cache import consultas as cache
from app.services.particiones import asegurar_particiones

NOMBRE_CLIENTE = "HT-10 medición caché"
NOMBRE_PARAMETRO = "Temperatura caché HT-10"


def _limpiar_corrida_anterior(db) -> None:
    """Igual que en medir_pruning_ht08.py: el script es idempotente, así
    que se puede correr tantas veces como haga falta sin acumular filas
    de corridas anteriores. Ver ahí el detalle del orden de borrado
    (mp_frmt antes que dspstv por DEC-09, tlmtr antes que prmtr por FK)."""
    cliente = db.query(Cliente).filter(Cliente.rzn_scl == NOMBRE_CLIENTE).first()
    if cliente is not None:
        ids_sedes = db.query(Sede.id_sd).filter(Sede.id_clnt == cliente.id_clnt)
        for sede in db.query(Sede).filter(Sede.id_clnt == cliente.id_clnt):
            db.execute(text("DELETE FROM tlmtr WHERE id_sd = :id_sd"), {"id_sd": sede.id_sd})
        ids_ubicaciones = db.query(Ubicacion.id_ubccn).filter(Ubicacion.id_sd.in_(ids_sedes))
        ids_dispositivos = db.query(Dispositivo.id_dspstv).filter(
            Dispositivo.id_ubccn.in_(ids_ubicaciones)
        )
        db.query(MapeoFormato).filter(MapeoFormato.id_dspstv.in_(ids_dispositivos)).delete(
            synchronize_session=False
        )
        db.query(Dispositivo).filter(Dispositivo.id_ubccn.in_(ids_ubicaciones)).delete(
            synchronize_session=False
        )
        db.query(Ubicacion).filter(Ubicacion.id_sd.in_(ids_sedes)).delete(
            synchronize_session=False
        )
        db.query(ConexionFTP).filter(ConexionFTP.id_sd.in_(ids_sedes)).delete(
            synchronize_session=False
        )
        db.query(Sede).filter(Sede.id_clnt == cliente.id_clnt).delete(synchronize_session=False)
        db.query(Cliente).filter(Cliente.id_clnt == cliente.id_clnt).delete(
            synchronize_session=False
        )

    db.query(Parametro).filter(Parametro.nmbr == NOMBRE_PARAMETRO).delete(synchronize_session=False)
    db.flush()


def _sembrar(db, meses: int, minutos_entre_lecturas: int):
    """Dataset MULTI-SEDE, que es el escenario de la HT: 3 sedes con una
    ubicación y un dispositivo cada una, y lecturas a la cadencia real de
    un datalogger (~15 min, ver frcnc_mnts) durante varios meses.

    Tres sedes y no una: la caché se indexa por sede y la invalidación es
    dirigida, así que un dataset de una sola sede no distingue "invalidé
    lo justo" de "invalidé todo".
    """
    cliente = Cliente(rzn_scl=NOMBRE_CLIENTE, rc="00000000001", crr_cntct="ht10@pangea-dev.com")
    db.add(cliente)
    db.flush()

    sedes = [Sede(id_clnt=cliente.id_clnt, nmbr=f"Sede caché {i}") for i in range(1, 4)]
    db.add_all(sedes)
    db.flush()

    parametro = Parametro(nmbr=NOMBRE_PARAMETRO, undd="C")
    db.add(parametro)
    db.flush()

    dispositivos = []
    for sede in sedes:
        ubicacion = Ubicacion(
            id_sd=sede.id_sd, nmbr=f"Ubicación {sede.nmbr}", lttd=4.6, lngtd=-74.0, plgn_gjsn={}
        )
        conexion = ConexionFTP(
            id_sd=sede.id_sd,
            nmbr=f"FTP {sede.nmbr}",
            hst="host",
            usr_ftp="u",
            rt_rmt="/",
            crdncl_cfrd="x",
        )
        db.add_all([ubicacion, conexion])
        db.flush()
        dispositivo = Dispositivo(
            id_ubccn=ubicacion.id_ubccn,
            id_cnxn=conexion.id_cnxn,
            nmbr=f"Disp {sede.nmbr}",
            mrc="Marca caché",
            lttd=4.6,
            lngtd=-74.0,
        )
        db.add(dispositivo)
        db.flush()
        db.add(MapeoFormato(id_dspstv=dispositivo.id_dspstv, frmt_fch="%Y-%m-%d %H:%M:%S"))
        db.flush()
        dispositivos.append((dispositivo, sede, ubicacion))

    # Ventana que TERMINA hoy: las consultas de referencia miran hacia
    # atrás desde ahora (7 días, 30 días, 90 días), que es como consulta
    # un usuario real. Sembrar hacia el futuro dejaría los rangos de 7
    # días vacíos y la medición no diría nada.
    hasta = dt.date.today() + dt.timedelta(days=1)
    desde = hasta - dt.timedelta(days=30 * meses)
    asegurar_particiones(db.connection(), desde.replace(day=1), meses + 2)

    for dispositivo, sede, _ in dispositivos:
        db.execute(
            text(
                "INSERT INTO tlmtr (fch_hr, id_dspstv, id_prmtr, id_sd, vlr) "
                "SELECT g, :id_dspstv, :id_prmtr, :id_sd, random() * 100 "
                "FROM generate_series(:desde, :hasta, make_interval(mins => :paso)) AS g"
            ),
            {
                "id_dspstv": dispositivo.id_dspstv,
                "id_prmtr": parametro.id_prmtr,
                "id_sd": sede.id_sd,
                "desde": desde,
                "hasta": hasta,
                "paso": minutos_entre_lecturas,
            },
        )
    db.execute(text("ANALYZE tlmtr"))
    db.flush()
    return dispositivos, parametro


def _consulta_mediciones(db, id_sd: int, dias: int):
    """La forma de consulta de GET /mediciones tras HT-10: filtro por sede
    + rango de fechas + ORDER BY, todo en SQL.

    Es la que debe aprovechar idx_tlmtr_sd (id_sd, fch_hr) y el pruning de
    particiones de HT-08 (punto 4 de la HT).
    """
    hasta = dt.datetime.now(dt.timezone.utc)
    desde = hasta - dt.timedelta(days=dias)
    return db.execute(
        text(
            "SELECT fch_hr, vlr FROM tlmtr "
            "WHERE id_sd = :id_sd AND fch_hr >= :desde AND fch_hr <= :hasta "
            "ORDER BY fch_hr DESC"
        ),
        {"id_sd": id_sd, "desde": desde, "hasta": hasta},
    ).all()


def _cronometrar(funcion, repeticiones: int) -> list:
    """Devuelve la lista de duraciones en milisegundos."""
    tiempos = []
    for _ in range(repeticiones):
        inicio = time.perf_counter()
        funcion()
        tiempos.append((time.perf_counter() - inicio) * 1000)
    return tiempos


def _p95(tiempos: list) -> float:
    """p95 por el método del percentil más cercano (nearest-rank), que no
    interpola: con 20-30 repeticiones interpolar inventaría un valor que
    no corresponde a ninguna medición real."""
    ordenados = sorted(tiempos)
    indice = max(0, min(len(ordenados) - 1, int(round(0.95 * len(ordenados))) - 1))
    return ordenados[indice]


def _medir_consulta(db, nombre: str, id_sd: int, dias: int, repeticiones: int) -> dict:
    """Mide la misma consulta SIN caché y CON caché.

    SIN caché: cada repetición ejecuta el SELECT contra Postgres.
    CON caché: se usa la capa real de HT-10 (misma clave, mismo Redis),
    así que la primera repetición es MISS y el resto HIT -que es lo que
    ocurre en producción con TTL de 45s-.
    """
    ambito = cache.ambito_de_usuario({"sede_id": id_sd}, [id_sd])
    clave = cache.clave("medicion-benchmark", ambito, dias=dias)
    cache.invalidar_todo()

    sin_cache = _cronometrar(lambda: _consulta_mediciones(db, id_sd, dias), repeticiones)

    def _con_cache():
        cacheado = cache.obtener(clave)
        if cacheado is not None:
            return cacheado
        filas = _consulta_mediciones(db, id_sd, dias)
        # Se serializa igual que el endpoint: el costo de json.dumps sobre
        # la respuesta forma parte del tiempo real y omitirlo inflaría la
        # mejora medida.
        datos = [{"fch_hr": f[0].isoformat(), "vlr": float(f[1])} for f in filas]
        cache.guardar(clave, datos, indices=[cache.indice_de_sede(id_sd)])
        return datos

    con_cache = _cronometrar(_con_cache, repeticiones)
    filas = len(_consulta_mediciones(db, id_sd, dias))

    return {
        "nombre": nombre,
        "filas": filas,
        "sin_cache_media": statistics.mean(sin_cache),
        "sin_cache_p95": _p95(sin_cache),
        # Los HIT se reportan aparte de la media general: la media incluye
        # el MISS inicial, y en una vista real el usuario paga ese MISS una
        # vez cada 45s y los HIT todas las demás veces.
        "con_cache_media": statistics.mean(con_cache),
        "con_cache_p95": _p95(con_cache),
        "con_cache_hits_media": statistics.mean(con_cache[1:]) if len(con_cache) > 1 else 0.0,
    }


def _explain(db, id_sd: int, dias: int) -> str:
    hasta = dt.datetime.now(dt.timezone.utc)
    desde = hasta - dt.timedelta(days=dias)
    filas = db.execute(
        text(
            "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) "
            "SELECT fch_hr, vlr FROM tlmtr "
            "WHERE id_sd = :id_sd AND fch_hr >= :desde AND fch_hr <= :hasta "
            "ORDER BY fch_hr DESC"
        ),
        {"id_sd": id_sd, "desde": desde, "hasta": hasta},
    ).all()
    return "\n".join(fila[0] for fila in filas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meses", type=int, default=6, help="meses de datos a generar (default: 6)")
    parser.add_argument(
        "--minutos",
        type=int,
        default=15,
        help="minutos entre lecturas sintéticas (default: 15, la cadencia real de un datalogger)",
    )
    parser.add_argument(
        "--repeticiones", type=int, default=20, help="repeticiones por consulta (default: 20)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        _limpiar_corrida_anterior(db)
        dispositivos, _parametro = _sembrar(db, args.meses, args.minutos)
        db.commit()

        _dispositivo, sede, _ubicacion = dispositivos[0]
        total = db.execute(
            text("SELECT count(*) FROM tlmtr WHERE id_sd = :id_sd"), {"id_sd": sede.id_sd}
        ).scalar()
        total_todas = db.execute(
            text(
                "SELECT count(*) FROM tlmtr WHERE id_sd IN "
                "(SELECT id_sd FROM sd WHERE nmbr LIKE 'Sede caché %')"
            )
        ).scalar()

        print("=" * 78)
        print("HT-10 - Medición de tiempo de respuesta antes/después de la caché")
        print("=" * 78)
        print(
            f"Dataset sintético: {total_todas} filas en 3 sedes "
            f"({total} en la sede medida, id_sd={sede.id_sd}), "
            f"1 lectura cada {args.minutos} min durante ~{args.meses} meses."
        )
        print(f"Repeticiones por consulta: {args.repeticiones}")
        print(f"TTL de caché: {cache.TTL_CORTO}s   Redis: {cache.CACHE_REDIS_URL}\n")

        consultas_referencia = [
            ("Gráfico 1 día", 1),
            ("Gráfico 7 días (CA1)", 7),
            ("Gráfico 30 días", 30),
            ("Gráfico 90 días", 90),
        ]

        resultados = []
        for nombre, dias in consultas_referencia:
            resultados.append(
                _medir_consulta(db, nombre, sede.id_sd, dias, args.repeticiones)
            )

        encabezado = (
            f"{'Consulta':<24}{'Filas':>8}{'ANTES p95':>12}{'DESPUES p95':>13}"
            f"{'HIT medio':>12}{'Mejora':>10}"
        )
        print(encabezado)
        print("-" * len(encabezado))
        for r in resultados:
            mejora = (
                f"{r['sin_cache_p95'] / r['con_cache_hits_media']:.0f}x"
                if r["con_cache_hits_media"] > 0
                else "n/d"
            )
            print(
                f"{r['nombre']:<24}{r['filas']:>8}{r['sin_cache_p95']:>10.1f}ms"
                f"{r['con_cache_p95']:>11.1f}ms{r['con_cache_hits_media']:>10.2f}ms{mejora:>10}"
            )

        print("\n" + "=" * 78)
        print("CA1: rangos de hasta 7 días por debajo de 1s (p95)")
        print("=" * 78)
        for r in resultados:
            if r["nombre"].startswith(("Gráfico 1 día", "Gráfico 7 días")):
                estado = "OK " if r["con_cache_p95"] < 1000 else "NO "
                print(
                    f"{estado}{r['nombre']}: p95 con caché = {r['con_cache_p95']:.1f}ms "
                    f"(sin caché {r['sin_cache_p95']:.1f}ms)"
                )
        print(
            "\nNOTA: medición LOCAL contra docker compose (Postgres + Redis en localhost) "
            "sobre\ndataset sintético. NO es una medición de staging real."
        )

        print("\n" + "=" * 78)
        print("Punto 4: partition pruning de HT-08 sobre la consulta de 7 días")
        print("=" * 78)
        plan = _explain(db, sede.id_sd, 7)
        print(plan)
        particiones_totales = db.execute(
            text("SELECT count(*) FROM pg_tables WHERE tablename ~ '^tlmtr_[0-9]{4}_[0-9]{2}$'")
        ).scalar()
        tocadas = sum(
            1
            for linea in plan.splitlines()
            if (" on tlmtr_" in linea) and ("Seq Scan" in linea or "Index" in linea)
        )
        print(
            f"\nParticiones tocadas: {tocadas} de {particiones_totales}. "
            + (
                "OK: el filtro de fecha del endpoint permite descartar particiones."
                if tocadas < particiones_totales
                else "ADVERTENCIA: no se descartó ninguna partición, revisar."
            )
        )
    finally:
        cache.invalidar_todo()
        db.close()


if __name__ == "__main__":
    main()
