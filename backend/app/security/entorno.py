"""Alcance operativo compartido por HTTP, listados y recursos individuales."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Cliente, Sede, Ubicacion, UsuarioCliente, UsuarioProyecto

ROLES_CENERIS = {"Administrador", "Técnico CENERIS", "Tecnico CENERIS"}
MODULOS_OPERATIVOS = {"Ubicaciones", "Dispositivos", "Ingesta", "Tableros", "Alarmas"}


def es_ceneris(usuario: dict) -> bool:
    return usuario.get("scope") == "global" and usuario.get("rol") in ROLES_CENERIS


def resolver_entorno(db: Session, usuario: dict, cliente_id=None, proyecto_id=None) -> dict:
    resultado = dict(usuario)
    resultado.update(cliente_id=cliente_id, proyecto_id=proyecto_id, rol_empresa=None)
    if usuario.get("scope") == "por_cliente":
        query = db.query(UsuarioCliente).join(Cliente, Cliente.id_clnt == UsuarioCliente.id_clnt).filter(
            UsuarioCliente.id_usr == int(usuario["sub"]), UsuarioCliente.estd == "Activo",
            Cliente.estd == "Activo",
        )
        if cliente_id is not None:
            query = query.filter(UsuarioCliente.id_clnt == cliente_id)
        miembro = query.order_by(UsuarioCliente.id_mmb).first()
        if miembro is None:
            raise HTTPException(403, "No tienes acceso a esta empresa")
        resultado.update(cliente_id=miembro.id_clnt, rol_empresa=miembro.rol_emp)
    elif cliente_id is not None and not es_ceneris(usuario):
        raise HTTPException(403, "No puedes cambiar de empresa")
    if resultado["cliente_id"] is not None:
        empresa = db.get(Cliente, resultado["cliente_id"])
        if empresa is None or empresa.estd != "Activo":
            raise HTTPException(403, "Empresa no disponible")
    if proyecto_id is not None:
        proyecto = db.get(Ubicacion, proyecto_id)
        if proyecto is None:
            raise HTTPException(403, "Proyecto no disponible")
        empresa_proyecto = db.get(Sede, proyecto.id_sd).id_clnt
        if resultado["cliente_id"] is not None and empresa_proyecto != resultado["cliente_id"]:
            raise HTTPException(403, "El proyecto no pertenece a la empresa seleccionada")
        if resultado.get("scope") == "por_cliente" and resultado["rol_empresa"] == "Lector":
            asignado = db.query(UsuarioProyecto).filter(
                UsuarioProyecto.id_mmb == miembro.id_mmb, UsuarioProyecto.id_ubccn == proyecto_id
            ).first()
            if asignado is None:
                raise HTTPException(403, "No tienes acceso a este proyecto")
        elif not es_ceneris(usuario) and resultado.get("scope") != "por_cliente":
            raise HTTPException(403, "No puedes cambiar de proyecto")
        resultado["cliente_id"] = empresa_proyecto
    resultado["_entorno_resuelto"] = True
    return resultado


def contexto(db: Session, usuario: dict) -> dict:
    # También soporta callers internos y tests que reciben la identidad sin headers.
    if usuario.get("_entorno_resuelto"):
        return usuario
    return resolver_entorno(db, usuario, usuario.get("cliente_id"), usuario.get("proyecto_id"))


def sedes_permitidas(db: Session, usuario: dict) -> list[int] | None:
    usuario = contexto(db, usuario)
    query = db.query(Sede.id_sd)
    if usuario.get("scope") == "por_sede":
        return [usuario["sede_id"]] if usuario.get("sede_id") else []
    if usuario.get("cliente_id") is not None:
        query = query.filter(Sede.id_clnt == usuario["cliente_id"])
    elif usuario.get("scope") == "global":
        return None
    else:
        return []
    if usuario.get("proyecto_id") is not None:
        query = query.filter(Sede.id_sd.in_(
            db.query(Ubicacion.id_sd).filter(Ubicacion.id_ubccn == usuario["proyecto_id"])
        ))
    if usuario.get("scope") == "por_cliente" and usuario["rol_empresa"] == "Lector":
        asignados = db.query(UsuarioProyecto.id_ubccn).join(
            UsuarioCliente, UsuarioCliente.id_mmb == UsuarioProyecto.id_mmb
        ).filter(UsuarioCliente.id_usr == int(usuario["sub"]),
                 UsuarioCliente.id_clnt == usuario["cliente_id"], UsuarioCliente.estd == "Activo")
        query = query.filter(Sede.id_sd.in_(
            db.query(Ubicacion.id_sd).filter(Ubicacion.id_ubccn.in_(asignados))
        ))
    return [fila[0] for fila in query.all()]


def filtrar_sedes(query, columna, db: Session, usuario: dict):
    ids = sedes_permitidas(db, usuario)
    return query if ids is None else query.filter(columna.in_(ids))


def filtrar_proyectos(query, columna, db: Session, usuario: dict):
    """Aislamiento preciso, incluso si dos proyectos comparten una sede."""
    usuario = contexto(db, usuario)
    visibles = filtrar_sedes(db.query(Ubicacion.id_ubccn), Ubicacion.id_sd, db, usuario)
    if usuario.get("proyecto_id") is not None:
        visibles = visibles.filter(Ubicacion.id_ubccn == usuario["proyecto_id"])
    if usuario.get("scope") == "por_cliente" and usuario["rol_empresa"] == "Lector":
        asignados = db.query(UsuarioProyecto.id_ubccn).join(
            UsuarioCliente, UsuarioCliente.id_mmb == UsuarioProyecto.id_mmb
        ).filter(UsuarioCliente.id_usr == int(usuario["sub"]),
                 UsuarioCliente.id_clnt == usuario["cliente_id"], UsuarioCliente.estd == "Activo")
        visibles = visibles.filter(Ubicacion.id_ubccn.in_(asignados))
    return query.filter(columna.in_(visibles))


def verificar_proyecto(db: Session, usuario: dict, proyecto_id: int) -> None:
    existe = filtrar_proyectos(db.query(Ubicacion.id_ubccn), Ubicacion.id_ubccn, db, usuario).filter(
        Ubicacion.id_ubccn == proyecto_id
    ).first()
    if existe is None:
        raise HTTPException(403, "No tienes acceso a este proyecto")


def permiso_del_entorno(db: Session, usuario: dict, modulo: str, accion: str) -> bool | None:
    if usuario.get("scope") == "por_cliente":
        rol = contexto(db, usuario)["rol_empresa"]
        if modulo not in MODULOS_OPERATIVOS:
            return False
        if rol in {"Administrador", "Tecnico"}:
            return True
        return modulo in {"Ubicaciones", "Dispositivos", "Tableros", "Alarmas"} and (
            accion == "lectura" or modulo == "Tableros"
        )
    if es_ceneris(usuario):
        return modulo in MODULOS_OPERATIVOS | {"Catalogo"} or (
            usuario["rol"] == "Administrador" and modulo in {"Usuarios", "Comercial"}
        )
    return None  # Compatibilidad con cuentas anteriores por sede/comerciales.


def puede_operar(db: Session, usuario: dict) -> bool:
    if usuario.get("scope") == "por_cliente":
        return contexto(db, usuario)["rol_empresa"] in {"Administrador", "Tecnico"}
    return usuario.get("rol") in ROLES_CENERIS
