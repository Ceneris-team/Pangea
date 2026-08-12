"""
Datos de prueba para la ficha del dispositivo (DEC-09 / IMP-06).

Siembra un escenario que cubre los casos de uso del rediseño, incluido el
bug que lo originó: dos dataloggers de la MISMA marca en la MISMA sede con
sensores distintos cableados.

Correr con el stack levantado (docker compose up -d):

    cd backend
    ./venv/Scripts/python.exe -m app.scripts.seed_dispositivos_demo

Es idempotente: se puede correr varias veces sin duplicar nada (busca por
nombre antes de insertar). Con --reset borra solo lo que este script creó
-sus dispositivos, mapeos, conexiones y ubicaciones- y lo vuelve a sembrar.

NO toca usuarios, roles ni permisos: usa la Sede Demo (la que ya tienen
asignada admin@ / tecnico@ / cliente@ en prms_usr_sd), porque un
dispositivo colgado de otra sede no sería visible desde la interfaz.

Para probar la pestaña "Carga de datos" hay un .dat por dispositivo en
backend/tests/fixtures/, con las columnas que espera cada mapeo:

    H_demo_rio_a.dat      -> [DEMO] CR1000 Río A       (pH, cond., ORP)
    H_demo_rio_b.dat      -> [DEMO] CR1000 Río B       (temp., batería)
    H_demo_gabinete.dat   -> [DEMO] Gabinete Planta    (trama H)
    E_demo_gabinete.dat   -> [DEMO] Gabinete Planta    (trama E)
    H_demo_sonda_eu.dat   -> [DEMO] Sonda EU           (';' y decimal ',')

El prefijo H_/E_ del nombre es lo que decide el tipo de trama, así que si
los renombras tiene que conservarse.
"""
import argparse
import datetime as dt
import sys

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import ConexionFTP, Dispositivo, Sede, Ubicacion
from app.models.archivo_ingesta import ArchivoIngesta
from app.models.mapeo_dispositivo import MapeoColumna, MapeoFormato, Parametro
from app.models.telemetria import Telemetria
from app.security.ftp_crypto import encrypt_credential

SEDE_DEMO = "Sede Demo"

POLIGONO = {
    "type": "Polygon",
    "coordinates": [
        [
            [-77.05, -12.05],
            [-77.05, -12.03],
            [-77.03, -12.03],
            [-77.03, -12.05],
            [-77.05, -12.05],
        ]
    ],
}

# Parámetros que el script necesita. Los que ya existan se reusan por
# nombre (prmtr.nmbr es UNIQUE); los que falten se crean con su unidad
# real, porque el catálogo sembrado a mano quedó con undd='N/A'.
PARAMETROS = {
    "temperatura": "C°",
    "ph": "pH",
    "conductividad": "uS/cm",
    "orp": "mV",
    "bateria_v": "V",
    "estado_gabinete": "N/A",
    "estado_puerta": "N/A",
    "contador_puerta": "N/A",
}

# Marca de agua para poder limpiar solo lo de este script (--reset).
PREFIJO = "[DEMO]"


def _log(mensaje: str) -> None:
    print(f"  {mensaje}")


def obtener_sede(db: Session) -> Sede:
    sede = db.query(Sede).filter(Sede.nmbr == SEDE_DEMO).first()
    if sede is None:
        sedes = [s.nmbr for s in db.query(Sede).all()]
        raise SystemExit(
            f"No existe la sede '{SEDE_DEMO}'. Sedes disponibles: {sedes}.\n"
            f"Este script siembra sobre la sede que ya tienen asignada los "
            f"usuarios de desarrollo; ajusta SEDE_DEMO si tu base usa otra."
        )
    return sede


def asegurar_parametros(db: Session) -> dict:
    """nombre -> Parametro, creando los que falten."""
    resultado = {}
    for nombre, unidad in PARAMETROS.items():
        parametro = db.query(Parametro).filter(Parametro.nmbr == nombre).first()
        if parametro is None:
            parametro = Parametro(nmbr=nombre, undd=unidad, dscrpcn="Sembrado por el script de demo")
            db.add(parametro)
            db.flush()
            _log(f"parámetro creado: {nombre} ({unidad})")
        resultado[nombre] = parametro
    return resultado


