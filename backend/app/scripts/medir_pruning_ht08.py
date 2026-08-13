"""
HT-08 CA2: mide y deja registrado el partition pruning de tlmtr con la
forma de consulta típica de HU12/HU13 (filtro por sede + rango de
fechas), corriendo EXPLAIN (ANALYZE, BUFFERS) contra datos reales.

Este script existe porque la medición que documenta el README
("Partition pruning verificado (CA2)") no era reproducible: no había
manera de regenerar el dataset que produjo esos números. HT-16
(optimización de índices, sprint posterior) va a necesitar repetir esta
medición con más sedes/dispositivos, así que conviene dejar el
generador, no solo el resultado de una corrida.

Genera datos sintéticos bajo un cliente/sede identificados por nombre
("HT-08 medición pruning") para poder limpiarlos y volver a correr el
script tantas veces como haga falta sin acumular filas de corridas
anteriores ni tocar datos reales de otros clientes/sedes.

Uso (contra una BD de dev/test, NUNCA producción):
    python -m app.scripts.medir_pruning_ht08
    python -m app.scripts.medir_pruning_ht08 --meses 7 --horas 3
"""
import argparse
import datetime as dt

from sqlalchemy import text

from app.database import SessionLocal
from app.models import Cliente, ConexionFTP, Dispositivo, MapeoFormato, Parametro, Sede, Ubicacion
from app.services.particiones import asegurar_particiones

NOMBRE_CLIENTE = "HT-08 medición pruning"
NOMBRE_PARAMETRO = "Temperatura pruning HT-08"


def _limpiar_corrida_anterior(db) -> None:
    # tlmtr referencia a prmtr por FK: hay que vaciar tlmtr antes de poder
    # borrar el parámetro sintético, y solo entonces borrarlo (es un
    # catálogo global, no cuelga de cliente/sede, así que se limpia
    # aparte y siempre, incluso si una corrida anterior falló a mitad de
    # camino y no llegó a borrar el cliente).
    cliente = db.query(Cliente).filter(Cliente.rzn_scl == NOMBRE_CLIENTE).first()
    if cliente is not None:
        for sede in db.query(Sede).filter(Sede.id_clnt == cliente.id_clnt):
            db.execute(text("DELETE FROM tlmtr WHERE id_sd = :id_sd"), {"id_sd": sede.id_sd})
<<<<<<< HEAD
        # MapeoFormato ahora cuelga de Dispositivo (id_dspstv), así que se
        # borra antes que Dispositivo, no después.
        db.query(MapeoFormato).filter(
            MapeoFormato.id_dspstv.in_(
                db.query(Dispositivo.id_dspstv).join(Ubicacion).join(Sede).filter(
                    Sede.id_clnt == cliente.id_clnt
                )
            )
=======
        # DEC-09: mp_frmt referencia a dspstv, así que los mapeos se borran
        # ANTES que los dispositivos (antes era al revés: dspstv.id_mp
        # apuntaba a mp_frmt).
        ids_dispositivos = db.query(Dispositivo.id_dspstv).filter(
            Dispositivo.id_ubccn.in_(
                db.query(Ubicacion.id_ubccn).join(Sede).filter(Sede.id_clnt == cliente.id_clnt)
            )
        )
        db.query(MapeoFormato).filter(
            MapeoFormato.id_dspstv.in_(ids_dispositivos)
>>>>>>> 9cc2710c1fbe0adfb3cde23c8f9f64de00d99853
        ).delete(synchronize_session=False)
        db.query(Dispositivo).filter(
            Dispositivo.id_ubccn.in_(
                db.query(Ubicacion.id_ubccn).join(Sede).filter(Sede.id_clnt == cliente.id_clnt)
            )
        ).delete(synchronize_session=False)
        db.query(Ubicacion).filter(
            Ubicacion.id_sd.in_(db.query(Sede.id_sd).filter(Sede.id_clnt == cliente.id_clnt))
        ).delete(synchronize_session=False)
        db.query(ConexionFTP).filter(
            ConexionFTP.id_sd.in_(db.query(Sede.id_sd).filter(Sede.id_clnt == cliente.id_clnt))
        ).delete(synchronize_session=False)
        db.query(Sede).filter(Sede.id_clnt == cliente.id_clnt).delete(synchronize_session=False)
        db.query(Cliente).filter(Cliente.id_clnt == cliente.id_clnt).delete(synchronize_session=False)

    db.query(Parametro).filter(Parametro.nmbr == NOMBRE_PARAMETRO).delete(synchronize_session=False)
    db.flush()


def _sembrar(db, meses: int, horas_entre_lecturas: int):
    cliente = Cliente(rzn_scl=NOMBRE_CLIENTE, rc="00000000000", crr_cntct="ht08@pangea-dev.com")
    db.add(cliente)
    db.flush()

    sedes = [Sede(id_clnt=cliente.id_clnt, nmbr=f"Sede pruning {i}") for i in range(1, 3)]
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
            id_sd=sede.id_sd, nmbr=f"FTP {sede.nmbr}", hst="host", usr_ftp="u", rt_rmt="/", crdncl_cfrd="x"
        )
        db.add_all([ubicacion, conexion])
        db.flush()
        # DEC-09: primero el dispositivo, y el mapeo cuelga de él.
        dispositivo = Dispositivo(
            id_ubccn=ubicacion.id_ubccn, id_cnxn=conexion.id_cnxn,
            nmbr=f"Disp {sede.nmbr}", mrc="Marca pruning", lttd=4.6, lngtd=-74.0,
        )
        db.add(dispositivo)
        db.flush()
