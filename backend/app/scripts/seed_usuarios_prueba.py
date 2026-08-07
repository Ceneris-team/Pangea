"""
Script de seed para HT-04 / HU-01.

Crea los 4 roles del sistema (si no existen) y un usuario de prueba por
cada rol, con contraseña conocida para poder probar el login manualmente.

Uso:
    python -m app.scripts.seed_usuarios_prueba
"""
from app.database import SessionLocal
from app.models import Rol, Usuario
from app.security.hashing import hash_password  # ver sección 2 si no existe aún

ROLES = ["Administrador", "Técnico CENERIS", "Cliente Final", "Administrador Comercial"]

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


def main():
    db = SessionLocal()
    try:
        print("Creando roles...")
        roles_creados = {nombre: obtener_o_crear_rol(db, nombre) for nombre in ROLES}

        print("\nCreando usuarios de prueba...")
        for datos in USUARIOS_PRUEBA:
            obtener_o_crear_usuario(db, datos, roles_creados[datos["rol"]])

        print("\nListo. Credenciales de prueba (misma contraseña para todos):")
        print(f"  Password: {PASSWORD_PRUEBA}")
        for datos in USUARIOS_PRUEBA:
            print(f"  - {datos['crr']}  ({datos['rol']})")
    finally:
        db.close()


if __name__ == "__main__":
    main()