def asegurar_ubicacion(db: Session, sede: Sede, nombre: str) -> Ubicacion:
    ubicacion = (
        db.query(Ubicacion)
        .filter(Ubicacion.id_sd == sede.id_sd, Ubicacion.nmbr == nombre)
        .first()
    )
    if ubicacion is None:
        ubicacion = Ubicacion(
            id_sd=sede.id_sd,
            nmbr=nombre,
            dscrpcn="Ubicación de prueba (DEC-09)",
            lttd=-12.0464,
            lngtd=-77.0428,
            plgn_gjsn=POLIGONO,
            estd="Activa",
        )
        db.add(ubicacion)
        db.flush()
        _log(f"ubicación creada: {nombre}")
    return ubicacion


def asegurar_conexion(db: Session, sede: Sede, nombre: str, ruta: str, frecuencia: int) -> ConexionFTP:
    conexion = (
        db.query(ConexionFTP)
        .filter(ConexionFTP.id_sd == sede.id_sd, ConexionFTP.nmbr == nombre)
        .first()
    )
    if conexion is None:
        conexion = ConexionFTP(
            id_sd=sede.id_sd,
            nmbr=nombre,
            prtcl="FTP",
            hst="127.0.0.1",
            prt=21,
            usr_ftp="datalogger",
            # Se cifra con el helper real (HT-04): guardar texto plano acá
            # reventaría al descifrar en el sondeo.
            crdncl_cfrd=encrypt_credential("clave-de-prueba"),
            rt_rmt=ruta,
            frcnc_mnts=frecuencia,
            estd="Activa",
        )
        db.add(conexion)
        db.flush()
        _log(f"conexión FTP creada: {nombre} (polling {frecuencia} min)")
    return conexion


def asegurar_dispositivo(
    db: Session, ubicacion: Ubicacion, conexion: ConexionFTP, nombre: str,
    marca: str, modelo: str, estado: str = "Activo",
) -> Dispositivo:
    dispositivo = db.query(Dispositivo).filter(Dispositivo.nmbr == nombre).first()
    if dispositivo is None:
        dispositivo = Dispositivo(
            id_ubccn=ubicacion.id_ubccn,
            id_cnxn=conexion.id_cnxn,
            nmbr=nombre,
            mrc=marca,
            mdl=modelo,
            lttd=ubicacion.lttd,
            lngtd=ubicacion.lngtd,
            estd=estado,
        )
        db.add(dispositivo)
        db.flush()
        _log(f"dispositivo creado: {nombre} ({marca} {modelo}, {estado})")
    return dispositivo


def asegurar_mapeo(
    db: Session, dispositivo: Dispositivo, tp_trm: str, columnas: dict,
    dlmtdr: str = ",", dlmtdr_dcml: str = ".",
) -> MapeoFormato:
    """columnas: {indice_de_columna: Parametro}."""
    mapeo = (
        db.query(MapeoFormato)
        .filter(
            MapeoFormato.id_dspstv == dispositivo.id_dspstv,
            MapeoFormato.tp_trm == tp_trm,
            MapeoFormato.estd == "Activo",
        )
        .first()
    )
    if mapeo is None:
        mapeo = MapeoFormato(
            id_dspstv=dispositivo.id_dspstv,
            tp_trm=tp_trm,
            dlmtdr=dlmtdr,
            dlmtdr_dcml=dlmtdr_dcml,
            fl_inc_dts=1,
            frmt_fch="%Y-%m-%d %H:%M:%S",
            estd="Activo",
        )
        db.add(mapeo)
        db.flush()
        for indice, parametro in columnas.items():
            db.add(MapeoColumna(id_mp=mapeo.id_mp, indc_clmn=indice, id_prmtr=parametro.id_prmtr))
        db.flush()
        _log(
            f"mapeo {tp_trm} creado para {dispositivo.nmbr}: "
            f"{len(columnas)} columnas, decimal '{dlmtdr_dcml}'"
        )
    return mapeo


