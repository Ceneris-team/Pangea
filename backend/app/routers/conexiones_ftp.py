"""
HU 05 - Configurar conexión FTP del datalogger

CA: formulario con Nombre del datalogger, Host/IP, Puerto (default 21),
Usuario FTP, Contraseña FTP, Directorio remoto y Frecuencia de polling
(cada minuto / cada hora). "PROBAR CONEXIÓN" valida las credenciales
contra el servidor FTP real antes de habilitar "GUARDAR". Las
credenciales se cifran (HT-04, app/security/ftp_crypto.py) y nunca se
devuelven en texto plano. Solo Técnico CENERIS y Administrador acceden.
"""

import ftplib
import socket

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConexionFTP
from app.schemas import (
    ConexionFTPCreate,
    ConexionFTPListItem,
    ConexionFTPProbarRequest,
    ConexionFTPUpdate,
)
from app.security.dependencies import get_current_user
from app.security.ftp_crypto import encrypt_credential

router = APIRouter(prefix="/conexiones-ftp", tags=["Conexiones FTP"])

ROLES_CON_ACCESO = {"Administrador", "Técnico CENERIS", "Tecnico CENERIS"}
FRECUENCIAS_VALIDAS = {1, 60}  # CA: "cada minuto" o "cada hora"
TIMEOUT_SEGUNDOS = 8


def _requerir_tecnico_o_admin(usuario: dict = Depends(get_current_user)) -> dict:
    """HU 05 CA: 'Solo los roles Técnico CENERIS y Administrador tienen
    acceso a este módulo.'"""
    if usuario.get("rol") not in ROLES_CON_ACCESO:
        raise HTTPException(
            status_code=403,
            detail="Solo Técnico CENERIS o Administrador pueden acceder a este módulo",
        )
    return usuario


def _resolver_sede(usuario: dict, id_sd_body: int | None) -> int:
    """Un usuario con scope 'por_sede' siempre opera sobre su propia sede
    (viene en el token, HT-04). Un usuario 'global' debe indicar a qué
    sede pertenece el datalogger."""
    if usuario.get("scope") == "por_sede":
        return usuario["sede_id"]
    if id_sd_body is None:
        raise HTTPException(
            status_code=422,
            detail="Debe indicar id_sd: su usuario no está limitado a una sede única",
        )
    return id_sd_body


def _validar_frecuencia(frcnc_mnts: int) -> None:
    if frcnc_mnts not in FRECUENCIAS_VALIDAS:
        raise HTTPException(
            status_code=422,
            detail="La frecuencia de polling solo admite 'cada minuto' (1) o 'cada hora' (60)",
        )


@router.get("")
def listar_conexiones(
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: dict = Depends(_requerir_tecnico_o_admin),
):
    """CA: 'VER CONEXIONES' redirige al listado, la nueva configuración
    aparece registrada con estado 'Activo'."""
    query = db.query(ConexionFTP)
    if usuario.get("scope") == "por_sede":
        query = query.filter(ConexionFTP.id_sd == usuario["sede_id"])

    total = query.count()
    conexiones = (
        query.order_by(ConexionFTP.nmbr).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
    )

    items = [ConexionFTPListItem.model_validate(c) for c in conexiones]
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}


@router.post("/probar")
def probar_conexion(
    body: ConexionFTPProbarRequest,
    _usuario: dict = Depends(_requerir_tecnico_o_admin),
):
    """CA: 'PROBAR CONEXIÓN' intenta conectarse al servidor FTP con las
    credenciales ingresadas y muestra 'Conexión exitosa' antes de habilitar
    GUARDAR. No persiste nada en la base de datos."""
    try:
        with ftplib.FTP(timeout=TIMEOUT_SEGUNDOS) as ftp:
            ftp.connect(host=body.hst, port=body.prt)
            ftp.login(user=body.usr_ftp, passwd=body.contrasena_ftp)
            ftp.cwd(body.rt_rmt)
    except ftplib.error_perm as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Credenciales o directorio remoto inválidos: {exc}",
        )
    except (socket.timeout, socket.gaierror, ConnectionRefusedError, OSError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo conectar al servidor FTP: {exc}",
        )

    return {"exitosa": True, "mensaje": "Conexión exitosa"}


