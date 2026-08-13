"""
Script de seed para HT-04 / HU-01, extendido en HT-09 para dejar el
middleware de autorización usable en dev apenas se corre este script.

Crea los 4 roles del sistema (si no existen), un usuario de prueba por
cada rol, una sede demo, y una fila en prms_usr_sd (HT-03) por cada
combinación rol/módulo de PERMISOS_POR_ROL. Antes de HT-09 este script no
sembraba ningún permiso: los 4 usuarios existían pero, apenas
require_permiso() empezó a consultar prms_usr_sd en vez de la matriz en
memoria, cualquier request habría devuelto 403 sin esto.

PERMISOS_POR_ROL es un punto de partida razonable, no una decisión de
producto cerrada -las reglas de negocio reales de HT-03 las define el
equipo de producto editando prms_usr_sd directamente, no este script-.

Además siembra datos de ejemplo para probar HU06/HU07/HU10/HU11 sin tener
que cargarlos a mano: 2 ubicaciones, una conexión FTP demo (host ficticio;
sirve para ver el flujo en la UI, no para recibir archivos reales), un
catálogo de parámetros, un mapeo de formato con columnas asignadas, y 2
dispositivos activos. El usuario Cliente Final de prueba recibe permiso
(HU21) sobre ambas ubicaciones para poder ver algo al loguearse.

Uso:
    python -m app.scripts.seed_usuarios_prueba
"""
from app.database import SessionLocal
from app.models import (
    ConexionFTP, Dispositivo, MapeoColumna, MapeoFormato, Parametro,
    PermisoUbicacion, PermisoUsuarioSede, Rol, Sede, Ubicacion, Usuario, Cliente,
)
from app.security.ftp_crypto import encrypt_credential
from app.security.hashing import hash_password  # ver sección 2 si no existe aún

ROLES = ["Administrador", "Técnico CENERIS", "Cliente Final", "Administrador Comercial"]

# Módulos válidos según el CHECK constraint de prms_usr_sd (HT-03).
MODULOS = ["Usuarios", "Ubicaciones", "Dispositivos", "Ingesta", "Tableros", "Alarmas", "Comercial"]

# rol -> módulo -> nivel ('Lectura' | 'Edición'). Un módulo ausente para un
# rol equivale a 'Ninguno' (sin fila = sin acceso, ver tiene_permiso()).
PERMISOS_POR_ROL = {
    "Administrador": {modulo: "Edición" for modulo in MODULOS},
    "Técnico CENERIS": {
        "Ubicaciones": "Edición", "Dispositivos": "Edición", "Ingesta": "Edición",
        "Tableros": "Edición", "Alarmas": "Edición",
        "Usuarios": "Lectura", "Comercial": "Lectura",
    },
    "Cliente Final": {
        "Ubicaciones": "Lectura", "Dispositivos": "Lectura",
        "Tableros": "Lectura", "Alarmas": "Lectura",
    },
    "Administrador Comercial": {
        "Comercial": "Edición", "Ubicaciones": "Lectura", "Dispositivos": "Lectura",
    },
}

# password de prueba única para todos: cumple HU02 (8+ caracteres, 1 mayúscula, 1 número)
PASSWORD_PRUEBA = "Pangea2026"

USUARIOS_PRUEBA = [
    {
        "nmbr_cmplt": "Ana Administrador",
        "crr": "admin@pangea-dev.com",
        "rol": "Administrador",
        "scp": "global",
    },
    {
        "nmbr_cmplt": "Carlos Tecnico",
        "crr": "tecnico@pangea-dev.com",
        "rol": "Técnico CENERIS",
        "scp": "global",
    },
    {
        "nmbr_cmplt": "Luis Cliente",
        "crr": "cliente@pangea-dev.com",
        "rol": "Cliente Final",
        "scp": "por_sede",
    },
    {
        "nmbr_cmplt": "Maria Comercial",
        "crr": "comercial@pangea-dev.com",
        "rol": "Administrador Comercial",
        "scp": "global",
    },
]


# --- Datos de ejemplo (ubicaciones, dispositivos) --------------------------

UBICACIONES_DEMO = [
    {
        "nmbr": "Estación Norte",
        "dscrpcn": "Estación de monitoreo en el sector norte",
        "lttd": -16.500000,
        "lngtd": -68.150000,
        "plgn_gjsn": {
            "type": "Polygon",
            "coordinates": [[
                [-68.1520, -16.4980], [-68.1480, -16.4980],
                [-68.1480, -16.5020], [-68.1520, -16.5020],
                [-68.1520, -16.4980],
            ]],
        },
    },
    {
        "nmbr": "Estación Sur",
        "dscrpcn": "Estación de monitoreo en el sector sur",
        "lttd": -16.550000,
        "lngtd": -68.140000,
        "plgn_gjsn": {
            "type": "Polygon",
            "coordinates": [[
                [-68.1420, -16.5480], [-68.1380, -16.5480],
                [-68.1380, -16.5520], [-68.1420, -16.5520],
                [-68.1420, -16.5480],
            ]],
        },
    },
]