def sembrar_logs(db: Session, conexion: ConexionFTP, nombres_estados: list) -> None:
    """Filas de archv_ingst para que la pestaña Logs no salga vacía."""
    ahora = dt.datetime.now(dt.timezone.utc)
    for desfase, (nombre, estado, mensaje) in enumerate(nombres_estados):
        ya_existe = (
            db.query(ArchivoIngesta)
            .filter(
                ArchivoIngesta.id_cnxn == conexion.id_cnxn,
                ArchivoIngesta.nmbr_archv == nombre,
            )
            .first()
        )
        if ya_existe is not None:
            continue
        db.add(ArchivoIngesta(
            id_cnxn=conexion.id_cnxn,
            nmbr_archv=nombre,
            estd=estado,
            fch_dtccn=ahora - dt.timedelta(hours=desfase + 1),
            fch_prcsd=(ahora - dt.timedelta(hours=desfase + 1, minutes=-2)
                       if estado in ("Exitoso", "Fallido") else None),
            mnsj_errr=mensaje,
            rgstrs_prcsds=12 if estado == "Exitoso" else None,
        ))
    db.flush()


def limpiar(db: Session) -> None:
    """Borra solo lo sembrado por este script, en orden de dependencias."""
    dispositivos = db.query(Dispositivo).filter(Dispositivo.nmbr.like(f"{PREFIJO}%")).all()
    ids = [d.id_dspstv for d in dispositivos]
    conexiones = [d.id_cnxn for d in dispositivos]

    if ids:
        db.query(Telemetria).filter(Telemetria.id_dspstv.in_(ids)).delete(synchronize_session=False)
        mapeos = db.query(MapeoFormato).filter(MapeoFormato.id_dspstv.in_(ids)).all()
        if mapeos:
            db.query(MapeoColumna).filter(
                MapeoColumna.id_mp.in_([m.id_mp for m in mapeos])
            ).delete(synchronize_session=False)
            db.query(MapeoFormato).filter(
                MapeoFormato.id_dspstv.in_(ids)
            ).delete(synchronize_session=False)
    if conexiones:
        db.query(ArchivoIngesta).filter(
            ArchivoIngesta.id_cnxn.in_(conexiones)
        ).delete(synchronize_session=False)
    if ids:
        db.query(Dispositivo).filter(Dispositivo.id_dspstv.in_(ids)).delete(synchronize_session=False)
    if conexiones:
        db.query(ConexionFTP).filter(ConexionFTP.id_cnxn.in_(conexiones)).delete(synchronize_session=False)

    db.query(Ubicacion).filter(Ubicacion.nmbr.like(f"{PREFIJO}%")).delete(synchronize_session=False)
    db.commit()
    _log(f"limpiados {len(ids)} dispositivos de demo y sus dependencias")


