"""Espacio empresarial: proyectos y usuarios aislados por cliente."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Cliente,
    Dispositivo,
    LogAuditoria,
    PermisoUbicacion,
    PermisoUsuarioSede,
    Rol,
    Sede,
    Ubicacion,
    Usuario,
    UsuarioCliente,
    UsuarioProyecto,
)
from app.security.dependencies import get_current_user
from app.security.entorno import es_ceneris
from app.security.hashing import generar_password_temporal, hash_password
from app.services.limites_plan import comprobar_cupo, resumen_cliente, suscripcion_vigente

router = APIRouter(prefix="/empresas", tags=["Empresas y proyectos"])


class EmpresaCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    ruc: str = Field(pattern=r"^\d{11}$")
    correo_contacto: EmailStr


class MiembroCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    correo: EmailStr
    rol: str
    proyecto_ids: list[int] = Field(default_factory=list)


class MiembroActualizar(BaseModel):
    rol: str
    estado: str
    proyecto_ids: list[int] = Field(default_factory=list)


def _acceso(db: Session, actor: dict, cliente_id: int) -> UsuarioCliente | None:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.estd != "Activo":
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    if es_ceneris(actor):
        return None
    if actor["rol"] != "Usuario Empresa" or actor["scope"] != "por_cliente":
        raise HTTPException(status_code=403, detail="No tienes acceso a esta empresa")
    membresia = db.query(UsuarioCliente).filter(
        UsuarioCliente.id_usr == int(actor["sub"]),
        UsuarioCliente.id_clnt == cliente_id,
        UsuarioCliente.estd == "Activo",
    ).first()
    if membresia is None:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta empresa")
    return membresia


def _administrador(db: Session, actor: dict, cliente_id: int) -> UsuarioCliente | None:
    membresia = _acceso(db, actor, cliente_id)
    if (membresia is None and actor["rol"] != "Administrador") or (membresia is not None and membresia.rol_emp != "Administrador"):
        raise HTTPException(status_code=403, detail="Solo un administrador puede gestionar esta empresa")
    return membresia


def _proyectos_permitidos(db: Session, membresia: UsuarioCliente | None) -> set[int] | None:
    if membresia is None or membresia.rol_emp in {"Administrador", "Tecnico"}:
        return None
    return {
        id_pryct for (id_pryct,) in db.query(UsuarioProyecto.id_ubccn)
        .filter(UsuarioProyecto.id_mmb == membresia.id_mmb).all()
    }


def _proyecto(db: Session, cliente_id: int, proyecto_id: int, membresia: UsuarioCliente | None) -> Ubicacion:
    proyecto = db.query(Ubicacion).join(Sede, Sede.id_sd == Ubicacion.id_sd).filter(
        Ubicacion.id_ubccn == proyecto_id, Sede.id_clnt == cliente_id
    ).first()
    if proyecto is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    permitidos = _proyectos_permitidos(db, membresia)
    if permitidos is not None and proyecto_id not in permitidos:
        raise HTTPException(status_code=403, detail="No tienes acceso a este proyecto")
    return proyecto


def _validar_asignaciones(db: Session, cliente_id: int, rol: str, ids: list[int]) -> set[int]:
    if rol not in {"Administrador", "Tecnico", "Lector"}:
        raise HTTPException(status_code=422, detail="Rol empresarial no válido")
    if rol in {"Administrador", "Tecnico"}:
        return set()  # Siempre ve todos los proyectos de su empresa.
    solicitados = set(ids)
    if not solicitados:
        raise HTTPException(status_code=422, detail="Asigna al menos un proyecto al usuario")
    existentes = {
        id_pryct for (id_pryct,) in db.query(Ubicacion.id_ubccn).join(Sede, Sede.id_sd == Ubicacion.id_sd).filter(
            Sede.id_clnt == cliente_id,
            Ubicacion.estd == "Activa",
            Ubicacion.id_ubccn.in_(solicitados),
        ).all()
    }
    if existentes != solicitados:
        raise HTTPException(status_code=422, detail="Hay proyectos que no pertenecen a esta empresa")
    return solicitados


def _auditar(db: Session, actor: dict, accion: str, entidad: str, datos: dict) -> None:
    db.add(LogAuditoria(
        id_usr=int(actor["sub"]), id_sd=None, accn=accion,
        entdd=entidad, vlrs_nvs=datos,
    ))


def _miembro_dict(db: Session, miembro: UsuarioCliente) -> dict:
    usuario = db.get(Usuario, miembro.id_usr)
    return {
        "id_mmb": miembro.id_mmb,
        "id_usr": usuario.id_usr,
        "nombre": usuario.nmbr_cmplt,
        "correo": usuario.crr,
        "rol": miembro.rol_emp,
        "estado": miembro.estd,
        "proyecto_ids": [id_pryct for (id_pryct,) in db.query(UsuarioProyecto.id_ubccn)
                         .filter(UsuarioProyecto.id_mmb == miembro.id_mmb).all()],
        "legado": False,
    }


def _resumen_operativo(db, cliente):
    resumen = resumen_cliente(db, cliente)
    # Los lectores y técnicos necesitan cupos y plan, no precios negociados.
    resumen.pop("condiciones", None)
    resumen.pop("programada", None)
    return resumen


@router.get("")
def listar_empresas(
    db: Session = Depends(get_db), actor: dict = Depends(get_current_user),
):
    if es_ceneris(actor):
        clientes = db.query(Cliente).filter(Cliente.estd == "Activo").order_by(Cliente.rzn_scl).all()
        membresias = {}
    elif actor["rol"] == "Usuario Empresa" and actor["scope"] == "por_cliente":
        filas = db.query(Cliente, UsuarioCliente).join(
            UsuarioCliente, UsuarioCliente.id_clnt == Cliente.id_clnt
        ).filter(
            UsuarioCliente.id_usr == int(actor["sub"]),
            UsuarioCliente.estd == "Activo", Cliente.estd == "Activo",
        ).order_by(Cliente.rzn_scl).all()
        clientes = [cliente for cliente, _ in filas]
        membresias = {cliente.id_clnt: m.rol_emp for cliente, m in filas}
    else:
        raise HTTPException(status_code=403, detail="No tienes acceso a empresas")
    return [{
        **_resumen_operativo(db, cliente),
        "rol_empresa": membresias.get(cliente.id_clnt, "CENERIS"),
        "proyectos_total": db.query(Ubicacion).join(Sede, Sede.id_sd == Ubicacion.id_sd).filter(Sede.id_clnt == cliente.id_clnt).count(),
    } for cliente in clientes]


@router.post("", status_code=201)
def crear_empresa(
    body: EmpresaCrear, db: Session = Depends(get_db), actor: dict = Depends(get_current_user),
):
    if actor["rol"] != "Administrador" or actor["scope"] != "global":
        raise HTTPException(status_code=403, detail="Solo CENERIS puede registrar empresas")
    nombre = body.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=422, detail="Indica la razón social")
    cliente = Cliente(rzn_scl=nombre, rc=body.ruc, crr_cntct=body.correo_contacto.lower())
    db.add(cliente)
    try:
        db.flush()
        _auditar(db, actor, "crear", "Empresa", {"cliente_id": cliente.id_clnt})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe una empresa con ese RUC") from None
    return {"id_clnt": cliente.id_clnt, "nombre": cliente.rzn_scl}


@router.get("/{cliente_id}/proyectos")
def listar_proyectos(
    cliente_id: int, db: Session = Depends(get_db), actor: dict = Depends(get_current_user),
):
    membresia = _acceso(db, actor, cliente_id)
    permitidos = _proyectos_permitidos(db, membresia)
    query = db.query(Ubicacion).join(Sede, Ubicacion.id_sd == Sede.id_sd).filter(Sede.id_clnt == cliente_id)
    if permitidos is not None:
        query = query.filter(Ubicacion.id_ubccn.in_(permitidos))
    conteos = dict(db.query(Dispositivo.id_ubccn, func.count(Dispositivo.id_dspstv))
                   .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
                   .join(Sede, Sede.id_sd == Ubicacion.id_sd)
                   .filter(Sede.id_clnt == cliente_id).group_by(Dispositivo.id_ubccn).all())
    return [{
        "id_ubccn": p.id_ubccn, "nombre": p.nmbr, "descripcion": p.dscrpcn,
        "estado": p.estd, "dispositivos_total": conteos.get(p.id_ubccn, 0),
    } for p in query.order_by(Ubicacion.nmbr).all()]


@router.get("/{cliente_id}/proyectos/{proyecto_id}/recursos")
def recursos_proyecto(
    cliente_id: int, proyecto_id: int,
    db: Session = Depends(get_db), actor: dict = Depends(get_current_user),
):
    miembro = _acceso(db, actor, cliente_id)
    proyecto = _proyecto(db, cliente_id, proyecto_id, miembro)
    dispositivos = db.query(Dispositivo).filter(Dispositivo.id_ubccn == proyecto.id_ubccn).order_by(Dispositivo.nmbr).all()
    return {"id_ubccn": proyecto.id_ubccn, "proyecto": proyecto.nmbr, "dispositivos": [
        {"id_dspstv": d.id_dspstv, "nombre": d.nmbr, "estado": d.estd} for d in dispositivos
    ]}


@router.get("/{cliente_id}/usuarios")
def listar_usuarios_empresa(
    cliente_id: int, db: Session = Depends(get_db), actor: dict = Depends(get_current_user),
):
    if es_ceneris(actor):
        _acceso(db, actor, cliente_id)
    else:
        _administrador(db, actor, cliente_id)
    miembros = db.query(UsuarioCliente).filter(UsuarioCliente.id_clnt == cliente_id).order_by(UsuarioCliente.id_mmb).all()
    items = [_miembro_dict(db, miembro) for miembro in miembros]
    ids_miembros = {miembro.id_usr for miembro in miembros}
    # Durante la transición, las cuentas Cliente Final existentes siguen
    # vinculadas por permisos históricos. Se muestran para que CENERIS y el
    # nuevo administrador conozcan el equipo completo, pero se editan en el
    # módulo anterior hasta migrar su identidad a una membresía explícita.
    por_sede = db.query(PermisoUsuarioSede.id_usr, Ubicacion.id_ubccn).join(
        Sede, Sede.id_sd == PermisoUsuarioSede.id_sd
    ).outerjoin(Ubicacion, Ubicacion.id_sd == Sede.id_sd).filter(Sede.id_clnt == cliente_id).distinct().all()
    por_ubicacion = db.query(PermisoUbicacion.id_usr, Ubicacion.id_ubccn).join(
        Ubicacion, Ubicacion.id_ubccn == PermisoUbicacion.id_ubccn
    ).join(Sede, Sede.id_sd == Ubicacion.id_sd).filter(Sede.id_clnt == cliente_id).distinct().all()
    proyectos_legados: dict[int, set[int]] = {}
    for id_usr, id_pryct in (*por_sede, *por_ubicacion):
        if id_usr not in ids_miembros:
            if id_pryct is not None:
                proyectos_legados.setdefault(id_usr, set()).add(id_pryct)
            else:
                proyectos_legados.setdefault(id_usr, set())
    if proyectos_legados:
        for usuario in db.query(Usuario).join(Rol, Rol.id_rl == Usuario.id_rl).filter(
            Usuario.id_usr.in_(proyectos_legados), Rol.nmbr == "Cliente Final"
        ).order_by(Usuario.nmbr_cmplt).all():
            items.append({
                "id_mmb": None, "id_usr": usuario.id_usr,
                "nombre": usuario.nmbr_cmplt, "correo": usuario.crr,
                "rol": "Cliente Final", "estado": usuario.estd,
                "proyecto_ids": sorted(proyectos_legados[usuario.id_usr]),
                "legado": True,
            })
    return items


@router.post("/{cliente_id}/usuarios", status_code=201)
def crear_usuario_empresa(
    cliente_id: int, body: MiembroCrear,
    db: Session = Depends(get_db), actor: dict = Depends(get_current_user),
):
    _administrador(db, actor, cliente_id)
    proyecto_ids = _validar_asignaciones(db, cliente_id, body.rol, body.proyecto_ids)
    if suscripcion_vigente(db, cliente_id) is None:
        raise HTTPException(status_code=409, detail="La empresa necesita una suscripción vigente")
    comprobar_cupo(db, cliente_id, "usuarios")
    correo = body.correo.lower()
    usuario = db.query(Usuario).filter(func.lower(Usuario.crr) == correo).first()
    password_temporal = None
    if usuario is None:
        rol_usuario = db.query(Rol).filter(Rol.nmbr == "Usuario Empresa").one()
        password_temporal = generar_password_temporal()
        usuario = Usuario(
            id_rl=rol_usuario.id_rl, scp="por_cliente", nmbr_cmplt=body.nombre.strip(),
            crr=correo, cntrsn_hsh=hash_password(password_temporal),
            dbe_cmbr_pswrd=True, estd="Activo",
        )
        db.add(usuario)
        db.flush()
    elif usuario.scp != "por_cliente" or usuario.rol.nmbr != "Usuario Empresa" or usuario.estd != "Activo":
        raise HTTPException(status_code=409, detail="Ese correo pertenece a una cuenta de otro tipo o inactiva")
    if db.query(UsuarioCliente).filter(
        UsuarioCliente.id_usr == usuario.id_usr, UsuarioCliente.id_clnt == cliente_id
    ).first():
        raise HTTPException(status_code=409, detail="Esta persona ya pertenece a la empresa")
    miembro = UsuarioCliente(id_usr=usuario.id_usr, id_clnt=cliente_id, rol_emp=body.rol, estd="Activo")
    db.add(miembro)
    db.flush()
    for id_pryct in proyecto_ids:
        db.add(UsuarioProyecto(id_mmb=miembro.id_mmb, id_ubccn=id_pryct))
    _auditar(db, actor, "crear", "MiembroEmpresa", {
        "cliente_id": cliente_id, "miembro_id": miembro.id_mmb,
        "rol": body.rol, "proyecto_ids": sorted(proyecto_ids),
    })
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo crear la membresía") from None
    return {"miembro": _miembro_dict(db, miembro), "contrasena_temporal": password_temporal}


@router.patch("/{cliente_id}/usuarios/{miembro_id}")
def actualizar_usuario_empresa(
    cliente_id: int, miembro_id: int, body: MiembroActualizar,
    db: Session = Depends(get_db), actor: dict = Depends(get_current_user),
):
    _administrador(db, actor, cliente_id)
    # Serializa cambios de administradores y altas en la misma empresa.
    db.query(Cliente).filter(Cliente.id_clnt == cliente_id).with_for_update().one()
    if body.estado not in {"Activo", "Inactivo"}:
        raise HTTPException(status_code=422, detail="Estado no válido")
    proyecto_ids = _validar_asignaciones(db, cliente_id, body.rol, body.proyecto_ids)
    miembro = db.query(UsuarioCliente).filter(
        UsuarioCliente.id_mmb == miembro_id, UsuarioCliente.id_clnt == cliente_id
    ).with_for_update().first()
    if miembro is None:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")
    if miembro.rol_emp == "Administrador" and miembro.estd == "Activo" and (
        body.rol != "Administrador" or body.estado != "Activo"
    ):
        otros = db.query(UsuarioCliente).filter(
            UsuarioCliente.id_clnt == cliente_id,
            UsuarioCliente.id_mmb != miembro.id_mmb,
            UsuarioCliente.rol_emp == "Administrador",
            UsuarioCliente.estd == "Activo",
        ).count()
        if otros == 0:
            raise HTTPException(status_code=409, detail="No puedes dejar la empresa sin administrador")
    if miembro.estd == "Inactivo" and body.estado == "Activo":
        if suscripcion_vigente(db, cliente_id) is None:
            raise HTTPException(status_code=409, detail="La empresa necesita una suscripción vigente")
        comprobar_cupo(db, cliente_id, "usuarios")
    anterior = {"rol": miembro.rol_emp, "estado": miembro.estd}
    miembro.rol_emp = body.rol
    miembro.estd = body.estado
    db.query(UsuarioProyecto).filter(UsuarioProyecto.id_mmb == miembro.id_mmb).delete()
    for id_pryct in proyecto_ids:
        db.add(UsuarioProyecto(id_mmb=miembro.id_mmb, id_ubccn=id_pryct))
    _auditar(db, actor, "actualizar", "MiembroEmpresa", {
        "cliente_id": cliente_id, "miembro_id": miembro_id, "anterior": anterior,
        "rol": body.rol, "estado": body.estado, "proyecto_ids": sorted(proyecto_ids),
    })
    db.commit()
    return {"miembro": _miembro_dict(db, miembro)}
