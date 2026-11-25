"""Catálogo explícito de unidades lineales y temperatura con conversión SI.

No interpreta unidades desconocidas como adimensionales. Las expresiones de
unidad se limitan a productos, cocientes y potencias enteras acotadas.
"""

import ast
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Unidad:
    dimensiones: tuple = (0, 0, 0, 0, 0, 0, 0)  # SI y magnitudes de catálogo (pH, turbidez)
    escala: float = 1
    desplazamiento: float = 0
    relativa: bool = False


CATALOGO: dict[str, Unidad] = {}


def registrar(nombres, dimensiones=(0, 0, 0, 0, 0), escala=1, desplazamiento=0, relativa=False):
    dimensiones = tuple(dimensiones) + (0,) * (7 - len(dimensiones))
    for nombre in nombres:
        CATALOGO[nombre] = Unidad(dimensiones, escala, desplazamiento, relativa)


registrar(["1", "adimensional", "sin unidad"])
registrar(["%"], escala=0.01)
registrar(["ppm"], escala=1e-6)
registrar(["ppb"], escala=1e-9)
for simbolo, escala in [("m", 1), ("cm", 0.01), ("mm", 0.001), ("km", 1000)]:
    registrar([simbolo], (1, 0, 0, 0, 0), escala)
for simbolo, escala in [("kg", 1), ("g", 0.001), ("mg", 1e-6), ("ug", 1e-9)]:
    registrar([simbolo], (0, 1, 0, 0, 0), escala)
for simbolo, escala in [("s", 1), ("min", 60), ("h", 3600), ("d", 86400)]:
    registrar([simbolo], (0, 0, 1, 0, 0), escala)
registrar(["K"], (0, 0, 0, 1, 0))
registrar(["°C", "C", "degC"], (0, 0, 0, 1, 0), 1, 273.15)
registrar(["°F", "F", "degF"], (0, 0, 0, 1, 0), 5 / 9, 255.3722222222222)
registrar(["delta_degC", "delta_K"], (0, 0, 0, 1, 0), relativa=True)
registrar(["delta_degF"], (0, 0, 0, 1, 0), 5 / 9, relativa=True)
registrar(["L", "l"], (3, 0, 0, 0, 0), 0.001)
registrar(["mL"], (3, 0, 0, 0, 0), 1e-6)
registrar(["Pa"], (-1, 1, -2, 0, 0))
registrar(["kPa"], (-1, 1, -2, 0, 0), 1000)
registrar(["hPa", "mbar"], (-1, 1, -2, 0, 0), 100)
registrar(["bar"], (-1, 1, -2, 0, 0), 100000)
registrar(["psi"], (-1, 1, -2, 0, 0), 6894.757293168)
registrar(["Hz"], (0, 0, -1, 0, 0))
registrar(["A"], (0, 0, 0, 0, 1))
registrar(["mA"], (0, 0, 0, 0, 1), 0.001)
registrar(["V"], (2, 1, -3, 0, -1))
registrar(["mV"], (2, 1, -3, 0, -1), 0.001)
registrar(["W"], (2, 1, -3, 0, 0))
registrar(["kW"], (2, 1, -3, 0, 0), 1000)
registrar(["J"], (2, 1, -2, 0, 0))
registrar(["Wh"], (2, 1, -2, 0, 0), 3600)
registrar(["kWh"], (2, 1, -2, 0, 0), 3.6e6)
registrar(["S"], (-2, -1, 3, 0, 2))
registrar(["mS"], (-2, -1, 3, 0, 2), 0.001)
registrar(["uS"], (-2, -1, 3, 0, 2), 1e-6)
registrar(["pH"], (0, 0, 0, 0, 0, 1, 0))
registrar(["NTU"], (0, 0, 0, 0, 0, 0, 1))


def combinar(a, b, signo=1):
    return tuple(x + signo * y for x, y in zip(a, b))


def unidad(texto: str) -> Unidad:
    texto = texto.strip().replace("µ", "u").replace("μ", "u")
    if texto in CATALOGO:
        return CATALOGO[texto]
    normalizado = texto.replace("^", "**").replace("²", "**2").replace("³", "**3")
    if len(normalizado) > 60:
        raise ValueError("La unidad de medida no está reconocida en el catálogo.")
    try:
        raiz = ast.parse(normalizado, mode="eval").body

        def interpretar(n):
            if isinstance(n, ast.Name) and n.id in CATALOGO:
                u = CATALOGO[n.id]
                if u.desplazamiento:
                    raise ValueError("Usa K en unidades compuestas de temperatura.")
                return u
            if isinstance(n, ast.Constant) and type(n.value) is int and n.value == 1:
                return Unidad()
            if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Mult, ast.Div)):
                a, b = interpretar(n.left), interpretar(n.right)
                signo = 1 if isinstance(n.op, ast.Mult) else -1
                return Unidad(
                    combinar(a.dimensiones, b.dimensiones, signo), a.escala * b.escala**signo
                )
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow):
                exponente = ast.literal_eval(n.right)
                if type(exponente) is not int or abs(exponente) > 6:
                    raise ValueError("La potencia de una unidad debe ser un entero entre -6 y 6.")
                a = interpretar(n.left)
                return Unidad(tuple(x * exponente for x in a.dimensiones), a.escala**exponente)
            raise ValueError("Unidad de medida no reconocida. Selecciona una unidad del catálogo.")

        return interpretar(raiz)
    except (SyntaxError, TypeError, RecursionError) as exc:
        raise ValueError("Unidad de medida no reconocida en el catálogo.") from exc