def sembrar(db: Session) -> None:
    sede = obtener_sede(db)
    p = asegurar_parametros(db)

    ubicacion_rio = asegurar_ubicacion(db, sede, f"{PREFIJO} Río Rímac - Margen Izquierda")
    ubicacion_planta = asegurar_ubicacion(db, sede, f"{PREFIJO} Planta de Tratamiento")

    # --- CASO 1 y 2: el bug de DEC-09 -------------------------------------
    # Dos dataloggers de la MISMA marca en la MISMA sede, con sensores
    # distintos cableados. Antes compartían mapeo por (sede, marca) y las
    # lecturas del segundo se guardaban bajo el parámetro del primero.
    cnxn_a = asegurar_conexion(db, sede, f"{PREFIJO} FTP Río - Estación A", "/datos/estacion_a", 15)
    disp_a = asegurar_dispositivo(
        db, ubicacion_rio, cnxn_a, f"{PREFIJO} CR1000 Río A", "Campbell", "CR1000X",
    )
    # Calidad de agua: pH, conductividad, ORP.
    asegurar_mapeo(db, disp_a, "H", {1: p["ph"], 2: p["conductividad"], 3: p["orp"]})

    cnxn_b = asegurar_conexion(db, sede, f"{PREFIJO} FTP Río - Estación B", "/datos/estacion_b", 30)
    disp_b = asegurar_dispositivo(
        db, ubicacion_rio, cnxn_b, f"{PREFIJO} CR1000 Río B", "Campbell", "CR1000X",
    )
    # MISMA marca, MISMA sede, pero acá hay sensores de temperatura/batería.
    asegurar_mapeo(db, disp_b, "H", {1: p["temperatura"], 2: p["bateria_v"]})

    # --- CASO 3: un dispositivo con mapeo H y E a la vez -------------------
    cnxn_c = asegurar_conexion(db, sede, f"{PREFIJO} FTP Planta - Gabinete", "/datos/gabinete", 10)
    disp_c = asegurar_dispositivo(
        db, ubicacion_planta, cnxn_c, f"{PREFIJO} Gabinete Planta (H+E)", "Campbell", "CR300",
    )
    asegurar_mapeo(db, disp_c, "H", {1: p["temperatura"], 2: p["bateria_v"]})
    asegurar_mapeo(
        db, disp_c, "E",
        {1: p["estado_gabinete"], 2: p["estado_puerta"], 3: p["contador_puerta"]},
    )
    sembrar_logs(db, cnxn_c, [
        ("H_20260812_1200.dat", "Exitoso", None),
        ("E_20260812_1200.dat", "Exitoso", None),
        ("H_20260812_1100.dat", "Fallido",
         "No hay un formato activo (mp_frmt) para el dispositivo y el tipo de trama"),
        ("H_20260812_1300.dat", "Pendiente", None),
    ])

    # --- CASO 4: locale europeo (decimal con coma) ------------------------
    cnxn_d = asegurar_conexion(db, sede, f"{PREFIJO} FTP Planta - Sonda EU", "/datos/sonda_eu", 20)
    disp_d = asegurar_dispositivo(
        db, ubicacion_planta, cnxn_d, f"{PREFIJO} Sonda EU (decimal coma)", "OTT HydroMet", "ecoN",
    )
    # ';' de columna + ',' decimal: "23,5" es un número, no dos campos.
    asegurar_mapeo(
        db, disp_d, "H", {1: p["temperatura"], 2: p["ph"]},
        dlmtdr=";", dlmtdr_dcml=",",
    )

    # --- CASO 5: sin mapeo (recién creado) --------------------------------
    # Estado válido en DEC-09: se crea el dispositivo y el mapeo se
    # configura después. Sirve para probar la ficha en blanco y el error
    # "dispositivo sin configurar para este tipo de trama".
    cnxn_e = asegurar_conexion(db, sede, f"{PREFIJO} FTP Río - Estación Nueva", "/datos/nueva", 15)
    asegurar_dispositivo(
        db, ubicacion_rio, cnxn_e, f"{PREFIJO} Estación Nueva (sin mapeo)", "Sutron", "XLink 500",
    )

    # --- CASO 6: dispositivo inactivo -------------------------------------
    # Para probar el filtro por estado del listado (HU10).
    cnxn_f = asegurar_conexion(db, sede, f"{PREFIJO} FTP Planta - Retirada", "/datos/retirada", 60)
    disp_f = asegurar_dispositivo(
        db, ubicacion_planta, cnxn_f, f"{PREFIJO} Sonda Retirada", "Hach", "SC200",
        estado="Inactivo",
    )
    asegurar_mapeo(db, disp_f, "H", {1: p["ph"]})

    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true",
        help="borra lo sembrado por este script antes de volver a sembrarlo",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.reset:
            print("Limpiando datos de demo previos...")
            limpiar(db)
        print("Sembrando dispositivos de prueba (DEC-09)...")
        sembrar(db)

        print("\nListo. Dispositivos en la base:")
        for d in db.query(Dispositivo).order_by(Dispositivo.nmbr).all():
            mapeos = (
                db.query(MapeoFormato)
                .filter(MapeoFormato.id_dspstv == d.id_dspstv, MapeoFormato.estd == "Activo")
                .all()
            )
            tramas = "+".join(sorted(m.tp_trm for m in mapeos)) or "sin mapeo"
            print(f"  [{d.id_dspstv}] {d.nmbr} · {d.mrc} · {d.estd} · {tramas}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
