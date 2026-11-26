"""HU31: navegador real con API y PostgreSQL aislados, sin servicios externos."""

import json
import os
from urllib.parse import urlparse

import pytest

from app.models import ArchivoIngesta, IntentoProcesamiento, Rol
from app.tasks import reprocesos
from tests.routers.test_reprocesos import entorno as entorno


def test_permiso_lectura_muestra_cola_e_historial_sin_acciones(entorno):
    base = os.getenv("REPROCESOS_UI_URL")
    if not base:
        pytest.skip("Definir REPROCESOS_UI_URL para probar la interfaz")
    from playwright.sync_api import expect, sync_playwright

    from app.models.suscripcion import PermisoUsuarioSede

    e = entorno
    e["identidad"].update(
        scope="por_sede", sede_id=e["sede"].id_sd, cliente_id=None, proyecto_id=None
    )
    e["db"].add(
        PermisoUsuarioSede(
            id_usr=e["usuario"].id_usr,
            id_sd=e["sede"].id_sd,
            id_rl=e["usuario"].id_rl,
            mdl="Ingesta",
            nvl="Lectura",
        )
    )
    e["db"].commit()
    posts = []

    def responder(route):
        req = route.request
        if req.resource_type not in {"fetch", "xhr"}:
            route.continue_() if req.url.startswith(base) else route.abort()
            return
        url = urlparse(req.url)
        if req.method == "POST":
            posts.append(url.path)
        if url.path == "/auth/perfil":
            route.fulfill(
                json={
                    "nombre_completo": "Técnico lector",
                    "correo": "qa@example.com",
                    "rol": "Técnico CENERIS",
                    "scope": "por_sede",
                    "estado": "Activo",
                    "debe_cambiar_contrasena": False,
                    "zona_horaria": "America/Lima",
                    "operacion_habilitada": True,
                    "rol_empresa": None,
                    "cliente_id": e["sede"].id_clnt,
                    "proyecto_id": None,
                }
            )
        elif url.path == "/comercial/mi-acceso":
            route.fulfill(json={"operacion_habilitada": True, "aviso": None})
        elif url.path.startswith("/ingesta"):
            r = e["client"].get(f"{url.path}?{url.query}")
            assert r.status_code == 200, r.text
            route.fulfill(json=r.json())
        else:
            route.fulfill(json={"items": [], "total": 0})

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        pagina = browser.new_page(viewport={"width": 390, "height": 1000})
        pagina.add_init_script(f"sessionStorage.setItem('pangea_cliente','{e['sede'].id_clnt}');")
        pagina.route("**/*", responder)
        try:
            pagina.goto(f"{base}/cola-ingesta")
            pagina.get_by_role("button", name="Ver detalle", exact=True).click()
            detalle = pagina.get_by_role("dialog", name="Detalle del archivo", exact=True)
            expect(detalle).to_contain_text("Historial de intentos")
            expect(detalle.get_by_role("button", name="Reintentar", exact=True)).to_have_count(0)
            expect(
                pagina.get_by_role("button", name="Reintentar todos los fallidos", exact=False)
            ).to_have_count(0)
            assert posts == []
        finally:
            browser.close()


