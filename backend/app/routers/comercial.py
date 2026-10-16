"""Gestión de planes, límites y asignación de suscripciones."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Cliente,
    ComplementoComercial,
    FuncionalidadComercial,
    LimitePlan,
    LogAuditoria,
    PermisoUbicacion,
    PlanSuscripcion,
    Sede,
    Suscripcion,
    Ubicacion,
    Usuario,
)
from app.security.dependencies import get_current_user
from app.security.permisos import EDICION, LECTURA, require_permiso
from app.services.contratos import (
    aplicar_programadas,
    auditar,
    condiciones_de,
    contrato_dict,
    preparar_condiciones,
    registrar_contrato,
    validar_funcionalidades,
    validar_operacion,
)
from app.services.limites_plan import fecha_comercial, resumen_cliente

router = APIRouter(prefix="/comercial", tags=["Comercial"])


class PlanCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=300)
    precio_mensual: Decimal = Field(ge=0, decimal_places=2, max_digits=12)
    moneda: Literal["PEN", "USD"] = "PEN"

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El nombre es obligatorio")
        return valor


class LimitesGuardar(BaseModel):
    ubicaciones: int = Field(ge=0)
    dispositivos: int = Field(ge=0)
    usuarios: int = Field(ge=0)


class SuscripcionAsignar(BaseModel):
    plan_id: int
    fecha_inicio: date
    fecha_vencimiento: date
    operacion: Literal["Crear", "Cambiar", "Renovar"] | None = None
    precio_acordado: Decimal | None = Field(default=None, ge=0, decimal_places=2, max_digits=12)
    moneda: Literal["PEN", "USD"] | None = None
    periodicidad: Literal["Mensual", "Trimestral", "Anual"] = "Mensual"
    referencia: str | None = Field(default=None, max_length=200)
    motivo: str = Field(default="Asignación comercial", min_length=3, max_length=300)
    dias_gracia: int = Field(default=0, ge=0, le=30)
    es_prueba: bool = False
    limites_acordados: LimitesGuardar | None = None
    complementos: list["ComplementoSeleccionado"] = Field(default_factory=list)
    suscripcion_actual_id: int | None = None
    revision_plan: int | None = None
    clave_idempotencia: str | None = Field(default=None, min_length=16, max_length=64)

    @field_validator("motivo")
    @classmethod
    def motivo_no_vacio(cls, valor):
        if len(valor.strip()) < 3:
            raise ValueError("Indica un motivo de al menos tres caracteres")
        return valor.strip()


class ComplementoSeleccionado(BaseModel):
    id: int
    cantidad: int = Field(default=1, ge=1, le=10000)


class FuncionalidadesGuardar(BaseModel):
    funcionalidades: list[str]


class FuncionalidadCrear(BaseModel):
    codigo: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    nombre: str = Field(min_length=1, max_length=150)
    disponible: bool = False

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, valor):
        return PlanCrear.nombre_no_vacio(valor)


class ComplementoCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    tipo: Literal["Recurrente", "Servicio"]
    precio: Decimal = Field(ge=0, decimal_places=2, max_digits=12)
    moneda: Literal["PEN", "USD"] = "PEN"
    cupos: LimitesGuardar = Field(default_factory=lambda: LimitesGuardar(ubicaciones=0, dispositivos=0, usuarios=0))
    funcionalidades: list[str] = Field(default_factory=list)

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, valor):
        return PlanCrear.nombre_no_vacio(valor)


class EstadoCambiar(BaseModel):
    accion: Literal["Suspender", "Reactivar", "Cancelar"]
    motivo: str = Field(min_length=3, max_length=300)

    @field_validator("motivo")
    @classmethod
    def motivo_no_vacio(cls, valor):
        return SuscripcionAsignar.motivo_no_vacio(valor)


SuscripcionAsignar.model_rebuild()



def _solo_comercial(usuario: dict) -> None:
    if usuario.get("scope") != "global" or usuario.get("rol") not in {"Administrador", "Administrador Comercial"}:
        raise HTTPException(status_code=403, detail="Solo la administración CENERIS puede gestionar planes")


def _plan_dict(plan: PlanSuscripcion, limites: LimitePlan | None) -> dict:
    return {
        "id_pln": plan.id_pln,
        "nombre": plan.nmbr,
        "descripcion": plan.dscrpcn,
        "precio_mensual": str(plan.prc_mnsl),
        "estado": plan.estd,
        "moneda": plan.moneda, "revision": plan.revision,
        "funcionalidades": plan.funcionalidades,
        "limites": {
            "ubicaciones": limites.mx_ubccns,
            "dispositivos": limites.mx_dspstvs,
            "usuarios": limites.mx_usrs,
        }
        if limites
        else None,
    }


@router.get("/planes")
def listar_planes(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Comercial", LECTURA)),
):
    planes = db.query(PlanSuscripcion).order_by(PlanSuscripcion.prc_mnsl, PlanSuscripcion.id_pln).all()
    limites = {fila.id_pln: fila for fila in db.query(LimitePlan).all()}
    return [_plan_dict(plan, limites.get(plan.id_pln)) for plan in planes]


@router.post("/planes", status_code=201)
def crear_plan(
    body: PlanCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Comercial", EDICION)),
):
    _solo_comercial(usuario)
    if db.query(PlanSuscripcion).filter(func.lower(PlanSuscripcion.nmbr) == body.nombre.lower()).first():
        raise HTTPException(status_code=409, detail="Ya existe un plan con ese nombre")
    plan = PlanSuscripcion(nmbr=body.nombre, dscrpcn=body.descripcion, prc_mnsl=body.precio_mensual,
                           moneda=body.moneda, funcionalidades=["tableros"])
    db.add(plan)
    try:
        db.flush()
        auditar(db, usuario, "crear_plan", "PlanSuscripcion", despues={"plan_id": plan.id_pln, "nombre": plan.nmbr})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un plan con ese nombre") from None
    db.refresh(plan)
    return {"mensaje": "Plan de suscripción creado correctamente", "plan": _plan_dict(plan, None)}


@router.put("/planes/{id_pln}/limites")
def guardar_limites(
    id_pln: int,
    body: LimitesGuardar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Comercial", EDICION)),
):
    _solo_comercial(usuario)
    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id_pln == id_pln).with_for_update().first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    limites = db.query(LimitePlan).filter(LimitePlan.id_pln == id_pln).first()
    nuevo = limites is None
    antes = _plan_dict(plan, limites)
    if nuevo:
        limites = LimitePlan(id_pln=id_pln, mx_sds=0)
        db.add(limites)
    limites.mx_ubccns = body.ubicaciones
    limites.mx_dspstvs = body.dispositivos
    limites.mx_usrs = body.usuarios
    plan.revision += 1
    auditar(db, usuario, "editar_limites_plan", "PlanSuscripcion", antes, _plan_dict(plan, limites))
    db.commit()
    return {
        "mensaje": "Niveles y límites configurados correctamente" if nuevo else "Límites actualizados correctamente",
        "plan": _plan_dict(plan, limites),
    }


@router.get("/clientes")
def listar_clientes(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Comercial", LECTURA)),
):
    return [resumen_cliente(db, cliente) for cliente in db.query(Cliente).order_by(Cliente.rzn_scl).all()]


@router.get("/mi-plan")
def mi_plan(
    db: Session = Depends(get_db),
    usuario: dict = Depends(get_current_user),
):
    if usuario.get("scope") == "por_cliente" and usuario.get("rol_empresa") == "Administrador":
        return resumen_cliente(db, db.get(Cliente, usuario["cliente_id"]))
    if usuario.get("rol") != "Cliente Final":
        raise HTTPException(status_code=403, detail="Solo el Cliente Final puede consultar su plan")
    sede_id = usuario.get("sede_id")
    sede = db.get(Sede, sede_id) if sede_id is not None else None
    if sede is None:
        raise HTTPException(status_code=404, detail="No hay un cliente asociado a tu cuenta")
    cliente = db.get(Cliente, sede.id_clnt)
    resumen = resumen_cliente(db, cliente)
    resumen["ubicaciones_visibles"] = (
        db.query(Ubicacion)
        .join(Sede, Sede.id_sd == Ubicacion.id_sd)
        .join(PermisoUbicacion, PermisoUbicacion.id_ubccn == Ubicacion.id_ubccn)
        .filter(
            Sede.id_clnt == cliente.id_clnt,
            Ubicacion.estd == "Activa",
            PermisoUbicacion.id_usr == int(usuario["sub"]),
        )
        .count()
    )
    return resumen


@router.put("/clientes/{id_clnt}/suscripcion")
def asignar_suscripcion(
    id_clnt: int,
    body: SuscripcionAsignar,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Comercial", EDICION)),
):
    _solo_comercial(usuario)
    contrato, creado = registrar_contrato(db, id_clnt, body, usuario)
    db.commit()
    return {"mensaje": "Suscripción programada correctamente" if contrato.estd == "Programada" else "Suscripción asignada correctamente" if creado else "Suscripción ya registrada",
            "suscripcion_id": contrato.id_sscrpcn, "cliente": resumen_cliente(db, db.get(Cliente, id_clnt))}


@router.post("/clientes/{id_clnt}/suscripcion/preview")
def previsualizar_suscripcion(id_clnt: int, body: SuscripcionAsignar, db: Session = Depends(get_db),
                             usuario: dict = Depends(require_permiso("Comercial", EDICION))):
    _solo_comercial(usuario)
    cliente = db.get(Cliente, id_clnt)
    if cliente is None:
        raise HTTPException(404, "Empresa no encontrada")
    if cliente.estd != "Activo":
        raise HTTPException(422, "Activa la empresa antes de contratar una suscripción")
    plan = db.get(PlanSuscripcion, body.plan_id)
    if plan is None or plan.estd != "Activo":
        raise HTTPException(422, "Plan no disponible")
    actual, operacion = validar_operacion(db, id_clnt, body, fecha_comercial())
    condiciones = preparar_condiciones(db, body, plan)
    consumo = resumen_cliente(db, cliente)["consumo"]
    excedidos = [r for r, limite in condiciones["limites"].items() if limite and consumo[r] > limite]
    return {"condiciones": condiciones, "operacion": operacion,
            "suscripcion_actual_id": actual.id_sscrpcn if actual else None, "revision_plan": plan.revision,
            "fecha_inicio": body.fecha_inicio, "fecha_vencimiento": body.fecha_vencimiento,
            "recursos_excedidos": excedidos, "consumo": consumo,
            "advertencia": "Los recursos existentes se conservan; se bloquean nuevas altas donde se excede el cupo" if excedidos else None}


def _acceso_contrato(db, usuario, cliente_id):
    if usuario.get("scope") == "por_cliente" and usuario.get("cliente_id") == cliente_id and usuario.get("rol_empresa") == "Administrador":
        return
    _solo_comercial(usuario)


@router.get("/clientes/{id_clnt}/historial")
def historial(id_clnt: int, db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)):
    _acceso_contrato(db, usuario, id_clnt)
    contratos = db.query(Suscripcion).filter(Suscripcion.id_clnt == id_clnt).order_by(Suscripcion.id_sscrpcn.desc()).all()
    eventos = db.query(LogAuditoria).filter(LogAuditoria.entdd == "Suscripcion",
        LogAuditoria.vlrs_nvs["cliente_id"].as_integer() == id_clnt).order_by(LogAuditoria.id_evnt.desc()).limit(100).all()
    return {"suscripciones": [contrato_dict(db, c, fecha_comercial()) for c in contratos],
            "eventos": [{"id": e.id_evnt, "actor_id": e.id_usr, "actor_nombre": db.get(Usuario, e.id_usr).nmbr_cmplt, "fecha": e.fch_evnt,
                         "accion": e.accn, "antes": e.vlrs_antrrs, "despues": e.vlrs_nvs} for e in eventos]}


@router.get("/mi-acceso")
def mi_acceso(db: Session = Depends(get_db), usuario: dict = Depends(get_current_user)):
    from app.services.contratos import condiciones_de, estado_contrato, ultimo_contrato

    cliente_id = usuario.get("cliente_id")
    if cliente_id is None and usuario.get("sede_id"):
        sede = db.get(Sede, usuario["sede_id"])
        cliente_id = sede.id_clnt if sede else None
    if cliente_id is None:
        raise HTTPException(422, "Selecciona una empresa")
    hoy = fecha_comercial()
    contrato = ultimo_contrato(db, cliente_id, hoy)
    estado = estado_contrato(db, contrato, hoy)
    dias = (contrato.fch_vncmnt - hoy).days if contrato else None
    mensaje = None
    if estado not in {"Vigente", "En gracia"}:
        mensaje = f"{estado}: modo consulta. Se conservan los datos históricos y la recepción de telemetría."
    elif estado == "En gracia":
        mensaje = "La suscripción está en período de gracia. Contacta al administrador de tu empresa."
    elif dias is not None and dias <= 30:
        mensaje = f"La suscripción vence en {dias} días. Contacta al administrador para renovarla."
    habilitada = estado in {"Vigente", "En gracia"} and bool(contrato and condiciones_de(db, contrato)["limites"] is not None)
    if not habilitada and estado in {"Vigente", "En gracia"}:
        mensaje = "El contrato necesita límites configurados. Contacta al administrador."
    return {"cliente_id": cliente_id, "estado": estado, "operacion_habilitada": habilitada,
            "consulta_historica": True, "recepcion_telemetria": True, "aviso": mensaje,
            "funcionalidades": condiciones_de(db, contrato)["funcionalidades"] if contrato else []}


@router.post("/clientes/{id_clnt}/suscripciones/{id_suscripcion}/estado")
def cambiar_estado(id_clnt: int, id_suscripcion: int, body: EstadoCambiar, db: Session = Depends(get_db),
                   usuario: dict = Depends(require_permiso("Comercial", EDICION))):
    _solo_comercial(usuario)
    cliente = db.query(Cliente).filter(Cliente.id_clnt == id_clnt).with_for_update().first()
    if cliente is None:
        raise HTTPException(404, "Empresa no encontrada")
    aplicar_programadas(db, fecha_comercial(), id_clnt)
    contrato = db.query(Suscripcion).filter(Suscripcion.id_clnt == id_clnt, Suscripcion.id_sscrpcn == id_suscripcion).first()
    if contrato is None:
        raise HTTPException(404, "Suscripción no encontrada")
    antes = contrato.estd
    permitidos = {"Suspender": {"Activa"}, "Reactivar": {"Suspendida"}, "Cancelar": {"Activa", "Programada", "Suspendida"}}
    fin_gracia = contrato.fch_vncmnt + timedelta(days=condiciones_de(db, contrato).get("dias_gracia", 0))
    if antes not in permitidos[body.accion] or (body.accion != "Cancelar" and fin_gracia < fecha_comercial()):
        raise HTTPException(409, "La acción no corresponde al estado de esta suscripción")
    contrato.estd = {"Suspender": "Suspendida", "Reactivar": "Activa", "Cancelar": "Cancelada"}[body.accion]
    if antes == "Programada" and body.accion == "Cancelar":
        contrato.estd = "Anulada"
    anuladas = []
    if antes != "Programada" and body.accion == "Cancelar":
        for pendiente in db.query(Suscripcion).filter(Suscripcion.id_clnt == id_clnt,
                Suscripcion.estd == "Programada").all():
            pendiente.estd = "Anulada"
            anuladas.append(pendiente.id_sscrpcn)
    auditar(db, usuario, body.accion.lower(), "Suscripcion", {"estado": antes},
            {"cliente_id": id_clnt, "suscripcion_id": id_suscripcion, "estado": contrato.estd,
             "motivo": body.motivo, "programaciones_anuladas": anuladas})
    db.commit()
    return {"mensaje": "Estado de suscripción actualizado", "cliente": resumen_cliente(db, cliente)}


@router.get("/catalogo")
def catalogo(db: Session = Depends(get_db), usuario: dict = Depends(require_permiso("Comercial", LECTURA))):
    _solo_comercial(usuario)
    return {"funcionalidades": [{"codigo": f.codigo, "nombre": f.nombre, "disponible": bool(f.disponible)}
                              for f in db.query(FuncionalidadComercial).order_by(FuncionalidadComercial.nombre)],
            "complementos": [{"id": c.id, "nombre": c.nombre, "tipo": c.tipo, "precio": str(c.precio),
                "moneda": c.moneda, "cupos": c.cupos, "funcionalidades": c.funcionalidades, "activo": bool(c.activo)}
                for c in db.query(ComplementoComercial).order_by(ComplementoComercial.nombre)]}


@router.post("/funcionalidades", status_code=201)
def crear_funcionalidad(body: FuncionalidadCrear, db: Session = Depends(get_db),
                       usuario: dict = Depends(require_permiso("Comercial", EDICION))):
    _solo_comercial(usuario)
    if db.get(FuncionalidadComercial, body.codigo):
        raise HTTPException(409, "El código de funcionalidad ya existe")
    db.add(FuncionalidadComercial(codigo=body.codigo, nombre=body.nombre.strip(), disponible=int(body.disponible)))
    auditar(db, usuario, "crear_funcionalidad", "CatalogoComercial", despues=body.model_dump())
    db.commit()
    return {"mensaje": "Funcionalidad registrada"}


@router.put("/planes/{id_pln}/funcionalidades")
def guardar_funcionalidades(id_pln: int, body: FuncionalidadesGuardar, db: Session = Depends(get_db),
                           usuario: dict = Depends(require_permiso("Comercial", EDICION))):
    _solo_comercial(usuario)
    plan = db.query(PlanSuscripcion).filter(PlanSuscripcion.id_pln == id_pln).with_for_update().first()
    if plan is None:
        raise HTTPException(404, "Plan no encontrado")
    antes = {"funcionalidades": plan.funcionalidades, "revision": plan.revision}
    plan.funcionalidades = validar_funcionalidades(db, body.funcionalidades, exigir_disponibles=False)
    plan.revision += 1
    auditar(db, usuario, "editar_funcionalidades", "PlanSuscripcion", antes,
            {"plan_id": id_pln, "funcionalidades": plan.funcionalidades, "revision": plan.revision})
    db.commit()
    return {"mensaje": "Nueva revisión de funcionalidades guardada"}


@router.post("/complementos", status_code=201)
def crear_complemento(body: ComplementoCrear, db: Session = Depends(get_db),
                     usuario: dict = Depends(require_permiso("Comercial", EDICION))):
    _solo_comercial(usuario)
    funcionalidades = validar_funcionalidades(db, body.funcionalidades, exigir_disponibles=False)
    if body.tipo == "Servicio" and (any(body.cupos.model_dump().values()) or funcionalidades):
        raise HTTPException(422, "Un servicio puntual no amplía cupos ni concede funcionalidades recurrentes")
    if db.query(ComplementoComercial).filter(func.lower(ComplementoComercial.nombre) == body.nombre.strip().lower()).first():
        raise HTTPException(409, "Ya existe un complemento con ese nombre")
    extra = ComplementoComercial(nombre=body.nombre.strip(), tipo=body.tipo, precio=body.precio,
            moneda=body.moneda, cupos=body.cupos.model_dump(), funcionalidades=funcionalidades)
    db.add(extra)
    db.flush()
    auditar(db, usuario, "crear_complemento", "CatalogoComercial", despues={"id": extra.id, "nombre": extra.nombre})
    db.commit()
    return {"mensaje": "Complemento registrado"}
