"""
T41 - Configurar hashing con bcrypt
HT-04: "El sistema rechaza el almacenamiento de contraseñas en texto plano;
toda contraseña se guarda con hash bcrypt y salt."

bcrypt genera un salt distinto en cada llamada automáticamente (va incluido
dentro del propio hash resultante), así que nunca hay que guardarlo aparte.
"""
import bcrypt

# Factor de costo: más alto = más lento de calcular = más resistente a fuerza
# bruta, pero también más lento para el usuario real en cada login.
# 12 es el estándar recomendado en 2026 para un backend con tráfico normal.
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Genera el hash bcrypt de una contraseña en texto plano.
    Este es el único valor que se debe guardar en usr.cntrsn_hsh.
    """
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Compara una contraseña en texto plano contra el hash guardado.
    Se usa en el login (HU 01) y al validar la contraseña actual antes
    de cambiarla (HU 02, tarea T06).
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # hash con formato corrupto o vacío -> tratar como no válido, no reventar
        return False
