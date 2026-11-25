"""Referencias y validación de definiciones calculadas."""

import ast
import math
import re

from sqlalchemy.orm import Session

from app.models import (
    DependenciaCalculo,
    Dispositivo,
    MapeoColumna,
    MapeoFormato,
    Parametro,
    ParametroCalculado,
    Ubicacion,
)
from app.services.unidades_calculo import unidad, validar_unidades


def variable_origen(p):
    return f"c_{p.id_prm_clc}" if isinstance(p, ParametroCalculado) else f"p_{p.id_prmtr}"


def todos_origenes(db, sedes):
    resultado = origenes_por_sede(db, sedes)
    for p in (
        db.query(ParametroCalculado)
        .filter(ParametroCalculado.id_sd.in_(sedes), ParametroCalculado.validada.is_(True))
        .all()
    ):
        resultado[p.id_sd].append(p)
    return resultado


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
    por_variable = {variable_origen(p): p for p in origenes}
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
        r"\b[pc]_\d+\b",
        lambda m: f"[{por_variable[m[0]].nmbr}]" if m[0] in por_variable else m[0],
        formula,
    )
    return {"frml": legible, "referencias": referencias}


def preparar_formula(formula: str, origenes: list[Parametro]) -> str:
    activos = [p for p in origenes if p.estd == "Activo"]
    tokens = {f"[{p.nmbr}]": variable_origen(p) for p in activos}
    if len(tokens) != len(activos):
        raise ValueError(
            "Hay nombres ambiguos entre los parámetros de origen; corrige los nombres antes de crear la fórmula."
        )
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


def validar_definicion(db, sede_id, formula, salida, propio_id=None):
    origenes = todos_origenes(db, [sede_id])[sede_id]
    if propio_id is not None:
        origenes = [
            p
            for p in origenes
            if not isinstance(p, ParametroCalculado) or p.id_prm_clc != propio_id
        ]
    normalizada = preparar_formula(formula, origenes)
    variables = {
        n.id for n in ast.walk(ast.parse(normalizada, mode="eval")) if isinstance(n, ast.Name)
    }
    seleccionados = {variable_origen(p): p for p in origenes if variable_origen(p) in variables}
    unidades = {v: unidad(p.undd) for v, p in seleccionados.items()}
    validar_unidades(normalizada, unidades, salida)
    definiciones = {p.id_prm_clc: p for p in origenes if isinstance(p, ParametroCalculado)}
    relaciones = {}
    for d in (
        db.query(DependenciaCalculo).filter(DependenciaCalculo.id_prm_clc.in_(definiciones)).all()
    ):
        if d.id_origen_calculado:
            relaciones.setdefault(d.id_prm_clc, []).append(d.id_origen_calculado)
    visitados, en_camino = set(), set()

    def recorrer(id_):
        if id_ in en_camino or id_ == propio_id:
            raise ValueError("La fórmula contiene una dependencia circular.")
        if id_ in visitados:
            return
        p = definiciones.get(id_)
        if p is None or p.estd != "Activo":
            raise ValueError("Una dependencia calculada no está activa o disponible en el ámbito.")
        en_camino.add(id_)
        for hijo in relaciones.get(id_, []):
            recorrer(hijo)
        en_camino.remove(id_)
        visitados.add(id_)

    for p in seleccionados.values():
        if isinstance(p, ParametroCalculado):
            recorrer(p.id_prm_clc)
    return normalizada, seleccionados