TEMPERATURA = (0, 0, 0, 1, 0, 0, 0)
SIN_DIMENSION = (0, 0, 0, 0, 0, 0, 0)


def dimensiones_formula(n, unidades):
    if isinstance(n, ast.Name):
        return unidades[n.id].dimensiones
    if isinstance(n, ast.Constant):
        return SIN_DIMENSION
    if isinstance(n, ast.UnaryOp):
        return dimensiones_formula(n.operand, unidades)
    a, b = dimensiones_formula(n.left, unidades), dimensiones_formula(n.right, unidades)
    if isinstance(n.op, (ast.Add, ast.Sub, ast.Mod)):
        if a != b:
            raise ValueError(
                "Unidades incompatibles: suma, resta y módulo requieren la misma magnitud."
            )
        return a
    if isinstance(n.op, ast.Pow):
        try:
            exponente = ast.literal_eval(n.right)
        except (ValueError, TypeError) as exc:
            raise ValueError("La potencia debe ser una constante entera entre -6 y 6.") from exc
        if type(exponente) is not int or abs(exponente) > 6:
            raise ValueError("La potencia debe ser una constante entera entre -6 y 6.")
        return tuple(x * exponente for x in a)
    return combinar(a, b, 1 if isinstance(n.op, ast.Mult) else -1)


def validar_unidades(formula, unidades, salida):
    destino = unidad(salida)
    if dimensiones_formula(ast.parse(formula, mode="eval").body, unidades) != destino.dimensiones:
        raise ValueError("La unidad de salida no es compatible con el resultado de la fórmula.")


def evaluar(formula, valores, unidades, salida, *, con_tipo=False):
    """Evaluador AST sin eval/exec. Opera en SI, controla offsets térmicos."""

    def visitar(n):
        if isinstance(n, ast.Name):
            u = unidades[n.id]
            return (
                valores[n.id] * u.escala + u.desplazamiento,
                u.dimensiones,
                1.0 if u.dimensiones == TEMPERATURA and not u.relativa else 0.0,
            )
        if isinstance(n, ast.Constant):
            return float(n.value), SIN_DIMENSION, 0.0
        if isinstance(n, ast.UnaryOp):
            v, d, peso = visitar(n.operand)
            signo = -1 if isinstance(n.op, ast.USub) else 1
            return signo * v, d, signo * peso
        a, da, pa = visitar(n.left)
        b, db, pb = visitar(n.right)
        d = dimensiones_formula(n, unidades)
        if isinstance(n.op, ast.Add):
            v, peso = a + b, pa + pb
        elif isinstance(n.op, ast.Sub):
            v, peso = a - b, pa - pb
        elif isinstance(n.op, ast.Mult):
            v, peso = a * b, pa * b if da == TEMPERATURA else pb * a
        elif isinstance(n.op, ast.Div):
            if b == 0:
                raise ValueError("División entre cero")
            v, peso = a / b, pa / b if da == TEMPERATURA and db == SIN_DIMENSION else 0
        elif isinstance(n.op, ast.Mod):
            if b == 0:
                raise ValueError("Módulo entre cero")
            if da == TEMPERATURA:
                raise ValueError("El módulo no admite temperaturas absolutas")
            v, peso = a % b, 0
        else:
            v, peso = a**b, pa if b == 1 else 0
        if not math.isfinite(v) or abs(v) > 1e100:
            raise ValueError("Resultado numérico fuera del rango admitido")
        return v, d, peso if d == TEMPERATURA else 0

    try:
        valor, dimensiones, peso = visitar(ast.parse(formula, mode="eval").body)
        destino = unidad(salida)
        relativa = dimensiones == TEMPERATURA and math.isclose(peso, 0, abs_tol=1e-10)
        if dimensiones == TEMPERATURA:
            if math.isclose(peso, 0, abs_tol=1e-10):
                offset = 0  # diferencia térmica
            elif math.isclose(peso, 1, abs_tol=1e-10):
                offset = destino.desplazamiento
            else:
                raise ValueError(
                    "La operación no representa una temperatura ni una diferencia térmica válida"
                )
        else:
            offset = destino.desplazamiento
        resultado = (valor - offset) / destino.escala
        if not math.isfinite(resultado) or abs(resultado) > 1e100:
            raise ValueError("Resultado numérico fuera del rango admitido")
        return (resultado, relativa) if con_tipo else resultado
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("Resultado numérico no válido") from exc
