"""
T41 - Configurar hashing con bcrypt
HT-04: "El sistema rechaza el almacenamiento de contraseñas en texto plano;
toda contraseña se guarda con hash bcrypt y salt."

bcrypt genera un salt distinto en cada llamada automáticamente (va incluido
dentro del propio hash resultante), así que nunca hay que guardarlo aparte.
"""

import secrets
import string

import bcrypt

# Factor de costo: más alto = más lento de calcular = más resistente a fuerza
# bruta, pero también más lento para el usuario real en cada login.
# 12 es el estándar recomendado en 2026 para un backend con tráfico normal.
BCRYPT_ROUNDS = 12

# HU04 CA: mínimo 8 caracteres, al menos 1 mayúscula y 1 número.
_LONGITUD_PASSWORD_TEMPORAL = 12
_MINUSCULAS = string.ascii_lowercase
_MAYUSCULAS = string.ascii_uppercase
_DIGITOS = string.digits
_SIMBOLOS = "!@#$%*?-_"


def generar_password_temporal() -> str:
    """HU04 CA2: credencial temporal generada al crear un usuario.

    Garantiza al menos 1 mayúscula y 1 número por construcción (no por
    reintento), sacando esos dos caracteres del pool y completando el resto
    con secrets.choice para no perder aleatoriedad criptográfica.
    """
    rng = secrets.SystemRandom()
    obligatorios = [rng.choice(_MAYUSCULAS), rng.choice(_DIGITOS)]
    pool = _MINUSCULAS + _MAYUSCULAS + _DIGITOS + _SIMBOLOS
    resto = [rng.choice(pool) for _ in range(_LONGITUD_PASSWORD_TEMPORAL - len(obligatorios))]
    caracteres = obligatorios + resto
    rng.shuffle(caracteres)
    return "".join(caracteres)


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
