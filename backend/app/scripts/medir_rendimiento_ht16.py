"""
HT-16 CA1/CA5: mide el tiempo de respuesta p95 de GET /mediciones (HU32,
con valor_min/valor_max/frecuencia_muestreo) y GET /dispositivos (HU36,
con marca/ubicación/estado) contra un dataset equivalente a 5 clientes
activos, y deja el resultado documentado en backend/docs/ht16-rendimiento-consultas.md.

Mismo patrón que medir_pruning_ht08.py y medir_cache_ht10.py: siembra sus
propios datos sintéticos bajo clientes identificados por nombre, es
idempotente (limpia la corrida anterior antes de sembrar) y no toca datos
de otros clientes/sedes. A diferencia de esos dos scripts, mide contra el
ENDPOINT HTTP real (TestClient), no contra un SELECT directo: HT-16 pide
el p95 que percibe la vista, que incluye la resolución de permisos, la
serialización Pydantic y -en modo cursor- el merge en Python de
Telemetria + EventoTexto, no solo el tiempo de Postgres.

ESCALA: 5 clientes x 1 sede x 3 ubicaciones x 2 dispositivos x 4
parámetros numéricos, con una lectura cada 15 minutos durante 6 meses
(~2.1M filas en tlmtr). Es el mismo orden de magnitud que
backend/scripts/seed_benchmark_ht16.sql (ver ahí el razonamiento de la
escala); este script lo reimplementa en Python/SQLAlchemy para que sea
parte de la suite reproducible del proyecto, igual que sus dos
antecesores, en vez de un .sql aparte que hay que correr a mano.

Uso (contra una BD de dev/test, NUNCA producción):
    python -m app.scripts.medir_rendimiento_ht16
    python -m app.scripts.medir_rendimiento_ht16 --repeticiones 30
"""

import argparse
import datetime as dt
import statistics
import time

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal, get_db
from app.main import app
from app.models import Cliente, ConexionFTP, Dispositivo, MapeoFormato, Parametro, Sede, Ubicacion
from app.security.dependencies import get_current_user
from app.services.cache import consultas as cache

NOMBRE_CLIENTE_PREFIJO = "HT16-Bench-Cliente-"
N_CLIENTES = 5
N_UBICACIONES_POR_SEDE = 3
N_DISPOSITIVOS_POR_UBICACION = 2
N_PARAMETROS_POR_DISPOSITIVO = 4
MESES_DE_DATOS = 6
MINUTOS_ENTRE_LECTURAS = 15


