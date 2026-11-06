"""Un unico evento por respuesta denegada, sin confirmar la transaccion fallida."""

import logging

from fastapi.exception_handlers import http_exception_handler
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.security.auditoria_contexto import aplicar_contexto

logger = logging.getLogger("auditoria.autorizacion")


async def manejar_denegacion(request, exc):
    db = getattr(request.state, "auditoria_db", None)
    contexto = getattr(request.state, "auditoria_contexto", {})
    oculta_recurso = (
        exc.status_code == 404
        and isinstance(exc.detail, str)
        and exc.detail
        in {
            "Panel no encontrado",
            "Panel no encontrado en el proyecto activo",
            "Proyecto no encontrado",
            "Empresa no encontrada",
            "Ubicación no disponible",
            "Evento no encontrado",
            "Usuario no encontrado",
        }
    )
    if (exc.status_code == 403 or oculta_recurso) and db is not None and contexto.get("id_usr"):
        try:
            bind = db.get_bind()
            if isinstance(bind, Engine):
                # Revierte cualquier escritura pendiente y libera la conexion
                # antes de abrir la transaccion independiente de denegacion.
                db.close()
            # Conexion independiente en produccion. Los tests con transaccion externa
            # usan otro SAVEPOINT y pueden revertir tambien este registro al terminar.
            with Session(bind=bind, join_transaction_mode="create_savepoint") as registro:
                registro.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                registro.execute(text("SET LOCAL lock_timeout = '1000ms'"))
                aplicar_contexto(registro.connection(), contexto)
                datos = contexto.get("denegacion", {})
                params = request.path_params

                def entero(valor):
                    try:
                        return int(valor) if valor is not None else None
                    except (TypeError, ValueError):
                        return None

                empresa = entero(
                    params.get("cliente_id")
                    or request.headers.get("x-cliente-id")
                    or contexto.get("cliente_id")
                )
                proyecto = entero(
                    params.get("proyecto_id")
                    or params.get("id_ubccn")
                    or request.headers.get("x-proyecto-id")
                    or contexto.get("proyecto_id")
                )
                sede = entero(params.get("sede_id") or params.get("id_sd"))
                afectado = entero(params.get("id_usr"))
                encontrado = False
                if params.get("evento_id"):
                    evento = registro.execute(
                        text(
                            "SELECT id_clnt,id_sd,id_ubccn,id_afectado FROM lg_adtr WHERE id_evnt=:id"
                        ),
                        {"id": entero(params["evento_id"])},
                    ).first()
                    if evento:
                        empresa, sede, proyecto, afectado = evento
                        encontrado = True
                if params.get("miembro_id"):
                    miembro = registro.execute(
                        text("SELECT id_usr,id_clnt FROM usr_clnt WHERE id_mmb=:id"),
                        {"id": entero(params["miembro_id"])},
                    ).first()
                    if miembro:
                        afectado, empresa = miembro
                        encontrado = True
                if params.get("id_pnl"):
                    panel = registro.execute(
                        text("SELECT id_sd,id_ubccn_origen FROM pnl WHERE id_pnl=:id"),
                        {"id": entero(params["id_pnl"])},
                    ).first()
                    if panel:
                        sede, proyecto = panel
                        encontrado = True
                if params.get("id_dspstv"):
                    proyecto = registro.execute(
                        text("SELECT id_ubccn FROM dspstv WHERE id_dspstv=:id"),
                        {"id": entero(params["id_dspstv"])},
                    ).scalar_one_or_none()
                if proyecto and not params.get("evento_id"):
                    fila = registro.execute(
                        text(
                            "SELECT s.id_clnt,u.id_sd FROM ubccn u JOIN sd s USING(id_sd) WHERE u.id_ubccn=:id"
                        ),
                        {"id": proyecto},
                    ).first()
                    if fila:
                        empresa, sede = fila
                        encontrado = True
                if sede and not params.get("evento_id"):
                    empresa = registro.execute(
                        text("SELECT id_clnt FROM sd WHERE id_sd=:id"), {"id": sede}
                    ).scalar_one_or_none()
                recurso_especifico = any(
                    k in params
                    for k in (
                        "evento_id",
                        "miembro_id",
                        "id_pnl",
                        "id_dspstv",
                        "proyecto_id",
                        "id_ubccn",
                        "id_usr",
                    )
                )
                if oculta_recurso and not encontrado and empresa and not recurso_especifico:
                    encontrado = registro.execute(
                        text("SELECT EXISTS(SELECT 1 FROM clnt WHERE id_clnt=:id)"), {"id": empresa}
                    ).scalar_one()
                if oculta_recurso and not encontrado and afectado:
                    encontrado = registro.execute(
                        text("SELECT EXISTS(SELECT 1 FROM usr WHERE id_usr=:id)"), {"id": afectado}
                    ).scalar_one()
                if oculta_recurso and not encontrado:
                    return await http_exception_handler(request, exc)
                motivos = {
                    "No tienes permiso para realizar esta acción": "permisos_insuficientes",
                    "No tienes acceso a esta empresa": "empresa_no_autorizada",
                    "No puedes cambiar de empresa": "empresa_no_autorizada",
                    "El proyecto no pertenece a la empresa seleccionada": "proyecto_de_otra_empresa",
                    "No tienes acceso a este proyecto": "proyecto_no_autorizado",
                    "No puedes cambiar de proyecto": "proyecto_no_autorizado",
                    "Solo administradores pueden consultar la auditoria": "rol_insuficiente",
                    "Solo un administrador puede gestionar esta empresa": "rol_insuficiente",
                }
                motivo = motivos.get(str(exc.detail), "permisos_o_ambito_insuficientes")
                if oculta_recurso:
                    motivo = "recurso_fuera_de_ambito"
                if empresa:
                    estado = registro.execute(
                        text("SELECT estd FROM usr_clnt WHERE id_usr=:usr AND id_clnt=:empresa"),
                        {"usr": contexto["id_usr"], "empresa": empresa},
                    ).scalar_one_or_none()
                    if estado == "Inactivo":
                        motivo = "membresia_revocada"
                # Motivo controlado: nunca se copia un error, token o URL con query.
                registro.execute(
                    text("""INSERT INTO lg_adtr
                    (id_usr,id_afectado,id_clnt,id_sd,id_ubccn,accn,entdd,resultado,origen,ejecutor,motivo,operacion,solicitud_id)
                    VALUES (:actor,:afectado,:empresa,:sede,:proyecto,:accion,:entidad,'Denegado','API',:ejecutor,
                            :motivo,:operacion,:solicitud)"""),
                    {
                        "actor": contexto["id_usr"],
                        "afectado": afectado,
                        "motivo": motivo,
                        "empresa": empresa,
                        "sede": sede,
                        "proyecto": proyecto,
                        "accion": datos.get("accion", "acceso_denegado"),
                        "entidad": datos.get("entidad", "autorizacion"),
                        "ejecutor": f"usuario:{contexto['id_usr']}",
                        "operacion": contexto["operacion"],
                        "solicitud": contexto["solicitud"],
                    },
                )
                registro.commit()
        except Exception:
            # Alerta identificable; no incluir str(exc) ni parametros SQL sensibles.
            logger.error(
                "HT11_ALERTA_DENEGACION_NO_REGISTRADA solicitud=%s", contexto.get("solicitud")
            )
    return await http_exception_handler(request, exc)
