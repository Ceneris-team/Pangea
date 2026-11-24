"""Referencias de definiciones calculadas. Nunca evalúa las expresiones."""

import ast
import math
import re

from sqlalchemy.orm import Session

from app.models import Dispositivo, MapeoColumna, MapeoFormato, Parametro, Ubicacion


def origenes_por_sede(db: Session, sedes: list[int]) -> dict[int, list[Parametro]]:
    filas = (
        db.query(Ubicacion.id_sd, Parametro)
        .join(Dispositivo, Dispositivo.id_ubccn == Ubicacion.id_ubccn)
        .join(MapeoFormato, MapeoFormato.id_dspstv == Dispositivo.id_dspstv)
        .join(MapeoColumna, MapeoColumna.id_mp == MapeoFormato.id_mp)
        .join(Parametro, Parametro.id_prmtr == MapeoColumna.id_prmtr)
        .filter(
            Ubicacion.id_sd.in_(sedes),
            MapeoFormato.estd == "Activo",
            Parametro.tipo_dato == "numerico",
            Parametro.estd != "Fusionado",
        )
        .distinct()
        .order_by(Parametro.nmbr, Parametro.id_prmtr)
        .all()
    )
    resultado = {sede: [] for sede in sedes}
    for sede, parametro in filas:
        resultado[sede].append(parametro)
    return resultado


def describir_formula(formula: str, origenes: list[Parametro]) -> dict:
    por_variable = {f"p_{p.id_prmtr}": p for p in origenes}
    # Las fórmulas anteriores no tienen una relación formal con el catálogo.
    # Se muestran sus variables sin inventar asociaciones por similitud de nombre.
    try:
        arbol = ast.parse(formula, mode="eval")
        nombres = sorted(
            (n for n in ast.walk(arbol) if isinstance(n, ast.Name)),
            key=lambda n: (n.lineno, n.col_offset),
        )
        variables = list(dict.fromkeys(n.id for n in nombres))
    except (SyntaxError, ValueError, RecursionError):
        variables = list(dict.fromkeys(re.findall(r"\bp_\d+\b", formula)))
    referencias = []
    for variable in variables:
        p = por_variable.get(variable)
        referencias.append(
            {
                "variable": variable,
                "nombre": p.nmbr if p else None,
                "unidad": p.undd if p else None,
                "estado": p.estd if p else None,
                "disponible": p is not None,
            }
        )
    legible = re.sub(
        r"\bp_\d+\b",
        lambda m: f"[{por_variable[m[0]].nmbr}]" if m[0] in por_variable else m[0],
        formula,
    )
    return {"frml": legible, "referencias": referencias}


def preparar_formula(formula: str, origenes: list[Parametro]) -> str:
    activos = [p for p in origenes if p.estd == "Activo"]
    tokens = {f"[{p.nmbr}]": f"p_{p.id_prmtr}" for p in activos}
    if tokens:
        patron = "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True))
        formula = re.sub(patron, lambda m: tokens[m[0]], formula)
    formula = formula.strip()
    if not formula or len(formula) > 500:
        raise ValueError("La fórmula es obligatoria y admite hasta 500 caracteres.")
    try:
        arbol = ast.parse(formula, mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ValueError(
            "Revisa la fórmula: usa parámetros de origen, números y operaciones aritméticas."
        ) from exc
    permitidos = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.UAdd,
        ast.USub,
    )
    nodos = list(ast.walk(arbol))
    variables = {n.id for n in nodos if isinstance(n, ast.Name)}
    if not variables or not variables <= set(tokens.values()):
        raise ValueError(
            "La fórmula debe utilizar parámetros numéricos activos disponibles en el ámbito elegido."
        )
    if len(nodos) > 150 or any(not isinstance(n, permitidos) for n in nodos):
        raise ValueError(
            "La fórmula admite números, parámetros, paréntesis y las operaciones +, -, *, /, ** y %."
        )
    if any(
        isinstance(n, ast.Constant)
        and (
            type(n.value) not in (int, float)
            or (isinstance(n.value, float) and not math.isfinite(n.value))
        )
        for n in nodos
    ):
        raise ValueError("La fórmula solo admite constantes numéricas finitas.")
    return formula
