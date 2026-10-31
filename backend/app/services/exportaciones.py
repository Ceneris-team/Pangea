import csv
import datetime as dt
import heapq
import os
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from sqlalchemy import func, text

from app.models import (
    Dispositivo,
    EventoTexto,
    Exportacion,
    Parametro,
    Sede,
    Telemetria,
    Ubicacion,
    Usuario,
)
from app.schemas_exportaciones import ExportacionCrear
from app.security.entorno import permiso_del_entorno, resolver_entorno
from app.security.permisos import LECTURA, tiene_permiso
from app.security.ubicaciones_permitidas import ubicaciones_permitidas

CABECERAS = [
    "Empresa",
    "Sede",
    "Proyecto",
    "ID dispositivo",
    "Dispositivo",
    "ID parámetro",
    "Parámetro",
    "Unidad",
    "Fecha y hora",
    "Valor",
    "Tipo",
]


def ahora():
    return dt.datetime.now(dt.timezone.utc)


def limites():
    return {
        "max_dias": max(1, int(os.getenv("EXPORT_MAX_DAYS", "31"))),
        "max_filas": min(1_048_575, max(1, int(os.getenv("EXPORT_MAX_ROWS", "1000000")))),
        "max_bytes": max(1024, int(os.getenv("EXPORT_MAX_BYTES", "104857600"))),
        "lote": max(1, min(10000, int(os.getenv("EXPORT_CHUNK_ROWS", "2000")))),
        "vigencia_horas": max(1, min(168, int(os.getenv("EXPORT_TTL_HOURS", "24")))),
        "simultaneas": max(1, int(os.getenv("EXPORT_MAX_ACTIVE_PER_USER", "2"))),
    }


def validar_solicitud(db, usuario, body: ExportacionCrear):
    if body.fecha_fin - body.fecha_inicio > dt.timedelta(days=limites()["max_dias"]):
        raise HTTPException(
            422,
            f"El rango máximo por exportación es de {limites()['max_dias']} días. Divide la consulta en varios periodos.",
        )
    visibles = set(ubicaciones_permitidas(db, usuario))
    solicitadas = set(body.ubicacion_ids) or visibles
    if not solicitadas or not solicitadas <= visibles:
        raise HTTPException(403, "No tienes acceso a todos los proyectos solicitados")
    if body.dispositivo_ids:
        validos = {
            id_
            for (id_,) in db.query(Dispositivo.id_dspstv).filter(
                Dispositivo.id_ubccn.in_(solicitadas),
                Dispositivo.id_dspstv.in_(body.dispositivo_ids),
            )
        }
        if validos != set(body.dispositivo_ids):
            raise HTTPException(403, "No tienes acceso a todos los dispositivos solicitados")
    filtros = body.model_dump(mode="json", exclude={"formato"})
    filtros.update(
        ubicacion_ids=sorted(solicitadas),
        cliente_id=usuario.get("cliente_id"),
        proyecto_id=usuario.get("proyecto_id"),
        sede_id=usuario.get("sede_id"),
        scope=usuario["scope"],
        rol=usuario["rol"],
    )
    return filtros


def revalidar_acceso(db, exportacion):
    cuenta = db.get(Usuario, exportacion.id_usr, populate_existing=True)
    filtros = exportacion.fltrs_aplcds
    if (
        cuenta is None
        or cuenta.estd != "Activo"
        or cuenta.scp != filtros["scope"]
        or cuenta.rol.nmbr != filtros["rol"]
    ):
        raise HTTPException(403, "Tu acceso cambió. Solicita una nueva exportación")
    usuario = resolver_entorno(
        db,
        {
            "sub": str(cuenta.id_usr),
            "scope": cuenta.scp,
            "rol": cuenta.rol.nmbr,
            "sede_id": filtros.get("sede_id"),
        },
        filtros.get("cliente_id"),
        filtros.get("proyecto_id"),
    )
    permitido = permiso_del_entorno(db, usuario, "Tableros", LECTURA)
    if permitido is None:
        permitido = tiene_permiso(db, cuenta.id_usr, usuario.get("sede_id"), "Tableros", LECTURA)
    if not permitido or not set(filtros["ubicacion_ids"]) <= set(
        ubicaciones_permitidas(db, usuario)
    ):
        raise HTTPException(403, "Ya no tienes acceso a todos los datos de esta exportación")
    # Un dispositivo trasladado a otro proyecto no debe cambiar el alcance del archivo.
    if filtros.get("dispositivo_ids"):
        ids = {
            id_
            for (id_,) in db.query(Dispositivo.id_dspstv).filter(
                Dispositivo.id_dspstv.in_(filtros["dispositivo_ids"]),
                Dispositivo.id_ubccn.in_(filtros["ubicacion_ids"]),
            )
        }
        if ids != set(filtros["dispositivo_ids"]):
            raise HTTPException(403, "El alcance del dispositivo cambió")
    return cuenta


def obtener_propia(db, id_exportacion, usuario):
    exportacion = (
        db.query(Exportacion)
        .filter_by(id_exprtcn=id_exportacion, id_usr=int(usuario["sub"]))
        .first()
    )
    if exportacion is None:
        raise HTTPException(404, "Exportación no encontrada")
    if exportacion.fltrs_aplcds.get("cliente_id") != usuario.get(
        "cliente_id"
    ) or exportacion.fltrs_aplcds.get("proyecto_id") != usuario.get("proyecto_id"):
        raise HTTPException(
            404, "La exportación pertenece a otro entorno. Abre la empresa y el proyecto originales"
        )
    revalidar_acceso(db, exportacion)
    return exportacion


