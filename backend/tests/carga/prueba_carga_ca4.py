"""
HT-05 CA4: "la cola soporta al menos un archivo por minuto por datalogger
sin cuellos de botella perceptibles".

Prueba de carga MANUAL (no está en CI todavía). Levanta un servidor FTP
local que sirve los fixtures de backend/tests/fixtures/, crea N conexiones
cnxn_ftp de prueba apuntando a él, encola de golpe N_ARCHIVOS por conexión
y mide cuánto tarda la cola real (Celery + Redis + worker) en dejarlas
todas en estado terminal.

IMPORTANTE: corre contra la base de datos LOCAL. Verifica antes que el
stack esté levantado SIN docker-compose.override.aws-test.yml, si no
estarías escribiendo datos de prueba en la RDS compartida:

    docker compose -f docker-compose.yml --profile full up -d

Uso:
    cd backend
    ./venv/Scripts/python.exe tests/carga/prueba_carga_ca4.py
    ./venv/Scripts/python.exe tests/carga/prueba_carga_ca4.py --limpiar

Todo lo que crea queda marcado con el prefijo PREFIJO_PRUEBA para poder
borrarlo después con --limpiar.
"""
import argparse
import datetime as dt
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

from sqlalchemy import text

from app.database import SessionLocal
from app.models.archivo_ingesta import ArchivoIngesta
from app.models.mapeo_dispositivo import (
    Dispositivo, MapeoColumna, MapeoFormato, Parametro,
)
from app.models.telemetria import Telemetria
from app.models.ubicacion_conexion import ConexionFTP, Ubicacion
from app.security.ftp_crypto import encrypt_credential
from app.services.ingesta.estandarizador import mapeo_de_ejemplo
from app.tasks.ingesta import procesar_archivo_dat

PREFIJO_PRUEBA = "CARGA_CA4_"
FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"

USUARIO_FTP = "pangea_test"
PASSWORD_FTP = "pangea_test"
PUERTO_FTP = 2121

# Escenario: 5 dataloggers x 12 archivos = 60 archivos encolados de golpe.
# 12 archivos/datalogger representa ~12 minutos de operación real (1
# archivo/minuto/datalogger, el mínimo que exige CA4) comprimidos en una
# sola ráfaga instantánea: si la cola los absorbe en bastante menos de 12
# minutos, CA4 se cumple con margen.
N_CONEXIONES = 5
N_ARCHIVOS_POR_CONEXION = 12
TIMEOUT_SEGUNDOS = 600

ESTADOS_TERMINALES = ("Exitoso", "Fallido")


def _ip_alcanzable_desde_worker() -> str:
    """El worker corre en un contenedor: 'localhost' sería el contenedor
    mismo, no esta máquina. host.docker.internal resuelve al host desde
    dentro de Docker Desktop."""
    return os.environ.get("HOST_FTP_PRUEBA", "host.docker.internal")


