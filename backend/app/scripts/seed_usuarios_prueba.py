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

Uso:
    python -m app.scripts.seed_usuarios_prueba
"""

from app.database import SessionLocal
from app.models import Cliente, PermisoUsuarioSede, Rol, Sede, Usuario
from app.security.hashing import hash_password  # ver sección 2 si no existe aún

ROLES = ["Administrador", "Técnico CENERIS", "Cliente Final", "Administrador Comercial"]

# Módulos válidos según el CHECK constraint de prms_usr_sd (HT-03).
MODULOS = ["Usuarios", "Ubicaciones", "Dispositivos", "Ingesta", "Tableros", "Alarmas", "Comercial"]

# rol -> módulo -> nivel ('Lectura' | 'Edición'). Un módulo ausente para un
# rol equivale a 'Ninguno' (sin fila = sin acceso, ver tiene_permiso()).
PERMISOS_POR_ROL = {
    "Administrador": {modulo: "Edición" for modulo in MODULOS},
    "Técnico CENERIS": {
        "Ubicaciones": "Edición",
        "Dispositivos": "Edición",
        "Ingesta": "Edición",
        "Tableros": "Edición",
        "Alarmas": "Edición",
        "Usuarios": "Lectura",
        "Comercial": "Lectura",
    },
    "Cliente Final": {
        "Ubicaciones": "Lectura",
        "Dispositivos": "Lectura",
        "Tableros": "Lectura",
        # HU28 declara al Cliente Final como quien crea las alarmas ("YO
        # COMO Cliente Final, DESEO crear una nueva alarma"), así que el
        # nivel sembrado pasa de Lectura a Edición: con Lectura, el rol
        # dueño de la HU recibía 403 al guardar.
        "Alarmas": "Edición",
    },
    "Administrador Comercial": {
        "Comercial": "Edición",
        "Ubicaciones": "Lectura",
        "Dispositivos": "Lectura",
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


def main():
    db = SessionLocal()
    try:
        print("Creando roles...")
        roles_creados = {nombre: obtener_o_crear_rol(db, nombre) for nombre in ROLES}

        print("\nCreando sede demo...")
        sede_demo = obtener_o_crear_sede_demo(db)

        print("\nCreando usuarios de prueba...")
        for datos in USUARIOS_PRUEBA:
            rol = roles_creados[datos["rol"]]
            usuario = obtener_o_crear_usuario(db, datos, rol)
            otorgar_permisos_de_rol(db, usuario, rol, sede_demo)

        print("\nListo. Credenciales de prueba (misma contraseña para todos):")
        print(f"  Password: {PASSWORD_PRUEBA}")
        for datos in USUARIOS_PRUEBA:
            print(f"  - {datos['crr']}  ({datos['rol']})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