@pytest.mark.parametrize("ancho", [1365, 390])
@pytest.mark.parametrize("rol", ["Técnico CENERIS", "Administrador"])
def test_reproceso_individual_masivo_cancelacion_historial_y_refresco(
    entorno, ancho, rol, tmp_path
):
    base = os.getenv("REPROCESOS_UI_URL")
    if not base:
        pytest.skip("Definir REPROCESOS_UI_URL para probar la interfaz")
    from playwright.sync_api import expect, sync_playwright

    e = entorno
    e["usuario"].rol = e["db"].query(Rol).filter_by(nmbr=rol).one()
    e["identidad"]["rol"] = rol
    for i in range(12):
        e["db"].add(
            ArchivoIngesta(
                id_cnxn=e["conexion"].id_cnxn,
                id_dspstv=e["equipo"].id_dspstv,
                nmbr_archv=f"H_pendiente_{i}.dat",
                estd="Fallido",
                mnsj_errr="Mapeo pendiente",
            )
        )
    e["db"].commit()
    errores, solicitudes = [], []

    def responder(route):
        req = route.request
        if req.resource_type not in {"fetch", "xhr"}:
            route.continue_() if req.url.startswith(base) else route.abort()
            return
        url = urlparse(req.url)
        if url.path == "/auth/perfil":
            route.fulfill(
                json={
                    "nombre_completo": "Técnico QA",
                    "correo": "qa@example.com",
                    "rol": rol,
                    "scope": "global",
                    "estado": "Activo",
                    "debe_cambiar_contrasena": False,
                    "zona_horaria": "America/Lima",
                    "operacion_habilitada": True,
                    "rol_empresa": None,
                    "cliente_id": e["sede"].id_clnt,
                    "proyecto_id": e["proyecto"].id_ubccn,
                }
            )
            return
        if url.path == "/comercial/mi-acceso":
            route.fulfill(json={"operacion_habilitada": True, "aviso": None})
            return
        if url.path.startswith("/ingesta"):
            respuesta = e["client"].request(req.method, f"{url.path}?{url.query}")
            assert respuesta.status_code == 200, respuesta.text
            if req.method == "POST":
                solicitudes.append(req.url)
                if url.path.endswith("/reintentar"):
                    intento = (
                        e["db"]
                        .query(IntentoProcesamiento)
                        .filter_by(id_archv=e["archivo"].id_archv, rsltd="Pendiente")
                        .one()
                    )
                    reprocesos.procesar_reproceso(e["archivo"].id_archv, intento.id_intnt)
            route.fulfill(status=respuesta.status_code, json=respuesta.json())
            return
        route.fulfill(json={"items": [], "total": 0})

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        pagina = browser.new_page(viewport={"width": ancho, "height": 1000})
        pagina.clock.install()
        pagina.add_init_script(
            f"sessionStorage.setItem('pangea_cliente',{json.dumps(str(e['sede'].id_clnt))}); sessionStorage.setItem('pangea_proyecto_v2',{json.dumps(str(e['proyecto'].id_ubccn))});"
        )
        pagina.route("**/*", responder)
        pagina.on("pageerror", lambda error: errores.append(str(error)))
        try:
            pagina.goto(
                f"{base}/cola-ingesta?dispositivo_id={e['equipo'].id_dspstv}&id_cnxn={e['conexion'].id_cnxn}"
            )
            expect(
                pagina.get_by_role("heading", name="Cola de ingesta", exact=True)
            ).to_be_visible()
            pagina.get_by_label("Estado:", exact=True).select_option("Fallido")
            boton = pagina.get_by_role("button", name="Reintentar todos los fallidos", exact=True)
            expect(boton).to_be_visible()
            # El archivo original está en la segunda página por orden estable.
            pagina.get_by_role("button", name="Siguiente", exact=True).click()
            pagina.locator("tbody tr").filter(has_text="H_original.dat").get_by_role(
                "button", name="Ver detalle", exact=True
            ).click()
            detalle = pagina.get_by_role("dialog", name="Detalle del archivo", exact=True)
            expect(detalle).to_contain_text("Mapeo pendiente")
            detalle.get_by_role("button", name="Reintentar", exact=True).click()
            expect(detalle).to_contain_text("Procesado")
            expect(detalle).to_contain_text("Solicitud manual")
            expect(detalle).to_contain_text("1 lectura(s) nueva(s)")
            detalle.screenshot(path=str(tmp_path / f"hu31-detalle-{ancho}.png"))
            detalle.get_by_role("button", name="Cerrar", exact=True).click()
            expect(pagina.get_by_label("Estado:", exact=True)).to_have_value("Fallido")
            expect(pagina.get_by_text("Página 2 de 2", exact=True)).to_be_visible()
            masivo = pagina.get_by_role("button", name="Reintentar todos los fallidos", exact=True)
            masivo.click()
            confirmar = pagina.get_by_role(
                "dialog", name="Confirmar reintento de archivos", exact=True
            )
            expect(
                confirmar.get_by_role("heading", name="Reintentar todos los fallidos", exact=True)
            ).to_be_visible()
            expect(confirmar.locator("strong")).to_have_text("12")
            expect(confirmar).to_contain_text("todas las páginas")
            expect(confirmar).to_contain_text("Solo el equipo seleccionado")
            confirmar.get_by_role("button", name="Cancelar", exact=True).click()
            assert len(solicitudes) == 1
            assert e["db"].query(ArchivoIngesta).filter_by(estd="Fallido").count() == 12
            masivo.click()
            confirmar.get_by_role("button", name="Confirmar reintento", exact=True).click()
            expect(confirmar).to_have_count(0)
            expect(pagina.get_by_text("Página 1 de 1", exact=True)).to_be_visible()
            expect(pagina.get_by_text("No hay archivos en la cola", exact=False)).to_be_visible()
            assert len(solicitudes) == 2
            assert f"id_dspstv={e['equipo'].id_dspstv}" in solicitudes[-1]
            assert (
                "estado=Fallido" in solicitudes[-1]
                and f"id_cnxn={e['conexion'].id_cnxn}" in solicitudes[-1]
            )
            pagina.get_by_label("Estado:", exact=True).select_option("En espera")
            expect(pagina.locator("tbody tr")).to_have_count(10)
            pagina.locator("tbody tr").first.get_by_role(
                "button", name="Ver detalle", exact=True
            ).click()
            expect(detalle).to_contain_text("En espera")
            nombre = detalle.locator("dd").first.inner_text()
            archivo = e["db"].query(ArchivoIngesta).filter_by(nmbr_archv=nombre).one()
            intento = (
                e["db"]
                .query(IntentoProcesamiento)
                .filter_by(id_archv=archivo.id_archv, rsltd="Pendiente")
                .one()
            )
            reprocesos.procesar_reproceso(archivo.id_archv, intento.id_intnt)
            # Fuerza el mismo tick de 30 s que usa producción para refrescar detalle e historial.
            pagina.clock.fast_forward(30_100)
            expect(detalle).to_contain_text("No existe una copia original conservada")
            expect(detalle).to_contain_text("Fallido")
            assert pagina.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert errores == []
        except Exception:
            pagina.screenshot(path=str(tmp_path / f"hu31-error-{ancho}.png"), full_page=True)
            raise
        finally:
            browser.close()