def _ip_lan_del_host() -> str:
    """IP numérica de esta máquina en la LAN.

    masquerade_address DEBE ser una IP, no un hostname: viaja dentro de la
    respuesta 227 del protocolo FTP ("227 Entering passive mode
    (h1,h2,h3,h4,p1,p2)"), que solo admite octetos numéricos. Poner ahí
    'host.docker.internal' produce "227 Entering passive mode
    (host,docker,internal,...)", que el cliente ftplib no puede parsear y
    la descarga falla.
    """
    forzada = os.environ.get("IP_MASQUERADE_PRUEBA")
    if forzada:
        return forzada
    # No envía tráfico (UDP sin connect real), solo fuerza al SO a elegir
    # la interfaz de salida y así descubrir su IP local.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def levantar_ftp(directorio: str) -> FTPServer:
    autorizador = DummyAuthorizer()
    autorizador.add_user(USUARIO_FTP, PASSWORD_FTP, directorio, perm="elr")
    manejador = FTPHandler
    manejador.authorizer = autorizador
    # El worker está en otra red (contenedor): el modo pasivo debe anunciar
    # un rango de puertos fijo y alcanzable, no uno aleatorio.
    manejador.passive_ports = range(30000, 30020)
    manejador.masquerade_address = _ip_lan_del_host()

    servidor = FTPServer(("0.0.0.0", PUERTO_FTP), manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return servidor


def _fecha_en_particion_existente(db) -> dt.datetime:
    """Devuelve una fecha cubierta por alguna partición de tlmtr.

    tlmtr está particionada por rango mensual y las particiones se crean
    por adelantado (ver migración eadc512979fc y el job de HT-08). Los
    fixtures traen fechas de junio 2026, para las que NO hay partición:
    insertarlas produce "no partition of relation tlmtr found for row" y
    la prueba mediría ese fallo en vez de la capacidad de la cola.

    Tampoco sirve la partición más reciente sin más: suele ser de un mes
    futuro, y PP-99 rechaza por diseño los timestamps futuros. Se busca la
    partición del mes actual y, si no existe, la más reciente que ya haya
    empezado.
    """
    filas = db.execute(text(
        "SELECT tablename FROM pg_tables WHERE tablename ~ '^tlmtr_[0-9]{4}_[0-9]{2}$' "
        "ORDER BY tablename"
    )).all()
    if not filas:
        raise RuntimeError(
            "tlmtr no tiene particiones mensuales; corre las migraciones "
            "antes de la prueba de carga."
        )

    ahora = dt.datetime.now()
    candidatas = []
    for (tabla,) in filas:
        anio, mes = tabla.split("_")[1:3]
        inicio = dt.datetime(int(anio), int(mes), 1)
        if inicio <= ahora:  # descarta particiones de meses futuros
            candidatas.append(inicio)

    if not candidatas:
        raise RuntimeError(
            "Todas las particiones de tlmtr son de meses futuros; no hay "
            "ninguna donde escribir lecturas con timestamp no futuro."
        )

    inicio = max(candidatas)
    if (inicio.year, inicio.month) == (ahora.year, ahora.month):
        # Mes en curso: un par de horas atrás, nunca en el futuro.
        return (ahora - dt.timedelta(hours=2)).replace(microsecond=0)
    return inicio.replace(day=15, hour=10)


def preparar_directorio_ftp(fecha: dt.datetime) -> str:
    """Copia los fixtures al directorio servido, generando N_ARCHIVOS por
    conexión con nombres únicos. Alterna las dos cadencias reales:
    H_ (periódico cada 15 min) y E_ (irregular por evento).

    La fecha original del fixture se sustituye por `fecha` (dentro de una
    partición existente de tlmtr); cada archivo recibe además un minuto
    distinto para que las lecturas no colisionen entre sí."""
    directorio = tempfile.mkdtemp(prefix="pangea_carga_")
    fixture_estado = FIXTURES / "ejemplo_estado_gabinete.dat"
    fixture_agua = FIXTURES / "ejemplo_calidad_agua.dat"

    for i in range(N_CONEXIONES):
        for j in range(N_ARCHIVOS_POR_CONEXION):
            # H_ = trama periódica de calidad de agua; E_ = evento de estado
            if j % 3 == 0:
                origen, prefijo = fixture_estado, "E_"
            else:
                origen, prefijo = fixture_agua, "H_"

            # Se resta (no se suma) para no empujar ninguna marca al futuro:
            # PP-99 rechaza timestamps futuros.
            marca = fecha - dt.timedelta(minutes=i * N_ARCHIVOS_POR_CONEXION + j)
            contenido = origen.read_text(encoding="utf-8")
            # Los fixtures traen la fecha entre comillas al inicio de la fila
            # de datos; se reemplaza solo esa marca temporal principal.
            contenido = contenido.replace(
                '"2026-06-02 14:30:00"', f'"{marca:%Y-%m-%d %H:%M:%S}"'
            ).replace(
                '"2026-06-08 13:20:00"', f'"{marca:%Y-%m-%d %H:%M:%S}"'
            )

            destino = pathlib.Path(directorio) / f"{prefijo}{PREFIJO_PRUEBA}c{i}_{j}.dat"
            destino.write_text(contenido, encoding="utf-8")

    return directorio


def asegurar_datos_base(db) -> int:
    """La prueba necesita una sede + ubicación + los parámetros del mapeo
    mock, si no todo terminaría en 'Fallido' y estaríamos midiendo la
    velocidad de fallar, no la del pipeline. Crea lo mínimo y devuelve
    id_sd. Idempotente: reutiliza lo que ya exista."""
    fila = db.execute(text("SELECT id_sd FROM sd ORDER BY id_sd LIMIT 1")).first()
    if fila is None:
        cliente = db.execute(text(
            "INSERT INTO clnt (rzn_scl, rc, crr_cntct, estd) VALUES "
            "(:rz, :rc, :crr, 'Activo') RETURNING id_clnt"
        ), {
            "rz": f"{PREFIJO_PRUEBA}cliente",
            "rc": "99999999999",
            "crr": "carga_ca4@example.test",
        }).first()
        fila = db.execute(text(
            "INSERT INTO sd (id_clnt, nmbr, estd) VALUES "
            "(:c, :n, 'Activa') RETURNING id_sd"
        ), {"c": cliente[0], "n": f"{PREFIJO_PRUEBA}sede"}).first()
        db.commit()
    id_sd = fila[0]

    # Parámetros del mapeo mock (PP-98): sin fila en prmtr, guardar_lecturas
    # descarta la lectura y no se mediría la escritura en tlmtr.
    existentes = {p.nmbr for p in db.query(Parametro).all()}
    for nombre in set(mapeo_de_ejemplo().values()):
        if nombre not in existentes:
            db.add(Parametro(nmbr=nombre, undd="N/A", dscrpcn=f"{PREFIJO_PRUEBA}parametro"))
    db.commit()

    return id_sd


# Índice de columna (0-based sobre el header) -> parámetro estándar, para
# cada fixture. PP-96 resuelve el mapeo real desde mp_clmn, que referencia
# las columnas por índice, así que la prueba tiene que sembrarlo igual.
COLUMNAS_TRAMA_H = {  # ejemplo_calidad_agua.dat
    2: "bateria_v",
    9: "temperatura",
    10: "conductividad",
    16: "ph",
    19: "orp",
}
COLUMNAS_TRAMA_E = {  # ejemplo_estado_gabinete.dat
    4: "contador_puerta",
}


def crear_ubicacion(db, id_sd: int) -> Ubicacion:
    """Crea la ubicación de prueba. El mapeo de formato ya no cuelga de la
    ubicación/marca: se crea por dispositivo, en
    crear_mapeos_por_dispositivo(), una vez existen los dispositivos."""
    ubicacion = Ubicacion(
        id_sd=id_sd,
        nmbr=f"{PREFIJO_PRUEBA}ubicacion",
        lttd=0, lngtd=0,
        plgn_gjsn={"type": "Polygon", "coordinates": []},
        estd="Activa",
    )
    db.add(ubicacion)
    db.commit()
    return ubicacion


def crear_mapeos_por_dispositivo(db, dispositivos: list) -> None:
    """Crea los DOS formatos (H y E) con sus mapeos de columna para CADA
    dispositivo -ya no uno compartido por marca-, que es como PP-96 espera
    encontrarlos en mp_frmt/mp_clmn."""
    parametros = {p.nmbr: p.id_prmtr for p in db.query(Parametro).all()}
    for dispositivo in dispositivos:
        for tipo, columnas in (("H", COLUMNAS_TRAMA_H), ("E", COLUMNAS_TRAMA_E)):
            formato = MapeoFormato(
                id_dspstv=dispositivo.id_dspstv, tp_trm=tipo,
                dlmtdr=",", fl_inc_dts=1, frmt_fch="%Y-%m-%d %H:%M:%S", estd="Activo",
            )
            db.add(formato)
            db.flush()
            for indice, nombre_parametro in columnas.items():
                db.add(MapeoColumna(
                    id_mp=formato.id_mp,
                    indc_clmn=indice,
                    id_prmtr=parametros[nombre_parametro],
                ))
    db.commit()


def crear_conexiones(db, id_sd: int) -> list:
    """Crea N_CONEXIONES cnxn_ftp de prueba apuntando al FTP local."""
    credencial = encrypt_credential(PASSWORD_FTP)
    conexiones = []
    for i in range(N_CONEXIONES):
        cnxn = ConexionFTP(
            id_sd=id_sd,
            nmbr=f"{PREFIJO_PRUEBA}datalogger_{i}",
            prtcl="FTP",
            hst=_ip_alcanzable_desde_worker(),
            prt=PUERTO_FTP,
            usr_ftp=USUARIO_FTP,
            crdncl_cfrd=credencial,
            rt_rmt="/",
            frcnc_mnts=1,
            estd="Activa",
        )
        db.add(cnxn)
        conexiones.append(cnxn)
    db.commit()
    return conexiones


def crear_dispositivos(db, conexiones: list, ubicacion) -> list:
    """resolver_dispositivo (PP-100) exige exactamente 1 dispositivo activo
    por conexión; sin esto todo terminaría en 'Fallido'. El mapeo (H/E) se
    crea aparte, en crear_mapeos_por_dispositivo(), una vez existe cada
    dispositivo."""
    dispositivos = []
    for i, cnxn in enumerate(conexiones):
        dispositivo = Dispositivo(
            id_ubccn=ubicacion.id_ubccn,
            id_cnxn=cnxn.id_cnxn,
            nmbr=f"{PREFIJO_PRUEBA}dispositivo_{i}",
            mrc=f"{PREFIJO_PRUEBA}marca",
            lttd=0, lngtd=0,
            estd="Activo",
        )
        db.add(dispositivo)
        dispositivos.append(dispositivo)
    db.commit()
    return dispositivos


def encolar_archivos(db, conexiones: list) -> list:
    """Crea las filas archv_ingst en 'Pendiente' y encola los jobs de
    golpe, igual que haría sondear_conexiones_ftp pero sin esperar el
    tick de Beat."""
    ids = []
    for i, cnxn in enumerate(conexiones):
        for j in range(N_ARCHIVOS_POR_CONEXION):
            prefijo = "E_" if j % 3 == 0 else "H_"
            archivo = ArchivoIngesta(
                id_cnxn=cnxn.id_cnxn,
                nmbr_archv=f"{prefijo}{PREFIJO_PRUEBA}c{i}_{j}.dat",
            )
            db.add(archivo)
            db.flush()
            ids.append(archivo.id_archv)
    db.commit()

    for id_archv in ids:
        procesar_archivo_dat.delay(id_archv=id_archv)

    return ids


def esperar_procesamiento(db, ids: list) -> dict:
    """Sondea archv_ingst hasta que todos los ids estén en estado terminal
    o se agote el timeout. Devuelve métricas de la corrida."""
    inicio = time.monotonic()
    ultimo_reporte = 0.0
    historial = []

    while True:
        db.expire_all()
        filas = db.query(ArchivoIngesta).filter(ArchivoIngesta.id_archv.in_(ids)).all()
        conteo = {}
        for f in filas:
            conteo[f.estd] = conteo.get(f.estd, 0) + 1

        terminados = sum(conteo.get(e, 0) for e in ESTADOS_TERMINALES)
        transcurrido = time.monotonic() - inicio
        historial.append((transcurrido, terminados))

        if transcurrido - ultimo_reporte >= 2.0 or terminados == len(ids):
            print(
                f"  t={transcurrido:6.1f}s  terminados={terminados}/{len(ids)}  {conteo}",
                flush=True,
            )
            ultimo_reporte = transcurrido

        if terminados == len(ids):
            return {"segundos": transcurrido, "conteo": conteo, "historial": historial}

        if transcurrido > TIMEOUT_SEGUNDOS:
            return {
                "segundos": transcurrido,
                "conteo": conteo,
                "historial": historial,
                "timeout": True,
            }

        time.sleep(0.5)


def limpiar(db) -> None:
    """Borra todo lo que creó esta prueba (archv_ingst, tlmtr y cnxn_ftp
    con el prefijo)."""
    conexiones = db.query(ConexionFTP).filter(
        ConexionFTP.nmbr.like(f"{PREFIJO_PRUEBA}%")
    ).all()
    ids_cnxn = [c.id_cnxn for c in conexiones]

    archivos = db.query(ArchivoIngesta).filter(
        ArchivoIngesta.nmbr_archv.like(f"%{PREFIJO_PRUEBA}%")
    ).all()
    ids_archv = [a.id_archv for a in archivos]

    borradas_tlmtr = 0
    if ids_archv:
        borradas_tlmtr = db.query(Telemetria).filter(
            Telemetria.id_archv.in_(ids_archv)
        ).delete(synchronize_session=False)
        db.query(ArchivoIngesta).filter(
            ArchivoIngesta.id_archv.in_(ids_archv)
        ).delete(synchronize_session=False)

    # mp_frmt ahora cuelga de dspstv (id_dspstv): hay que borrar
    # mp_clmn -> mp_frmt ANTES de tocar dspstv, no después.
    ids_disp = [
        d.id_dspstv for d in db.query(Dispositivo).filter(
            Dispositivo.nmbr.like(f"{PREFIJO_PRUEBA}%")
        ).all()
    ]
    ids_mp = []
    if ids_disp:
        ids_mp = [
            m.id_mp for m in db.query(MapeoFormato).filter(
                MapeoFormato.id_dspstv.in_(ids_disp)
            ).all()
        ]
    if ids_mp:
        db.query(MapeoColumna).filter(
            MapeoColumna.id_mp.in_(ids_mp)
        ).delete(synchronize_session=False)
        db.query(MapeoFormato).filter(
            MapeoFormato.id_mp.in_(ids_mp)
        ).delete(synchronize_session=False)

    # dspstv referencia cnxn_ftp: hay que borrarlo antes que la conexión.
    borrados_disp = db.query(Dispositivo).filter(
        Dispositivo.nmbr.like(f"{PREFIJO_PRUEBA}%")
    ).delete(synchronize_session=False)

    if ids_cnxn:
        db.query(ConexionFTP).filter(
            ConexionFTP.id_cnxn.in_(ids_cnxn)
        ).delete(synchronize_session=False)

    db.query(Ubicacion).filter(
        Ubicacion.nmbr.like(f"{PREFIJO_PRUEBA}%")
    ).delete(synchronize_session=False)
    db.commit()
    print(
        f"Limpieza: {len(ids_archv)} archv_ingst, {borradas_tlmtr} tlmtr, "
        f"{borrados_disp} dspstv, {len(ids_cnxn)} cnxn_ftp borradas."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limpiar", action="store_true", help="solo borra los datos de prueba")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.limpiar:
            limpiar(db)
            return 0

        total = N_CONEXIONES * N_ARCHIVOS_POR_CONEXION
        print(f"Escenario: {N_CONEXIONES} dataloggers x {N_ARCHIVOS_POR_CONEXION} "
              f"archivos = {total} archivos encolados de golpe")

        fecha_lecturas = _fecha_en_particion_existente(db)
        print(f"Fecha base de las lecturas: {fecha_lecturas:%Y-%m-%d %H:%M:%S} "
              f"(dentro de una partición existente de tlmtr)")
        directorio = preparar_directorio_ftp(fecha_lecturas)
        servidor = levantar_ftp(directorio)
        print(f"FTP de prueba en {_ip_alcanzable_desde_worker()}:{PUERTO_FTP} "
              f"(masquerade {_ip_lan_del_host()}) sirviendo {directorio}")

        try:
            limpiar(db)  # arranca de cero por si quedó algo de una corrida previa
            id_sd = asegurar_datos_base(db)
            ubicacion = crear_ubicacion(db, id_sd)
            conexiones = crear_conexiones(db, id_sd)
            dispositivos = crear_dispositivos(db, conexiones, ubicacion)
            crear_mapeos_por_dispositivo(db, dispositivos)
            print(f"Creadas {len(conexiones)} conexiones cnxn_ftp + dispositivos de prueba")

            t0 = time.monotonic()
            ids = encolar_archivos(db, conexiones)
            t_encolado = time.monotonic() - t0
            print(f"Encolados {len(ids)} jobs en {t_encolado:.2f}s\n")

            resultado = esperar_procesamiento(db, ids)
        finally:
            servidor.close_all()

        print()
        print("=" * 62)
        segundos = resultado["segundos"]
        hubo_timeout = bool(resultado.get("timeout"))
        minutos_reales = N_ARCHIVOS_POR_CONEXION  # 1 archivo/min/datalogger

        if hubo_timeout:
            print(f"TIMEOUT tras {segundos:.1f}s - la cola NO drenó completa")
        else:
            print(f"Todos los archivos en estado terminal en {segundos:.1f}s")
            print(f"Throughput: {len(ids) / segundos:.2f} archivos/segundo "
                  f"({len(ids) / segundos * 60:.0f} archivos/minuto)")
        print(f"Estados finales: {resultado['conteo']}")

        # Verificación real de CA4: además de drenar a tiempo, los archivos
        # deben haberse procesado BIEN. Un archivo que termina en 'Fallido'
        # -o que se queda en 'Procesando'- no cuenta como procesado, y sin
        # filas en tlmtr el pipeline no llegó a persistir nada.
        exitosos = resultado["conteo"].get("Exitoso", 0)
        db.expire_all()
        filas_tlmtr = db.query(Telemetria).filter(
            Telemetria.id_archv.in_(ids)
        ).count()
        print(f"Filas escritas en tlmtr: {filas_tlmtr}")

        drenó_a_tiempo = (not hubo_timeout) and segundos < minutos_reales * 60
        todos_exitosos = exitosos == len(ids)
        persistió = filas_tlmtr > 0
        cumple = drenó_a_tiempo and todos_exitosos and persistió

        print()
        print(f"CA4: {total} archivos = {minutos_reales} min de operación real "
              f"(1 archivo/min/datalogger).")
        print(f"     Drenó a tiempo:      {'si' if drenó_a_tiempo else 'NO'} "
              f"({segundos / 60:.2f} min de {minutos_reales} min)")
        print(f"     Todos exitosos:      {'si' if todos_exitosos else 'NO'} "
              f"({exitosos}/{len(ids)})")
        print(f"     Persistió en tlmtr:  {'si' if persistió else 'NO'} "
              f"({filas_tlmtr} filas)")
        print(f"     -> {'CUMPLE' if cumple else 'NO CUMPLE'}")
        print("=" * 62)
        return 0 if cumple else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