def _lecturas(db, modelo, filtros, lote):
    from app.models import Cliente

    id_lectura = modelo.id_lctr if modelo is Telemetria else modelo.id_evnt
    query = (
        db.query(
            modelo.fch_hr,
            id_lectura,
            Cliente.rzn_scl,
            Sede.nmbr,
            Ubicacion.nmbr,
            Dispositivo.id_dspstv,
            Dispositivo.nmbr,
            Parametro.id_prmtr,
            Parametro.nmbr,
            Parametro.undd,
            modelo.vlr,
        )
        .select_from(modelo)
        .join(Dispositivo, Dispositivo.id_dspstv == modelo.id_dspstv)
        .join(Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn)
        .join(Sede, Sede.id_sd == Ubicacion.id_sd)
        .join(Cliente, Cliente.id_clnt == Sede.id_clnt)
        .join(Parametro, Parametro.id_prmtr == modelo.id_prmtr)
        .filter(
            Dispositivo.id_ubccn.in_(filtros["ubicacion_ids"]),
            modelo.fch_hr >= dt.datetime.fromisoformat(filtros["fecha_inicio"]),
            modelo.fch_hr <= dt.datetime.fromisoformat(filtros["fecha_fin"]),
        )
    )
    for campo, columna in (
        ("dispositivo_ids", modelo.id_dspstv),
        ("parametro_ids", modelo.id_prmtr),
    ):
        if filtros[campo]:
            query = query.filter(columna.in_(filtros[campo]))
    if modelo is Telemetria:
        if filtros["valor_min"] is not None:
            query = query.filter(modelo.vlr >= Decimal(filtros["valor_min"]))
        if filtros["valor_max"] is not None:
            query = query.filter(modelo.vlr <= Decimal(filtros["valor_max"]))
    if filtros["frecuencia_muestreo"] is not None:
        bucket = func.date_bin(
            dt.timedelta(minutes=filtros["frecuencia_muestreo"]),
            modelo.fch_hr,
            dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc),
        )
        query = query.distinct(modelo.id_dspstv, modelo.id_prmtr, bucket).order_by(
            modelo.id_dspstv, modelo.id_prmtr, bucket, modelo.fch_hr.desc(), id_lectura.desc()
        )
        sub = query.subquery()
        query = db.query(*sub.c).order_by(sub.c[0], sub.c[1])
    else:
        query = query.order_by(modelo.fch_hr, id_lectura)
    return query.limit(limites()["max_filas"] + 1).yield_per(lote)


def celda_csv(valor):
    if isinstance(valor, str) and valor.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + valor
    return valor


def generar_archivo(db, exportacion, destino):
    config = limites()
    # Cada lectura usa un cursor de servidor; heapq.merge solo conserva una fila por cursor.
    db.execute(text("SET LOCAL statement_timeout = '300000'"))
    numericas = _lecturas(db, Telemetria, exportacion.fltrs_aplcds, config["lote"])
    eventos = _lecturas(db, EventoTexto, exportacion.fltrs_aplcds, config["lote"])
    fuentes = (
        ((fila, "numerico") for fila in numericas),
        ((fila, "texto") for fila in eventos),
    )
    filas = heapq.merge(*fuentes, key=lambda item: (item[0][0], item[1], item[0][1]))
    zona = ZoneInfo(exportacion.fltrs_aplcds["zona_horaria"])
    libro = Workbook(write_only=True) if exportacion.frmt == "xlsx" else None
    hoja = libro.create_sheet("Telemetría") if libro else None
    archivo_csv = open(destino, "w", newline="", encoding="utf-8-sig") if not libro else None
    escritor = csv.writer(archivo_csv) if archivo_csv else None

    def escribir(valores):
        if escritor:
            escritor.writerow([celda_csv(v) for v in valores])
        else:
            celdas = []
            for valor in valores:
                if isinstance(valor, str) and valor.startswith("="):
                    celda = WriteOnlyCell(hoja, value=valor)
                    celda.data_type = "s"
                    celdas.append(celda)
                else:
                    celdas.append(valor)
            hoja.append(celdas)

    cantidad = 0
    try:
        escribir(CABECERAS)
        for fila, tipo in filas:
            cantidad += 1
            if cantidad > config["max_filas"]:
                raise ValueError(
                    f"La exportación supera el máximo de {config['max_filas']} registros. Reduce el rango o los filtros."
                )
            (
                fecha,
                _,
                empresa,
                sede,
                proyecto,
                id_dispositivo,
                dispositivo,
                id_parametro,
                parametro,
                unidad,
                valor,
            ) = fila
            escribir(
                [
                    empresa,
                    sede,
                    proyecto,
                    id_dispositivo,
                    dispositivo,
                    id_parametro,
                    parametro,
                    unidad,
                    fecha.astimezone(zona).isoformat(),
                    valor,
                    tipo,
                ]
            )
            if cantidad % config["lote"] == 0 and archivo_csv:
                archivo_csv.flush()
                if archivo_csv.tell() > config["max_bytes"]:
                    raise ValueError(
                        "El archivo supera el tamaño máximo configurado. Reduce la consulta."
                    )
        if libro:
            libro.save(destino)
    finally:
        if archivo_csv:
            archivo_csv.close()
        if libro:
            if not hoja.closed:
                hoja.close()
            libro.close()
            # openpyxl usa XML temporal en modo write_only, incluso si falla el límite.
            if hoja._writer and os.path.exists(hoja._writer.out):
                hoja._writer.cleanup()
    tamano = Path(destino).stat().st_size
    if tamano > config["max_bytes"]:
        raise ValueError("El archivo supera el tamaño máximo configurado. Reduce la consulta.")
    return cantidad, tamano
