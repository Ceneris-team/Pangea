"""
HU 02 - Gestionar contraseña

Detalle de conversación: "La nueva contraseña debe tener mínimo 8
caracteres, al menos 1 letra mayúscula y 1 número."
"""
import re

MSG_POLITICA_INVALIDA = (
    "La contraseña debe tener mínimo 8 caracteres, al menos 1 letra mayúscula y 1 número."
)


def es_password_valido(password: str) -> bool:
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[0-9]", password):
        return False
    return True