PARAMETROS_DEMO = [
    {"nmbr": "Temperatura", "undd": "°C", "dscrpcn": "Temperatura ambiente"},
    {"nmbr": "Humedad", "undd": "%", "dscrpcn": "Humedad relativa"},
    {"nmbr": "pH", "undd": "pH", "dscrpcn": "Nivel de pH del agua"},
]

# Marca/formato usados por los dispositivos demo (HU06). El delimitador,
# fila de inicio y formato de fecha son valores típicos de un datalogger
# Campbell Scientific; el mapeo asigna la columna 1 a Temperatura y la 2 a
# Humedad, la columna 0 queda para la fecha (fuera de mp_clmn, ver HU06).
MAPEO_FORMATO_DEMO = {
    "mrc": "Campbell Scientific",
    "tp_trm": "H",
    "dlmtdr": ",",
    "fl_inc_dts": 1,
    "frmt_fch": "%Y-%m-%d %H:%M:%S",
}
MAPEO_COLUMNAS_DEMO = [
    {"indc_clmn": 1, "parametro": "Temperatura"},
    {"indc_clmn": 2, "parametro": "Humedad"},
]

# Conexiones FTP demo: host ficticio. Sirven para ver el flujo de HU05/HU06
# en la interfaz (selector de dispositivo, listar archivos-ftp, etc); no van
# a poder listar/descargar archivos reales porque no hay un servidor FTP
# corriendo en dev. Una por dispositivo: resolver_dispositivo() (ver
# routers/dispositivos.py) asume exactamente un dispositivo Activo por
# conexión, así que compartir una sola rompería esa regla en silencio.
CONEXIONES_FTP_DEMO = [
    {
        "nmbr": "FTP Estación Norte (demo)",
        "hst": "ftp-norte.demo.pangea.local",
        "prt": 21,
        "usr_ftp": "demo",
        "password": "DemoFtp2026",
        "rt_rmt": "/datos/estacion-norte",
        "frcnc_mnts": 15,
    },
    {
        "nmbr": "FTP Estación Sur (demo)",
        "hst": "ftp-sur.demo.pangea.local",
        "prt": 21,
        "usr_ftp": "demo",
        "password": "DemoFtp2026",
        "rt_rmt": "/datos/estacion-sur",
        "frcnc_mnts": 15,
    },
]

DISPOSITIVOS_DEMO = [
    {
        "nmbr": "Datalogger CR120",
        "mrc": "Campbell Scientific",
        "mdl": "CR120",
        "ubicacion": "Estación Norte",
        "conexion": "FTP Estación Norte (demo)",
    },
    {
        "nmbr": "Datalogger CR120-B",
        "mrc": "Campbell Scientific",
        "mdl": "CR120",
        "ubicacion": "Estación Sur",
        "conexion": "FTP Estación Sur (demo)",
    },
]


def obtener_o_crear_rol(db, nombre: str) -> Rol:
    rol = db.query(Rol).filter(Rol.nmbr == nombre).first()
    if rol is None:
        rol = Rol(nmbr=nombre, dscrpcn=f"Rol {nombre}")
        db.add(rol)
        db.commit()
        db.refresh(rol)
        print(f"  [+] Rol creado: {nombre}")
    return rol


