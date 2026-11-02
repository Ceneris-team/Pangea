import csv
import datetime as dt
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import text

from app.database import get_db
from app.main import app
from app.models import EventoTexto, Exportacion, UsuarioCliente, UsuarioProyecto
from app.routers import exportaciones as router
from app.security.dependencies import get_current_user
from app.security.entorno import resolver_entorno
from app.services.exportaciones import ahora, revalidar_acceso
from app.tasks import exportaciones as tareas
from tests.routers.test_mediciones import (
    crear_conexion,
    crear_dispositivo,
    crear_medicion,
    crear_parametro,
    crear_ubicacion,
)


class AlmacenFalso:
    objetos = {}
    eliminados = []
    firmas = []

    def __init__(self, bucket=None):
        self.bucket = bucket or "exportaciones-privadas"

    def subir(self, path, key, formato):
        self.objetos[key] = path.read_bytes()
        return "version-1"

    def eliminar(self, key, version=None):
        self.eliminados.append((key, version))
        self.objetos.pop(key, None)

    def firmar(self, key, segundos, version=None):
        self.firmas.append((key, segundos, version))
        return "https://privado.example/descarga-firmada"


@pytest.fixture()
def entorno_exportacion(db_session, fabrica, monkeypatch):
    db = db_session
    monkeypatch.setenv("EXPORT_S3_BUCKET", "exportaciones-privadas")
    monkeypatch.setenv("EXPORT_CHUNK_ROWS", "2")
    monkeypatch.setattr(router, "encolar_exportacion", MagicMock())
    monkeypatch.setattr(tareas, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(tareas, "AlmacenExportaciones", AlmacenFalso)
    monkeypatch.setattr(router, "AlmacenExportaciones", AlmacenFalso)
    monkeypatch.setattr(tareas.notificar_exportacion, "apply_async", MagicMock())
    AlmacenFalso.objetos = {}
    AlmacenFalso.eliminados = []
    AlmacenFalso.firmas = []
    cuenta = fabrica.usuario(fabrica.rol("Administrador"), scp="global")
    sedes = [fabrica.sede(), fabrica.sede()]
    proyectos = [crear_ubicacion(db, sede, f"Proyecto export {i}") for i, sede in enumerate(sedes)]
    dispositivos = [
        crear_dispositivo(db, proyecto, crear_conexion(db, sede), f"DL {i}")
        for i, (sede, proyecto) in enumerate(zip(sedes, proyectos))
    ]
    parametro = crear_parametro(db, f"Nivel export {cuenta.id_usr}")
    texto = crear_parametro(db, f"Evento export {cuenta.id_usr}", tipo_dato="texto")
    fin = ahora()
    for i in range(4):
        crear_medicion(
            db,
            dispositivos[0],
            parametro,
            sedes[0],
            valor=i - 1,
            fecha=fin - dt.timedelta(minutes=i + 1),
        )
    crear_medicion(
        db, dispositivos[1], parametro, sedes[1], valor=999, fecha=fin - dt.timedelta(minutes=1)
    )
    db.add(
        EventoTexto(
            id_dspstv=dispositivos[0].id_dspstv,
            id_prmtr=texto.id_prmtr,
            id_sd=sedes[0].id_sd,
            fch_hr=fin - dt.timedelta(seconds=30),
            vlr='=HYPERLINK("https://example.com")',
        )
    )
    db.flush()
    identidad = resolver_entorno(
        db,
        {"sub": str(cuenta.id_usr), "scope": "global", "rol": "Administrador", "sede_id": None},
        sedes[0].id_clnt,
        proyectos[0].id_ubccn,
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: identidad
    body = {
        "formato": "csv",
        "fecha_inicio": (fin - dt.timedelta(days=1)).isoformat(),
        "fecha_fin": fin.isoformat(),
        "ubicacion_ids": [proyectos[0].id_ubccn],
    }
    try:
        with TestClient(app) as client:
            yield client, db, cuenta, identidad, proyectos, dispositivos, body
    finally:
        app.dependency_overrides.clear()


def solicitar(entorno, **cambios):
    client, db, _, _, _, _, body = entorno
    response = client.post("/exportaciones", json={**body, **cambios})
    assert response.status_code == 202, response.text
    return db.get(Exportacion, response.json()["exportacion"]["id_exprtcn"])


def test_solicitud_no_genera_archivo_en_http_y_persiste_antes_de_encolar(entorno_exportacion):
    exportacion = solicitar(entorno_exportacion)
    assert exportacion.estd == "Pendiente"
    assert exportacion.objeto_clave is None
    assert not AlmacenFalso.objetos
    router.encolar_exportacion.assert_called_once_with(exportacion.id_exprtcn)


def test_selector_de_dispositivos_y_listado_respetan_entorno(entorno_exportacion):
    client, _, _, identidad, _, dispositivos, _ = entorno_exportacion
    exportacion = solicitar(entorno_exportacion)
    opciones = client.get("/exportaciones/dispositivos").json()["items"]
    assert [opcion["id_dspstv"] for opcion in opciones] == [dispositivos[0].id_dspstv]
    assert client.get("/exportaciones").json()["items"][0]["id_exprtcn"] == exportacion.id_exprtcn
    identidad["cliente_id"] = -1
    assert client.get("/exportaciones").json()["items"] == []


@pytest.mark.parametrize("formato", ["csv", "xlsx"])
def test_limite_de_bytes_no_publica_archivo_parcial(entorno_exportacion, monkeypatch, formato):
    _, db, _, _, proyectos, dispositivos, _ = entorno_exportacion
    evento = db.query(EventoTexto).first()
    for i in range(6):
        db.add(
            EventoTexto(
                id_dspstv=dispositivos[0].id_dspstv,
                id_prmtr=evento.id_prmtr,
                id_sd=proyectos[0].id_sd,
                fch_hr=ahora() - dt.timedelta(minutes=i + 1),
                vlr="texto" * 100,
            )
        )
    db.flush()
    monkeypatch.setenv("EXPORT_MAX_BYTES", "1024")
    exportacion = solicitar(entorno_exportacion, formato=formato)
    assert tareas.generar_exportacion(exportacion.id_exprtcn)["estado"] == "Fallida"
    assert not AlmacenFalso.objetos
    assert "tamaño" in exportacion.error


@pytest.mark.parametrize("formato", ["csv", "xlsx"])
def test_exporta_todas_las_paginas_numeros_y_textos_sin_datos_de_otra_empresa(
    entorno_exportacion, formato
):
    exportacion = solicitar(entorno_exportacion, formato=formato)
    resultado = tareas.generar_exportacion(exportacion.id_exprtcn)
    assert resultado == {"estado": "Lista", "filas": 5}
    contenido = AlmacenFalso.objetos[exportacion.objeto_clave]
    if formato == "csv":
        filas = list(csv.reader(io.StringIO(contenido.decode("utf-8-sig"))))
        assert filas[-1][-2].startswith("'=HYPERLINK")
        assert any(fila[-2] == "-1.0000" for fila in filas[1:])
    else:
        libro = load_workbook(io.BytesIO(contenido), read_only=True)
        hoja = libro.active
        filas = list(hoja.values)
        celdas = list(hoja.rows)[-1]
        assert celdas[-2].data_type == "s"
        libro.close()
    assert len(filas) == 6
    assert not any(str(fila[-2]) in {"999", "999.0000"} for fila in filas[1:])
    assert exportacion.url_dscrg is None
    assert (
        dt.timedelta(hours=23, minutes=59)
        < exportacion.fch_exprcn - ahora()
        <= dt.timedelta(hours=24)
    )


def test_reentrega_de_la_tarea_no_duplica_archivo_ni_notificacion(entorno_exportacion):
    exportacion = solicitar(entorno_exportacion)
    tareas.generar_exportacion(exportacion.id_exprtcn)
    clave = exportacion.objeto_clave
    assert tareas.generar_exportacion(exportacion.id_exprtcn) == {"estado": "omitida"}
    assert list(AlmacenFalso.objetos) == [clave]
    tareas.notificar_exportacion.apply_async.assert_called_once()


def test_limite_de_rango_se_rechaza_antes_de_crear_trabajo(entorno_exportacion):
    client, db, _, _, _, _, body = entorno_exportacion
    body["fecha_inicio"] = (ahora() - dt.timedelta(days=40)).isoformat()
    response = client.post("/exportaciones", json=body)
    assert response.status_code == 422
    assert "31 días" in response.json()["detail"]
    assert db.query(Exportacion).count() == 0


@pytest.mark.parametrize(
    "cambios",
    [
        {"formato": "pdf"},
        {"fecha_inicio": "2026-01-01T00:00:00"},
        {"valor_min": 10, "valor_max": 5},
        {"cliente_id": 100},
    ],
)
def test_rechaza_solicitudes_invalidas(entorno_exportacion, cambios):
    client, _, _, _, _, _, body = entorno_exportacion
    assert client.post("/exportaciones", json={**body, **cambios}).status_code == 422


def test_rechaza_proyecto_y_dispositivo_fuera_del_entorno(entorno_exportacion):
    client, _, _, _, proyectos, dispositivos, body = entorno_exportacion
    assert (
        client.post(
            "/exportaciones", json={**body, "ubicacion_ids": [proyectos[1].id_ubccn]}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/exportaciones", json={**body, "dispositivo_ids": [dispositivos[1].id_dspstv]}
        ).status_code
        == 403
    )


def test_limita_solicitudes_simultaneas(entorno_exportacion, monkeypatch):
    monkeypatch.setenv("EXPORT_MAX_ACTIVE_PER_USER", "1")
    solicitar(entorno_exportacion)
    client, _, _, _, _, _, body = entorno_exportacion
    assert client.post("/exportaciones", json=body).status_code == 429


def test_falla_sin_publicar_archivo_parcial_si_supera_filas(entorno_exportacion, monkeypatch):
    monkeypatch.setenv("EXPORT_MAX_ROWS", "3")
    exportacion = solicitar(entorno_exportacion)
    assert tareas.generar_exportacion(exportacion.id_exprtcn)["estado"] == "Fallida"
    assert not AlmacenFalso.objetos
    assert "3 registros" in exportacion.error


def test_descarga_revalida_propietario_entorno_y_expiracion(entorno_exportacion):
    client, db, _, identidad, proyectos, _, _ = entorno_exportacion
    exportacion = solicitar(entorno_exportacion)
    tareas.generar_exportacion(exportacion.id_exprtcn)
    response = client.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga")
    assert response.status_code == 200
    assert 0 < AlmacenFalso.firmas[-1][1] <= 60
    identidad["cliente_id"] = proyectos[1].id_sd  # Cualquier entorno diferente debe fallar.
    assert client.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga").status_code == 404
    identidad["cliente_id"] = exportacion.fltrs_aplcds["cliente_id"]
    identidad["sub"] = "999999"
    assert client.get(f"/exportaciones/{exportacion.id_exprtcn}").status_code == 404
    identidad["sub"] = str(exportacion.id_usr)
    exportacion.fch_exprcn = ahora() - dt.timedelta(seconds=1)
    db.flush()
    assert client.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga").status_code == 410


def test_no_genera_ni_descarga_despues_de_desactivar_usuario(entorno_exportacion):
    client, db, cuenta, _, _, _, _ = entorno_exportacion
    exportacion = solicitar(entorno_exportacion)
    cuenta.estd = "Inactivo"
    db.commit()
    assert tareas.generar_exportacion(exportacion.id_exprtcn)["estado"] == "Fallida"
    assert not AlmacenFalso.objetos
    assert client.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga").status_code == 403


def test_revalida_revocacion_de_proyecto_del_lector(entorno_exportacion, fabrica):
    _, db, _, _, proyectos, _, _ = entorno_exportacion
    usuario = fabrica.usuario(fabrica.rol("Usuario Empresa"), scp="por_cliente")
    from app.models import Sede

    sede = db.get(Sede, proyectos[0].id_sd)
    miembro = UsuarioCliente(id_usr=usuario.id_usr, id_clnt=sede.id_clnt, rol_emp="Lector")
    db.add(miembro)
    db.flush()
    permiso = UsuarioProyecto(id_mmb=miembro.id_mmb, id_ubccn=proyectos[0].id_ubccn)
    db.add(permiso)
    db.flush()
    exportacion = solicitar(entorno_exportacion)
    exportacion.id_usr = usuario.id_usr
    exportacion.fltrs_aplcds = {
        **exportacion.fltrs_aplcds,
        "scope": "por_cliente",
        "rol": "Usuario Empresa",
    }
    db.flush()
    revalidar_acceso(db, exportacion)
    db.delete(permiso)
    db.flush()
    with pytest.raises(Exception) as error:
        revalidar_acceso(db, exportacion)
    assert error.value.status_code == 403


def test_limpieza_elimina_version_expirada_y_bloquea_descarga(entorno_exportacion):
    client, db, _, _, _, _, _ = entorno_exportacion
    exportacion = solicitar(entorno_exportacion)
    tareas.generar_exportacion(exportacion.id_exprtcn)
    clave = exportacion.objeto_clave
    exportacion.fch_exprcn = ahora() - dt.timedelta(seconds=1)
    db.commit()
    assert tareas.mantener_exportaciones()["eliminadas"] == 1
    assert AlmacenFalso.eliminados == [(clave, "version-1")]
    assert exportacion.estd == "Expirada"
    assert not AlmacenFalso.objetos
    assert client.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga").status_code == 410


def test_notificacion_se_reintenta_sin_regenerar_archivo(entorno_exportacion):
    exportacion = solicitar(entorno_exportacion)
    tareas.generar_exportacion(exportacion.id_exprtcn)
    with patch("app.security.mailer.enviar_correo_exportacion", side_effect=OSError("SMTP caído")):
        assert tareas.notificar_exportacion(exportacion.id_exprtcn)["estado"] == "Fallida"
    assert exportacion.estd == "Lista"
    with patch("app.security.mailer.enviar_correo_exportacion") as correo:
        assert tareas.notificar_exportacion(exportacion.id_exprtcn)["estado"] == "Enviada"
        assert "?exportacion=" in correo.call_args.args[1]
        tareas.notificar_exportacion(exportacion.id_exprtcn)
        correo.assert_called_once()
    assert len(AlmacenFalso.objetos) == 1


def test_falla_de_limpieza_se_reintenta_sin_marcar_borrado(entorno_exportacion):
    _, db, _, _, _, _, _ = entorno_exportacion
    exportacion = solicitar(entorno_exportacion)
    tareas.generar_exportacion(exportacion.id_exprtcn)
    exportacion.fch_exprcn = ahora() - dt.timedelta(seconds=1)
    db.commit()
    with patch.object(AlmacenFalso, "eliminar", side_effect=OSError("S3 caído")):
        assert tareas.mantener_exportaciones()["eliminadas"] == 0
    assert exportacion.objeto_clave
    assert tareas.mantener_exportaciones()["eliminadas"] == 1


def test_recupera_solicitud_si_no_se_publico_en_broker(entorno_exportacion):
    exportacion = solicitar(entorno_exportacion)
    with patch.object(tareas, "encolar_exportacion") as encolar:
        tareas.mantener_exportaciones()
        encolar.assert_called_once_with(exportacion.id_exprtcn)


def test_exportacion_atascada_libera_cupo(entorno_exportacion):
    _, db, _, _, _, _, _ = entorno_exportacion
    exportacion = solicitar(entorno_exportacion)
    exportacion.estd = "En proceso"
    exportacion.fch_inicio = ahora() - dt.timedelta(minutes=30)
    db.commit()
    tareas.mantener_exportaciones()
    assert exportacion.estd == "Fallida"


def test_respeta_filtro_numerico_y_muestreo_explicito(entorno_exportacion):
    from app.models import Telemetria

    _, db, _, _, _, dispositivos, _ = entorno_exportacion
    base = ahora().replace(minute=0, second=0, microsecond=0) - dt.timedelta(hours=1)
    lecturas = (
        db.query(Telemetria)
        .filter_by(id_dspstv=dispositivos[0].id_dspstv)
        .order_by(Telemetria.id_lctr)
        .all()
    )
    for i, lectura in enumerate(lecturas):
        lectura.fch_hr = base + dt.timedelta(minutes=i)
    db.flush()
    exportacion = solicitar(entorno_exportacion, valor_min=1, frecuencia_muestreo=60)
    assert tareas.generar_exportacion(exportacion.id_exprtcn)["estado"] == "Lista"
    contenido = AlmacenFalso.objetos[exportacion.objeto_clave]
    filas = list(csv.reader(io.StringIO(contenido.decode("utf-8-sig"))))[1:]
    assert len(filas) == 2  # Una lectura numérica del intervalo y el evento textual.
    assert any(fila[-1] == "texto" for fila in filas)
    assert all(float(fila[-2]) >= 1 for fila in filas if fila[-1] == "numerico")


def test_error_transitorio_reusa_clave_y_no_deja_archivos_huerfanos(entorno_exportacion):
    exportacion = solicitar(entorno_exportacion)
    with patch.object(AlmacenFalso, "subir", side_effect=OSError("Respuesta de subida perdida")):
        assert tareas.generar_exportacion(exportacion.id_exprtcn)["estado"] == "Pendiente"
    clave = exportacion.objeto_clave
    tareas.generar_exportacion(exportacion.id_exprtcn)
    assert exportacion.objeto_clave == clave
    assert exportacion.intentos == 2


def pico_memoria_proceso():
    import sys

    if sys.platform != "win32":
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
    import ctypes

    class Contadores(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (nombre, ctypes.c_size_t)
            for nombre in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    contadores = Contadores()
    contadores.cb = ctypes.sizeof(contadores)
    funcion = ctypes.windll.psapi.GetProcessMemoryInfo
    funcion.argtypes = [ctypes.c_void_p, ctypes.POINTER(Contadores), ctypes.c_ulong]
    if not funcion(ctypes.c_void_p(-1), ctypes.byref(contadores), contadores.cb):
        raise ctypes.WinError()
    return contadores.PeakWorkingSetSize


@pytest.mark.parametrize("formato", ["csv", "xlsx"])
def test_mes_completo_por_minuto_con_memoria_acotada(entorno_exportacion, monkeypatch, formato):
    import time

    from app.models import Dispositivo
    from app.services.particiones import asegurar_particiones

    _, db, _, _, proyectos, dispositivos, body = entorno_exportacion
    fin = ahora().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    inicio = fin - dt.timedelta(days=31)
    asegurar_particiones(db.connection(), inicio.date(), 3)
    dispositivo = db.get(Dispositivo, dispositivos[0].id_dspstv)
    parametros = [crear_parametro(db, f"Benchmark {i}") for i in range(10)]
    db.execute(
        text("""
        INSERT INTO tlmtr (fch_hr, id_dspstv, id_prmtr, id_sd, vlr)
        SELECT serie, :dispositivo, parametro.id_prmtr, :sede, 12.3456
        FROM generate_series(CAST(:inicio AS timestamptz), CAST(:fin AS timestamptz) - interval '1 minute', interval '1 minute') AS serie
        CROSS JOIN prmtr AS parametro WHERE parametro.id_prmtr = ANY(:parametros)
    """),
        {
            "dispositivo": dispositivo.id_dspstv,
            "parametros": [p.id_prmtr for p in parametros],
            "sede": proyectos[0].id_sd,
            "inicio": inicio,
            "fin": fin,
        },
    )
    db.flush()
    monkeypatch.setenv("EXPORT_CHUNK_ROWS", "500")
    exportacion = solicitar(
        entorno_exportacion,
        formato=formato,
        fecha_inicio=inicio.isoformat(),
        fecha_fin=(fin - dt.timedelta(microseconds=1)).isoformat(),
    )
    comienzo = time.perf_counter()
    resultado = tareas.generar_exportacion(exportacion.id_exprtcn)
    pico = pico_memoria_proceso()
    segundos = time.perf_counter() - comienzo
    esperadas = 31 * 24 * 60 * 10
    assert resultado == {"estado": "Lista", "filas": esperadas}
    assert pico < 256 * 1024 * 1024
    assert segundos < 120
    print(
        f"BENCHMARK {formato}: {esperadas} filas; {segundos:.2f}s; RSS pico {pico / 1024 / 1024:.2f} MiB"
    )