def _limpiar_corrida_anterior(db) -> None:
    clientes = db.query(Cliente).filter(Cliente.rzn_scl.like(f"{NOMBRE_CLIENTE_PREFIJO}%")).all()
    for cliente in clientes:
        ids_sedes = db.query(Sede.id_sd).filter(Sede.id_clnt == cliente.id_clnt)
        ids_ubicaciones = db.query(Ubicacion.id_ubccn).filter(Ubicacion.id_sd.in_(ids_sedes))
        ids_dispositivos = db.query(Dispositivo.id_dspstv).filter(
            Dispositivo.id_ubccn.in_(ids_ubicaciones)
        )
        # tlmtr/evnt_txt se limpian con los ids YA MATERIALIZADOS (no una
        # subquery ORM directa en el DELETE): son las tablas más grandes
        # del dataset y un DELETE ... WHERE id_dspstv = ANY(:ids) con la
        # lista concreta es lo que deja usar el índice (id_dspstv, ...)
        # existente, en vez de correlacionar contra la subquery en cada fila.
        ids_dispositivos_lista = [i for (i,) in ids_dispositivos.all()]
        if ids_dispositivos_lista:
            db.execute(
                text("DELETE FROM tlmtr WHERE id_dspstv = ANY(:ids)"),
                {"ids": ids_dispositivos_lista},
            )
            db.execute(
                text("DELETE FROM evnt_txt WHERE id_dspstv = ANY(:ids)"),
                {"ids": ids_dispositivos_lista},
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
    for cliente in clientes:
        db.query(Cliente).filter(Cliente.id_clnt == cliente.id_clnt).delete(
            synchronize_session=False
        )
    db.query(Parametro).filter(Parametro.nmbr.like("HT16-Bench-Parametro-%")).delete(
        synchronize_session=False
    )
    db.flush()


def _sembrar(db):
    """5 clientes x 1 sede x 3 ubicaciones x 2 dispositivos x 4 parámetros,
    lecturas cada 15 min durante 6 meses. Devuelve (ubicaciones_ids,
    dispositivos_activos_muestra) para armar las consultas de referencia.
    """
    parametros = []
    for i in range(1, N_PARAMETROS_POR_DISPOSITIVO + 1):
        parametro = Parametro(nmbr=f"HT16-Bench-Parametro-{i}", undd="u")
        db.add(parametro)
        parametros.append(parametro)
    db.flush()

    ids_ubicaciones = []
    ids_dispositivos = []
    marcas = ["Campbell", "Vaisala", "Sutron"]

    for i_cliente in range(1, N_CLIENTES + 1):
        cliente = Cliente(
            rzn_scl=f"{NOMBRE_CLIENTE_PREFIJO}{i_cliente}",
            rc=f"BEN{i_cliente:08d}",
            crr_cntct=f"bench{i_cliente}@pangea-dev.com",
        )
        db.add(cliente)
        db.flush()

        sede = Sede(id_clnt=cliente.id_clnt, nmbr=f"HT16-Bench-Sede-{i_cliente}")
        db.add(sede)
        db.flush()

        for i_ub in range(1, N_UBICACIONES_POR_SEDE + 1):
            ubicacion = Ubicacion(
                id_sd=sede.id_sd,
                nmbr=f"HT16-Bench-Ubicacion-{i_cliente}-{i_ub}",
                lttd=4.6,
                lngtd=-74.0,
                plgn_gjsn={},
            )
            db.add(ubicacion)
            db.flush()
            ids_ubicaciones.append(ubicacion.id_ubccn)

            for i_d in range(1, N_DISPOSITIVOS_POR_UBICACION + 1):
                conexion = ConexionFTP(
                    id_sd=sede.id_sd,
                    nmbr=f"HT16-Bench-Cnxn-{ubicacion.id_ubccn}-{i_d}",
                    hst="bench.local",
                    usr_ftp="bench",
                    rt_rmt="/bench",
                    crdncl_cfrd="bench-credential-placeholder",
                )
                db.add(conexion)
                db.flush()
                dispositivo = Dispositivo(
                    id_ubccn=ubicacion.id_ubccn,
                    id_cnxn=conexion.id_cnxn,
                    nmbr=f"HT16-Bench-Dispositivo-{ubicacion.id_ubccn}-{i_d}",
                    mrc=marcas[(ubicacion.id_ubccn + i_d) % len(marcas)],
                    lttd=4.6,
                    lngtd=-74.0,
                )
                db.add(dispositivo)
                db.flush()
                db.add(MapeoFormato(id_dspstv=dispositivo.id_dspstv, frmt_fch="%Y-%m-%d %H:%M:%S"))
                db.flush()
                ids_dispositivos.append((dispositivo.id_dspstv, sede.id_sd))

    hasta = dt.datetime.now(dt.timezone.utc)
    desde = hasta - dt.timedelta(days=30 * MESES_DE_DATOS)

    for id_dspstv, id_sd in ids_dispositivos:
        for parametro in parametros:
            db.execute(
                text(
                    "INSERT INTO tlmtr (fch_hr, id_dspstv, id_prmtr, id_sd, vlr) "
                    "SELECT g, :id_dspstv, :id_prmtr, :id_sd, round((random() * 100)::numeric, 4) "
                    "FROM generate_series(:desde, :hasta, make_interval(mins => :paso)) AS g"
                ),
                {
                    "id_dspstv": id_dspstv,
                    "id_prmtr": parametro.id_prmtr,
                    "id_sd": id_sd,
                    "desde": desde,
                    "hasta": hasta,
                    "paso": MINUTOS_ENTRE_LECTURAS,
                },
            )
    db.execute(text("ANALYZE tlmtr"))
    db.flush()
    return ids_ubicaciones


def _p95(tiempos: list) -> float:
    ordenados = sorted(tiempos)
    indice = max(0, min(len(ordenados) - 1, int(round(0.95 * len(ordenados))) - 1))
    return ordenados[indice]


def _cronometrar_http(client, metodo_url_params, repeticiones: int) -> tuple[list, int]:
    """Devuelve (tiempos_ms, status_code_de_la_ultima_llamada)."""
    tiempos = []
    status = None
    for _ in range(repeticiones):
        inicio = time.perf_counter()
        resp = client.get(metodo_url_params[0], params=metodo_url_params[1])
        tiempos.append((time.perf_counter() - inicio) * 1000)
        status = resp.status_code
    return tiempos, status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repeticiones", type=int, default=20, help="repeticiones por consulta (default: 20)"
    )
    parser.add_argument(
        "--sin-poblar",
        action="store_true",
        help="no vuelve a sembrar datos: usa el dataset HT16-Bench-* ya existente",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if not args.sin_poblar:
            print("Limpiando corrida anterior (si existe)...")
            _limpiar_corrida_anterior(db)
            db.commit()
            print(
                f"Sembrando {N_CLIENTES} clientes x {N_UBICACIONES_POR_SEDE} ubicaciones x "
                f"{N_DISPOSITIVOS_POR_UBICACION} dispositivos x {N_PARAMETROS_POR_DISPOSITIVO} "
                f"parámetros, {MESES_DE_DATOS} meses cada {MINUTOS_ENTRE_LECTURAS} min "
                "(puede tardar más de un minuto)..."
            )
            ids_ubicaciones = _sembrar(db)
            db.commit()
        else:
            ids_ubicaciones = [
                u.id_ubccn
                for u in db.query(Ubicacion).filter(Ubicacion.nmbr.like("HT16-Bench-Ubicacion-%"))
            ]

        total_tlmtr = db.execute(
            text(
                "SELECT count(*) FROM tlmtr t JOIN dspstv d ON d.id_dspstv = t.id_dspstv "
                "WHERE d.nmbr LIKE 'HT16-Bench-%'"
            )
        ).scalar()
        print(f"Dataset: {len(ids_ubicaciones)} ubicaciones, {total_tlmtr} filas de tlmtr\n")

        cache.invalidar_todo()

        # Usuario Administrador simulado (scope global, sin restricción de
        # PermisoUbicacion): mismo patrón que tests/routers/*.py, vía
        # dependency_overrides -no hace falta un JWT real para medir el
        # costo del endpoint una vez resuelto el usuario.
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: {
            "sub": "1",
            "sede_id": None,
            "scope": "global",
            "rol": "Administrador",
        }
        client = TestClient(app)

        resultados = []

        # HU32: filtros avanzados sobre un rango acotado (modo cursor).
        ahora = dt.datetime.now(dt.timezone.utc)
        params_hu32 = {
            "fecha_inicio": (ahora - dt.timedelta(days=7)).isoformat(),
            "fecha_fin": ahora.isoformat(),
            "valor_min": "10",
            "valor_max": "90",
            "por_pagina": 50,
        }
        tiempos, status = _cronometrar_http(
            client, ("/mediciones", params_hu32), args.repeticiones
        )
        resultados.append(
            {
                "nombre": "HU32 GET /mediciones (valor_min/max, 7 días, cursor)",
                "status": status,
                "media_ms": statistics.mean(tiempos),
                "p95_ms": _p95(tiempos),
            }
        )

        # HU32: página siguiente por cursor (CA3: estable independiente de
        # la página pedida).
        primera = client.get("/mediciones", params=params_hu32).json()
        if primera.get("next_cursor"):
            params_pagina_2 = {**params_hu32, "cursor": primera["next_cursor"]}
            tiempos, status = _cronometrar_http(
                client, ("/mediciones", params_pagina_2), args.repeticiones
            )
            resultados.append(
                {
                    "nombre": "HU32 GET /mediciones (misma consulta, página 2 por cursor)",
                    "status": status,
                    "media_ms": statistics.mean(tiempos),
                    "p95_ms": _p95(tiempos),
                }
            )

        # HU32: frecuencia_muestreo (date_bin + DISTINCT ON).
        params_frecuencia = {
            "fecha_inicio": (ahora - dt.timedelta(days=7)).isoformat(),
            "fecha_fin": ahora.isoformat(),
            "frecuencia_muestreo": 60,
        }
        tiempos, status = _cronometrar_http(
            client, ("/mediciones", params_frecuencia), args.repeticiones
        )
        resultados.append(
            {
                "nombre": "HU32 GET /mediciones (frecuencia_muestreo=60, 7 días)",
                "status": status,
                "media_ms": statistics.mean(tiempos),
                "p95_ms": _p95(tiempos),
            }
        )

        # HU36: marca + ubicación + estado.
        params_hu36 = {"marca": "Campbell", "estado": "Activo", "por_pagina": 10}
        tiempos, status = _cronometrar_http(
            client, ("/dispositivos", params_hu36), args.repeticiones
        )
        resultados.append(
            {
                "nombre": "HU36 GET /dispositivos (marca+estado, offset/limit)",
                "status": status,
                "media_ms": statistics.mean(tiempos),
                "p95_ms": _p95(tiempos),
            }
        )

        # HU36: página lejana, para CA3 ("tiempos estables independiente
        # de la página pedida" -acá con offset, ver la decisión documentada
        # de por qué HU36 no migró a cursor).
        params_hu36_pagina_lejana = {**params_hu36, "pagina": 3}
        tiempos, status = _cronometrar_http(
            client, ("/dispositivos", params_hu36_pagina_lejana), args.repeticiones
        )
        resultados.append(
            {
                "nombre": "HU36 GET /dispositivos (misma consulta, página 3, offset)",
                "status": status,
                "media_ms": statistics.mean(tiempos),
                "p95_ms": _p95(tiempos),
            }
        )

        print("=" * 78)
        print(f"{'Consulta':<62}{'p95 (ms)':>8}  {'media':>6}")
        print("=" * 78)
        peor_p95 = 0.0
        for r in resultados:
            print(f"{r['nombre']:<62}{r['p95_ms']:>8.1f}  {r['media_ms']:>6.1f}")
            if r["status"] != 200:
                print(f"  ADVERTENCIA: status {r['status']} (se esperaba 200)")
            peor_p95 = max(peor_p95, r["p95_ms"])

        print("=" * 78)
        if peor_p95 < 1000:
            print(f"OK: peor p95 = {peor_p95:.1f}ms, bajo el umbral de 1000ms (CA1).")
        else:
            print(f"ADVERTENCIA: peor p95 = {peor_p95:.1f}ms, SUPERA el umbral de 1000ms (CA1).")
    finally:
        app.dependency_overrides.clear()
        db.close()


if __name__ == "__main__":
    main()