def obtener_o_crear_usuario(db, datos: dict, rol: Rol) -> Usuario:
    usuario = db.query(Usuario).filter(Usuario.crr == datos["crr"]).first()
    if usuario is not None:
        print(f"  [=] Ya existe: {datos['crr']}")
        return usuario

    usuario = Usuario(
        id_rl=rol.id_rl,
        scp=datos["scp"],
        nmbr_cmplt=datos["nmbr_cmplt"],
        crr=datos["crr"],
        cntrsn_hsh=hash_password(PASSWORD_PRUEBA),
        estd="Activo",
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    print(f"  [+] Usuario creado: {datos['crr']} / rol={rol.nmbr}")
    return usuario


def obtener_o_crear_sede_demo(db) -> Sede:
    cliente = db.query(Cliente).filter(Cliente.rc == "00000000000").first()
    if cliente is None:
        cliente = Cliente(
            rzn_scl="Cliente Demo",
            rc="00000000000",
            crr_cntct="contacto@pangea-dev.com",
            estd="Activo",
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
        print("  [+] Cliente demo creado: Cliente Demo")

    sede = db.query(Sede).filter(Sede.id_clnt == cliente.id_clnt, Sede.nmbr == "Sede Demo").first()
    if sede is None:
        sede = Sede(id_clnt=cliente.id_clnt, nmbr="Sede Demo", estd="Activa")
        db.add(sede)
        db.commit()
        db.refresh(sede)
        print("  [+] Sede demo creada: Sede Demo")
    return sede


def otorgar_permisos_de_rol(db, usuario: Usuario, rol: Rol, sede: Sede) -> None:
    """Siembra en prms_usr_sd (HT-03) el nivel de PERMISOS_POR_ROL para cada
    módulo, sobre la sede demo. Necesario incluso para los usuarios con
    scope 'global' (HT-09 CA4: scope global exime del filtro de sede, no
    del de módulo/nivel -ver el docstring de tiene_permiso() en
    app/security/permisos.py-)."""
    permisos_modulo = PERMISOS_POR_ROL.get(rol.nmbr, {})
    for modulo, nivel in permisos_modulo.items():
        existente = (
            db.query(PermisoUsuarioSede)
            .filter(
                PermisoUsuarioSede.id_usr == usuario.id_usr,
                PermisoUsuarioSede.id_sd == sede.id_sd,
                PermisoUsuarioSede.mdl == modulo,
            )
            .first()
        )
        if existente is not None:
            continue
        db.add(
            PermisoUsuarioSede(
                id_usr=usuario.id_usr,
                id_sd=sede.id_sd,
                id_rl=rol.id_rl,
                mdl=modulo,
                nvl=nivel,
            )
        )
    db.commit()


def crear_ubicaciones_demo(db, sede: Sede) -> dict[str, Ubicacion]:
    ubicaciones = {}
    for datos in UBICACIONES_DEMO:
        ubicacion = (
            db.query(Ubicacion)
            .filter(Ubicacion.id_sd == sede.id_sd, Ubicacion.nmbr == datos["nmbr"])
            .first()
        )
        if ubicacion is None:
            ubicacion = Ubicacion(
                id_sd=sede.id_sd,
                nmbr=datos["nmbr"],
                dscrpcn=datos["dscrpcn"],
                lttd=datos["lttd"],
                lngtd=datos["lngtd"],
                plgn_gjsn=datos["plgn_gjsn"],
            )
            db.add(ubicacion)
            db.commit()
            db.refresh(ubicacion)
            print(f"  [+] Ubicación creada: {datos['nmbr']}")
        else:
            print(f"  [=] Ya existe: {datos['nmbr']}")
        ubicaciones[datos["nmbr"]] = ubicacion
    return ubicaciones


def crear_parametros_demo(db) -> dict[str, Parametro]:
    parametros = {}
    for datos in PARAMETROS_DEMO:
        parametro = db.query(Parametro).filter(Parametro.nmbr == datos["nmbr"]).first()
        if parametro is None:
            parametro = Parametro(nmbr=datos["nmbr"], undd=datos["undd"], dscrpcn=datos["dscrpcn"])
            db.add(parametro)
            db.commit()
            db.refresh(parametro)
            print(f"  [+] Parámetro creado: {datos['nmbr']}")
        else:
            print(f"  [=] Ya existe: {datos['nmbr']}")
        parametros[datos["nmbr"]] = parametro
    return parametros


def crear_mapeo_formato_demo(db, sede: Sede, parametros: dict[str, Parametro]) -> MapeoFormato:
    mapeo = (
        db.query(MapeoFormato)
        .filter(
            MapeoFormato.id_sd == sede.id_sd,
            MapeoFormato.mrc == MAPEO_FORMATO_DEMO["mrc"],
            MapeoFormato.tp_trm == MAPEO_FORMATO_DEMO["tp_trm"],
        )
        .first()
    )
    if mapeo is None:
        mapeo = MapeoFormato(id_sd=sede.id_sd, estd="Activo", **MAPEO_FORMATO_DEMO)
        db.add(mapeo)
        db.commit()
        db.refresh(mapeo)
        print(f"  [+] Mapeo de formato creado: {MAPEO_FORMATO_DEMO['mrc']}")

        for columna in MAPEO_COLUMNAS_DEMO:
            db.add(
                MapeoColumna(
                    id_mp=mapeo.id_mp,
                    indc_clmn=columna["indc_clmn"],
                    id_prmtr=parametros[columna["parametro"]].id_prmtr,
                )
            )
        db.commit()
        print(f"  [+] {len(MAPEO_COLUMNAS_DEMO)} columnas asignadas al mapeo")
    else:
        print(f"  [=] Ya existe: mapeo {MAPEO_FORMATO_DEMO['mrc']}")
    return mapeo


def crear_conexiones_ftp_demo(db, sede: Sede) -> dict[str, ConexionFTP]:
    conexiones = {}
    for datos in CONEXIONES_FTP_DEMO:
        conexion = (
            db.query(ConexionFTP)
            .filter(ConexionFTP.id_sd == sede.id_sd, ConexionFTP.nmbr == datos["nmbr"])
            .first()
        )
        if conexion is None:
            conexion = ConexionFTP(
                id_sd=sede.id_sd,
                nmbr=datos["nmbr"],
                prtcl="FTP",
                hst=datos["hst"],
                prt=datos["prt"],
                usr_ftp=datos["usr_ftp"],
                crdncl_cfrd=encrypt_credential(datos["password"]),
                rt_rmt=datos["rt_rmt"],
                frcnc_mnts=datos["frcnc_mnts"],
                estd="Activa",
            )
            db.add(conexion)
            db.commit()
            db.refresh(conexion)
            print(f"  [+] Conexión FTP creada: {datos['nmbr']}")
        else:
            print(f"  [=] Ya existe: {datos['nmbr']}")
        conexiones[datos["nmbr"]] = conexion
    return conexiones


def crear_dispositivos_demo(
    db,
    ubicaciones: dict[str, Ubicacion],
    conexiones: dict[str, ConexionFTP],
    mapeo: MapeoFormato,
) -> None:
    for datos in DISPOSITIVOS_DEMO:
        dispositivo = db.query(Dispositivo).filter(Dispositivo.nmbr == datos["nmbr"]).first()
        if dispositivo is not None:
            print(f"  [=] Ya existe: {datos['nmbr']}")
            continue

        ubicacion = ubicaciones[datos["ubicacion"]]
        dispositivo = Dispositivo(
            id_ubccn=ubicacion.id_ubccn,
            id_cnxn=conexiones[datos["conexion"]].id_cnxn,
            id_mp=mapeo.id_mp,
            nmbr=datos["nmbr"],
            mrc=datos["mrc"],
            mdl=datos["mdl"],
            lttd=ubicacion.lttd,
            lngtd=ubicacion.lngtd,
            estd="Activo",
        )
        db.add(dispositivo)
        db.commit()
        print(f"  [+] Dispositivo creado: {datos['nmbr']} ({datos['ubicacion']})")


def otorgar_permiso_ubicaciones_cliente(db, usuario: Usuario, ubicaciones: dict[str, Ubicacion]) -> None:
    """HU21: sin esto, el Cliente Final de prueba (scope 'por_sede') no ve
    ninguna ubicación en el listado (HU07 filtra por prms_ubccn) ni ningún
    dispositivo (HU10 filtra igual, vía la ubicación)."""
    for ubicacion in ubicaciones.values():
        existente = (
            db.query(PermisoUbicacion)
            .filter(
                PermisoUbicacion.id_usr == usuario.id_usr,
                PermisoUbicacion.id_ubccn == ubicacion.id_ubccn,
            )
            .first()
        )
        if existente is None:
            db.add(PermisoUbicacion(id_usr=usuario.id_usr, id_ubccn=ubicacion.id_ubccn))
    db.commit()


def main():
    db = SessionLocal()
    try:
        print("Creando roles...")
        roles_creados = {nombre: obtener_o_crear_rol(db, nombre) for nombre in ROLES}

        print("\nCreando sede demo...")
        sede_demo = obtener_o_crear_sede_demo(db)

        print("\nCreando usuarios de prueba...")
        usuarios_creados = {}
        for datos in USUARIOS_PRUEBA:
            rol = roles_creados[datos["rol"]]
            usuario = obtener_o_crear_usuario(db, datos, rol)
            otorgar_permisos_de_rol(db, usuario, rol, sede_demo)
            usuarios_creados[datos["rol"]] = usuario

        print("\nCreando ubicaciones de ejemplo...")
        ubicaciones_demo = crear_ubicaciones_demo(db, sede_demo)

        print("\nOtorgando acceso a esas ubicaciones al usuario Cliente Final...")
        otorgar_permiso_ubicaciones_cliente(db, usuarios_creados["Cliente Final"], ubicaciones_demo)

        print("\nCreando catálogo de parámetros...")
        parametros_demo = crear_parametros_demo(db)

        print("\nCreando mapeo de formato de ejemplo...")
        mapeo_demo = crear_mapeo_formato_demo(db, sede_demo, parametros_demo)

        print("\nCreando conexiones FTP de ejemplo...")
        conexiones_demo = crear_conexiones_ftp_demo(db, sede_demo)

        print("\nCreando dispositivos de ejemplo...")
        crear_dispositivos_demo(db, ubicaciones_demo, conexiones_demo, mapeo_demo)

        print("\nListo. Credenciales de prueba (misma contraseña para todos):")
        print(f"  Password: {PASSWORD_PRUEBA}")
        for datos in USUARIOS_PRUEBA:
            print(f"  - {datos['crr']}  ({datos['rol']})")
    finally:
        db.close()


if __name__ == "__main__":
    main()