@router.get("/{id_cnxn}", response_model=ConexionFTPListItem)
def obtener_conexion(
    id_cnxn: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(_requerir_tecnico_o_admin),
):
    """Detalle de una conexión para prellenar el formulario de edición.
    No incluye la contraseña: igual que en la creación, las credenciales
    cifradas nunca se devuelven en texto plano (CA de HU05)."""
    conexion = db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == id_cnxn).first()
    if conexion is None:
        raise HTTPException(status_code=404, detail="Conexión FTP no encontrada")

    if usuario.get("scope") == "por_sede" and conexion.id_sd != usuario["sede_id"]:
        raise HTTPException(status_code=403, detail="No tiene acceso a esta conexión")

    return ConexionFTPListItem.model_validate(conexion)


@router.post("", status_code=201)
def crear_conexion(
    body: ConexionFTPCreate,
    db: Session = Depends(get_db),
    usuario: dict = Depends(_requerir_tecnico_o_admin),
):
    """CA: 'GUARDAR' registra la configuración FTP y muestra
    'Conexión FTP configurada correctamente'."""
    _validar_frecuencia(body.frcnc_mnts)
    id_sd = _resolver_sede(usuario, body.id_sd)

    conexion = ConexionFTP(
        id_sd=id_sd,
        nmbr=body.nmbr,
        prtcl="FTP",
        hst=body.hst,
        prt=body.prt,
        usr_ftp=body.usr_ftp,
        crdncl_cfrd=encrypt_credential(body.contrasena_ftp),
        rt_rmt=body.rt_rmt,
        frcnc_mnts=body.frcnc_mnts,
        estd="Activa",
    )
    db.add(conexion)
    db.commit()
    db.refresh(conexion)

    return {
        "mensaje": "Conexión FTP configurada correctamente",
        "conexion": ConexionFTPListItem.model_validate(conexion),
    }


@router.put("/{id_cnxn}")
def actualizar_conexion(
    id_cnxn: int,
    body: ConexionFTPUpdate,
    db: Session = Depends(get_db),
    usuario: dict = Depends(_requerir_tecnico_o_admin),
):
    """CA: 'ACTUALIZAR' guarda los nuevos valores y muestra
    'Configuración actualizada correctamente'."""
    conexion = db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == id_cnxn).first()
    if conexion is None:
        raise HTTPException(status_code=404, detail="Conexión FTP no encontrada")

    if usuario.get("scope") == "por_sede" and conexion.id_sd != usuario["sede_id"]:
        raise HTTPException(status_code=403, detail="No tiene acceso a esta conexión")

    if body.frcnc_mnts is not None:
        _validar_frecuencia(body.frcnc_mnts)

    datos = body.model_dump(exclude_unset=True, exclude={"contrasena_ftp"})
    for campo, valor in datos.items():
        setattr(conexion, campo, valor)

    if body.contrasena_ftp:
        conexion.crdncl_cfrd = encrypt_credential(body.contrasena_ftp)

    db.commit()
    db.refresh(conexion)

    return {
        "mensaje": "Configuración actualizada correctamente",
        "conexion": ConexionFTPListItem.model_validate(conexion),
    }


@router.delete("/{id_cnxn}")
def eliminar_conexion(
    id_cnxn: int,
    db: Session = Depends(get_db),
    usuario: dict = Depends(_requerir_tecnico_o_admin),
):
    """Desactiva la conexión (estd='Inactiva') en vez de borrar la fila.

    Un borrado físico rompería la FK NOT NULL de Dispositivo.id_cnxn si
    algún dispositivo la sigue referenciando, y perdería el historial de
    archv_ingst asociado a esta conexión. Desactivarla la saca del
    sondeo automático (sondear_conexiones_ftp filtra por estd='Activa')
    sin romper nada: si hay un dispositivo apuntándole, sigue existiendo
    pero deja de sondearse hasta que se reasigne a otra conexión activa.
    """
    conexion = db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == id_cnxn).first()
    if conexion is None:
        raise HTTPException(status_code=404, detail="Conexión FTP no encontrada")

    if usuario.get("scope") == "por_sede" and conexion.id_sd != usuario["sede_id"]:
        raise HTTPException(status_code=403, detail="No tiene acceso a esta conexión")

    conexion.estd = "Inactiva"
    db.commit()

    return {"mensaje": "Conexión FTP eliminada correctamente"}
