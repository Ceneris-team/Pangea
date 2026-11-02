"""Resumen de autorización para invalidar vistas abiertas sin guardar permisos en el JWT."""

import hashlib
import json

from sqlalchemy.orm import Session

from app.models import Cliente, PermisoUsuarioSede, Sede, Ubicacion, UsuarioCliente, UsuarioProyecto
from app.security.ubicaciones_permitidas import ubicaciones_permitidas


def estado_acceso(db: Session, usuario: dict) -> dict:
    id_usr = int(usuario["sub"])
    membresias = db.query(UsuarioCliente).filter(UsuarioCliente.id_usr == id_usr).order_by(
        UsuarioCliente.id_mmb,
    ).all()
    empresas = []
    proyectos_estado = []
    for miembro in membresias:
        empresa = db.get(Cliente, miembro.id_clnt)
        if miembro.estd != "Activo" or empresa.estd != "Activo":
            continue
        query = db.query(Ubicacion.id_ubccn, Ubicacion.estd).join(
            Sede, Sede.id_sd == Ubicacion.id_sd,
        ).filter(Sede.id_clnt == miembro.id_clnt)
        if miembro.rol_emp == "Lector":
            query = query.join(UsuarioProyecto, UsuarioProyecto.id_ubccn == Ubicacion.id_ubccn).filter(
                UsuarioProyecto.id_mmb == miembro.id_mmb,
            )
        proyectos = query.order_by(Ubicacion.id_ubccn).all()
        empresas.append({"id_clnt": empresa.id_clnt, "rol": miembro.rol_emp,
                         "proyecto_ids": [id_ for id_, _ in proyectos]})
        proyectos_estado.extend([list(row) for row in proyectos])
    legacy_ids = ubicaciones_permitidas(db, usuario) if usuario.get("scope") != "por_cliente" else []
    permisos = db.query(PermisoUsuarioSede.id_sd, PermisoUsuarioSede.mdl, PermisoUsuarioSede.nvl).filter(
        PermisoUsuarioSede.id_usr == id_usr,
    ).order_by(PermisoUsuarioSede.id_prms).all()
    contenido = {"empresas": empresas, "proyecto_ids": sorted(legacy_ids),
                 "proyectos_estado": proyectos_estado, "permisos": [list(row) for row in permisos],
                 "rol": usuario["rol"], "scope": usuario["scope"]}
    version = hashlib.sha256(json.dumps(contenido, sort_keys=True).encode()).hexdigest()
    return {"version": version, "empresas": empresas, "proyecto_ids": legacy_ids}