<<<<<<< HEAD
        mapeo = MapeoFormato(
            id_dspstv=dispositivo.id_dspstv, frmt_fch="%Y-%m-%d %H:%M:%S",
        )
        db.add(mapeo)
=======
        db.add(
            MapeoFormato(
                id_dspstv=dispositivo.id_dspstv, frmt_fch="%Y-%m-%d %H:%M:%S",
            )
        )
>>>>>>> 9cc2710c1fbe0adfb3cde23c8f9f64de00d99853
        db.flush()
        dispositivos.append((dispositivo, sede))

    hoy = dt.date.today()
    desde = hoy.replace(day=1)
    asegurar_particiones(db.connection(), desde, meses)

    for dispositivo, sede in dispositivos:
        db.execute(
            text(
                "INSERT INTO tlmtr (fch_hr, id_dspstv, id_prmtr, id_sd, vlr) "
                "SELECT g, :id_dspstv, :id_prmtr, :id_sd, random() * 100 "
                "FROM generate_series(:desde, :hasta, make_interval(hours => :paso)) AS g"
            ),
            {
                "id_dspstv": dispositivo.id_dspstv,
                "id_prmtr": parametro.id_prmtr,
                "id_sd": sede.id_sd,
                "desde": desde,
                "hasta": desde + dt.timedelta(days=30 * meses),
                "paso": horas_entre_lecturas,
            },
        )
    db.execute(text("ANALYZE tlmtr"))
    db.flush()
    return sedes[0], desde


def _explicar(db, id_sd: int, desde: dt.date) -> str:
    mes_siguiente = (desde.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    filas = db.execute(
        text(
            "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) "
            "SELECT fch_hr, vlr FROM tlmtr "
            "WHERE id_sd = :id_sd AND fch_hr >= :desde AND fch_hr < :hasta "
            "ORDER BY fch_hr"
        ),
        {"id_sd": id_sd, "desde": desde, "hasta": mes_siguiente},
    ).all()
    return "\n".join(fila[0] for fila in filas)


def _explicar_sin_filtro_fecha(db, id_sd: int) -> str:
    filas = db.execute(
        text(
            "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) "
            "SELECT fch_hr, vlr FROM tlmtr WHERE id_sd = :id_sd ORDER BY fch_hr"
        ),
        {"id_sd": id_sd},
    ).all()
    return "\n".join(fila[0] for fila in filas)


def _contar_particiones_tocadas(plan_texto: str) -> int:
    return sum(
        1 for linea in plan_texto.splitlines()
        if (" on tlmtr_" in linea) and ("Seq Scan" in linea or "Index" in linea)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meses", type=int, default=7, help="meses de datos a generar (default: 7)")
    parser.add_argument(
        "--horas", type=int, default=3, help="horas entre lecturas sintéticas (default: 3)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        _limpiar_corrida_anterior(db)
        sede, desde = _sembrar(db, args.meses, args.horas)
        db.commit()

        total = db.execute(text("SELECT count(*) FROM tlmtr WHERE id_sd = :id_sd"), {"id_sd": sede.id_sd}).scalar()
        particiones = db.execute(
            text("SELECT count(*) FROM pg_tables WHERE tablename ~ '^tlmtr_[0-9]{4}_[0-9]{2}$'")
        ).scalar()

        print(f"Datos sintéticos: {total} filas para sede id_sd={sede.id_sd}, {particiones} particiones existentes\n")

        print("=" * 70)
        print(f"CON filtro de sede + rango de fecha (mes de {desde.isoformat()}, forma de HU12/HU13):")
        print("=" * 70)
        plan_con_filtro = _explicar(db, sede.id_sd, desde)
        print(plan_con_filtro)
        tocadas_con_filtro = _contar_particiones_tocadas(plan_con_filtro)

        print("\n" + "=" * 70)
        print("SIN filtro de fecha (control, para comparar):")
        print("=" * 70)
        plan_sin_filtro = _explicar_sin_filtro_fecha(db, sede.id_sd)
        print(plan_sin_filtro)
        tocadas_sin_filtro = _contar_particiones_tocadas(plan_sin_filtro)

        print("\n" + "=" * 70)
        print("RESUMEN (CA2)")
        print("=" * 70)
        print(f"Con filtro de rango mensual: {tocadas_con_filtro} de {particiones} particiones tocadas")
        print(f"Sin filtro de fecha:         {tocadas_sin_filtro} de {particiones} particiones tocadas")
        if tocadas_con_filtro < particiones:
            print("\nOK: el planner descarta particiones irrelevantes con el filtro de fecha. CA2 cumplido.")
        else:
            print("\nADVERTENCIA: el filtro de fecha no redujo las particiones tocadas, revisar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
