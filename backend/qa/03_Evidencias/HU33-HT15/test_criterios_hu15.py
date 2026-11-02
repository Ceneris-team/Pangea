"""
QA - HU-15 (HU33) Pipeline de exportación en background con Celery (PP-283 a PP-286, PP-408).
Ronda 2: criterios de aceptación nuevos (vigencia, límites de Excel, revocaciones, temporales y rendimiento).

Ejecutar desde backend/ con la BD de test migrada:
    TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/pangea_test \
    venv/Scripts/python.exe -m pytest qa/03_Evidencias/HU33-HT15/test_criterios_hu15.py \
        --html=qa/03_Evidencias/HU33-HT15/pytest_criterios_hu15.html --self-contained-html

El rendimiento (test_rendimiento_*) se mide en un contenedor con los límites del worker de referencia
(2 CPU y 512 MiB): ver ejecutar_rendimiento_referencia.sh.
"""

import datetime as dt
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.models import Dispositivo
from app.services.exportaciones import ahora, limites
from app.services.particiones import asegurar_particiones
from app.tasks import exportaciones as tareas
from tests.conftest import _engine, db_session, fabrica  # noqa: F401
from tests.routers.test_exportaciones import (  # noqa: F401
    AlmacenFalso,
    entorno_exportacion,
    solicitar,
)
from tests.routers.test_mediciones import crear_parametro


def test_limite_de_filas_nunca_supera_el_maximo_de_excel(monkeypatch):
    monkeypatch.setenv("EXPORT_MAX_ROWS", "5000000")
    assert limites()["max_filas"] == 1_048_575


def test_limites_iniciales_son_los_del_criterio(monkeypatch):
    for variable in ("EXPORT_MAX_DAYS", "EXPORT_MAX_ROWS", "EXPORT_MAX_BYTES", "EXPORT_MAX_ACTIVE_PER_USER", "EXPORT_TTL_HOURS"):
        monkeypatch.delenv(variable, raising=False)
    config = limites()
    assert config["max_dias"] == 31
    assert config["max_filas"] == 1_000_000
    assert config["max_bytes"] == 100 * 1024 * 1024
    assert config["simultaneas"] == 2
    assert config["vigencia_horas"] == 24


def test_vigencia_no_cambia_al_descargar_reenviar_o_recargar(entorno_exportacion):
    client, db, _, _, _, _, _ = entorno_exportacion
    exportacion = solicitar(entorno_exportacion)
    tareas.generar_exportacion(exportacion.id_exprtcn)
    limite = exportacion.fch_exprcn
    for _ in range(3):
        assert client.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga").status_code == 200
        client.get(f"/exportaciones/{exportacion.id_exprtcn}")
    exportacion.notificada_en = None
    exportacion.notificacion_estado = "Pendiente"
    db.flush()
    tareas.notificar_exportacion(exportacion.id_exprtcn)
    db.refresh(exportacion)
    assert exportacion.fch_exprcn == limite
    assert all(segundos <= 60 for _, segundos, _ in AlmacenFalso.firmas)
    assert len(AlmacenFalso.firmas) == 3


def test_no_firma_despues_de_vencer(entorno_exportacion):
    client, db, _, _, _, _, _ = entorno_exportacion
    exportacion = solicitar(entorno_exportacion)
    tareas.generar_exportacion(exportacion.id_exprtcn)
    exportacion.fch_exprcn = ahora() - dt.timedelta(seconds=1)
    db.flush()
    firmas = len(AlmacenFalso.firmas)
    assert client.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga").status_code == 410
    assert len(AlmacenFalso.firmas) == firmas


def test_cambio_de_alcance_bloquea_nuevas_descargas_y_firmas(entorno_exportacion):
    client, db, cuenta, _, _, _, _ = entorno_exportacion
    exportacion = solicitar(entorno_exportacion)
    tareas.generar_exportacion(exportacion.id_exprtcn)
    assert client.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga").status_code == 200
    firmas = len(AlmacenFalso.firmas)
    cuenta.scp = "por_sede"
    db.flush()
    assert client.post(f"/exportaciones/{exportacion.id_exprtcn}/descarga").status_code in (403, 404)
    assert len(AlmacenFalso.firmas) == firmas


def test_filtros_se_conservan_y_se_permite_un_dispositivo(entorno_exportacion):
    _, _, _, _, proyectos, dispositivos, _ = entorno_exportacion
    exportacion = solicitar(
        entorno_exportacion, dispositivo_ids=[dispositivos[0].id_dspstv], valor_min="-5", valor_max="5"
    )
    filtros = exportacion.fltrs_aplcds
    assert filtros["dispositivo_ids"] == [dispositivos[0].id_dspstv]
    assert filtros["ubicacion_ids"] == [proyectos[0].id_ubccn]
    assert filtros["valor_min"] == "-5" and filtros["valor_max"] == "5"


def test_temporales_locales_se_limpian_con_exito_y_con_excepcion(entorno_exportacion, monkeypatch):
    carpetas = []
    original = tempfile.TemporaryDirectory

    class Registrada(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            carpetas.append(Path(self.name))

    monkeypatch.setattr(tareas.tempfile, "TemporaryDirectory", Registrada)
    exito = solicitar(entorno_exportacion)
    assert tareas.generar_exportacion(exito.id_exprtcn)["estado"] == "Lista"
    fallo = solicitar(entorno_exportacion)
    monkeypatch.setattr(
        AlmacenFalso, "subir", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fallo al subir"))
    )
    tareas.generar_exportacion(fallo.id_exprtcn)
    assert len(carpetas) == 2
    assert not any(carpeta.exists() for carpeta in carpetas)


# ---------------- Rendimiento en el worker de referencia (2 CPU y 512 MiB) ----------------
def _pico_rss_mib():
    """Pico de memoria residente del proceso (VmHWM en Linux; en Windows no se usa para aprobar)."""
    if sys.platform.startswith("linux"):
        for linea in Path("/proc/self/status").read_text().splitlines():
            if linea.startswith("VmHWM"):
                return int(linea.split()[1]) / 1024
    return float("nan")


def _pico_cgroup_mib():
    for ruta in ("/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory/memory.max_usage_in_bytes"):
        if os.path.exists(ruta):
            return int(Path(ruta).read_text()) / 1024 / 1024
    return float("nan")


@pytest.mark.parametrize("formato", ["csv", "xlsx"])
def test_rendimiento_un_mes_diez_parametros_por_minuto(entorno_exportacion, monkeypatch, formato):
    _, db, _, _, proyectos, dispositivos, _ = entorno_exportacion
    fin = ahora().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    inicio = fin - dt.timedelta(days=31)
    asegurar_particiones(db.connection(), inicio.date(), 3)
    dispositivo = db.get(Dispositivo, dispositivos[0].id_dspstv)
    parametros = [crear_parametro(db, f"Referencia {i}") for i in range(10)]
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
    monkeypatch.delenv("EXPORT_CHUNK_ROWS", raising=False)
    exportacion = solicitar(
        entorno_exportacion,
        formato=formato,
        fecha_inicio=inicio.isoformat(),
        fecha_fin=(fin - dt.timedelta(microseconds=1)).isoformat(),
        parametro_ids=[p.id_prmtr for p in parametros],
    )
    base_rss = _pico_rss_mib()
    comienzo = time.perf_counter()
    resultado = tareas.generar_exportacion(exportacion.id_exprtcn)
    segundos = time.perf_counter() - comienzo
    pico, cgroup = _pico_rss_mib(), _pico_cgroup_mib()
    esperadas = 31 * 24 * 60 * 10
    print(
        f"REFERENCIA {formato}: filas={resultado.get('filas')}; duracion={segundos:.2f}s; "
        f"tamano={exportacion.bytes_archivo / 1024 / 1024:.2f}MiB; RSS_pico={pico:.1f}MiB; "
        f"cgroup_pico={cgroup:.1f}MiB; RSS_antes={base_rss:.1f}MiB"
    )
    assert resultado == {"estado": "Lista", "filas": esperadas}
    assert segundos <= 120
    if sys.platform.startswith("linux"):
        assert pico <= 256
