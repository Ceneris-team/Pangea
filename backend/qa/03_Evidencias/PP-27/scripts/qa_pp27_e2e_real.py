"""QA PP-27 (PP-439): E2E contra la app REAL (API + worker Celery + beat + Vite de dev 78edb10).

Login real del Técnico CENERIS (seed_usuarios_prueba) en Cliente Demo y datos de seed_pp27.py.
Modo «lectura» (no cambia estados): listado, detalle, historial y modal masivo con Cancelar.
Modo «completo»: Reintentar individual, espera al worker real, masivo con confirmación.
Uso (desde backend/, API 127.0.0.1:8000, Vite 127.0.0.1:5180, datos recién sembrados):
    python qa_pp27_e2e_real.py <dir_evidencias> <ancho> <lectura|completo>
Creado por Elliot_QA | Aseguramiento de Calidad.
"""

import json
import os
import re
import sys
import time

from playwright.sync_api import expect, sync_playwright

UI = os.environ.get("PP27_UI", "http://127.0.0.1:5180")
EVID, ANCHO, MODO = sys.argv[1], int(sys.argv[2]), sys.argv[3]
# Valor de prueba del repo (app/scripts/seed_usuarios_prueba.py), leído sin importar la app.
with open(os.path.join(os.getcwd(), "app", "scripts", "seed_usuarios_prueba.py"), encoding="utf-8") as _f:
    PASSWORD_PRUEBA = re.search(r'PASSWORD_PRUEBA\s*=\s*"([^"]+)"', _f.read()).group(1)

resultados = []
os.makedirs(EVID, exist_ok=True)


def caso(cp, que, ok, detalle=""):
    resultados.append({"cp": cp, "que": que, "ok": bool(ok), "detalle": str(detalle)})
    print(f"{'PASA ' if ok else 'FALLA'} {cp} · {que} · {detalle}", flush=True)


def main():
    errores = []
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page(viewport={"width": ANCHO, "height": 1000})
        pag.on("pageerror", lambda e: errores.append(str(e)))

        def foto(nombre):
            pag.screenshot(path=os.path.join(EVID, f"{nombre}-{ANCHO}.png"), full_page=True)

        pag.goto(f"{UI}/login")
        pag.locator("#email").fill("tecnico@pangea-dev.com")
        pag.locator("#password").fill(PASSWORD_PRUEBA)
        pag.locator("button[type=submit]").click()
        pag.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        pag.get_by_role("button", name="Entrar al entorno de Cliente Demo").click()
        pag.wait_for_load_state("networkidle")
        pag.goto(f"{UI}/cola-ingesta")
        pag.wait_for_load_state("networkidle")

        estado = pag.locator("#filtro-estado")
        datalogger = pag.locator("#filtro-datalogger")
        filas = pag.locator("table tbody tr")
        detalle = pag.get_by_role("dialog", name="Detalle del archivo")

        def filtrar(est="", dl=""):
            estado.select_option(est)
            pag.wait_for_load_state("networkidle")
            if dl is not None:
                datalogger.select_option(label=dl) if dl else datalogger.select_option("")
                pag.wait_for_load_state("networkidle")
            time.sleep(0.5)

        def abrir(nombre):
            filas.filter(has_text=nombre).first.click()
            expect(detalle.get_by_text(nombre)).to_be_visible(timeout=8000)
            expect(detalle.get_by_text("Historial de intentos")).to_be_visible()
            pag.wait_for_load_state("networkidle")
            time.sleep(0.5)

        def cerrar():
            detalle.get_by_role("button", name="Cerrar").click()
            expect(detalle).to_be_hidden()

        # Rótulos frente al ticket (DEF de rótulos)
        h1 = pag.locator("h1").inner_text().strip()
        menu = pag.get_by_role("link", name=re.compile("Cola de", re.I)).first.inner_text().strip() if ANCHO > 700 else "(menú colapsado)"
        caso("CP-540", "Título de la pantalla = «Cola de ingesta»", h1.lower() == "cola de ingesta", f"h1='{h1}'; menú='{menu}'")

        # CP-540 · CA-01
        filtrar("Fallido", "")
        n = filas.count()
        cab = [t.strip().lower() for t in pag.locator("table thead th").all_inner_texts()]
        pie = pag.get_by_text(re.compile(r"Página \d+ de \d+")).inner_text()
        motivos = filas.filter(has_text="No hay un formato activo").count()
        foto("EV-CP-540_filtro-fallido")
        caso("CP-540", "Filtro Fallido: 10 por página, columnas y motivo visible",
             n == 10 and pie == "Página 1 de 2" and {"archivo", "datalogger de origen", "fecha de recepción", "estado"} <= set(cab) and motivos >= 9,
             f"filas={n}; pie='{pie}'; cab={cab}; con motivo={motivos}")

        # CP-549 · historial previo (intento automático)
        abrir("H_QA27_F_11.dat")
        hist = detalle.locator("li").all_inner_texts()
        boton = detalle.get_by_role("button", name=re.compile(r"^(Reintentar|Reprocesar)$"))
        rotulo = boton.inner_text().strip() if boton.count() else "(sin botón)"
        foto("EV-CP-549_historial-automatico")
        caso("CP-549", "Historial muestra el intento automático previo con su error",
             len(hist) == 1 and "Automático" in hist[0] and "No hay un formato activo" in hist[0], hist)
        caso("CP-541", "Acción individual rotulada «Reintentar»", rotulo == "Reintentar", f"rótulo='{rotulo}'")

        # CP-543 · modal masivo (cantidad, alcance, Cancelar)
        cerrar()
        filtrar("Fallido", "QA27 Datalogger A")
        masivo = pag.get_by_role("button", name=re.compile(r"(Reintentar todos los fallidos|Reprocesar fallidos del filtro)"))
        rot_masivo = masivo.inner_text().strip()
        masivo.click()
        modal = pag.get_by_role("dialog", name="Confirmar reproceso de archivos")
        texto = modal.inner_text()
        foto("EV-CP-543_confirmacion-masiva")
        caso("CP-543", "Confirmación con cantidad y alcance de todas las páginas",
             "13 archivo" in texto and "todas las páginas" in texto and "QA27 Datalogger A" in texto, texto.replace("\n", " "))
        caso("CP-543", "Acción masiva rotulada «Reintentar todos los fallidos»",
             rot_masivo.startswith("Reintentar todos los fallidos"), f"rótulo='{rot_masivo}'")
        modal.get_by_role("button", name="Cancelar").click()
        expect(modal).to_be_hidden()
        filtrar("Fallido", None)
        sigue = filas.count()
        caso("CP-543", "Cancelar no cambia estados", sigue == 10 and estado.input_value() == "Fallido",
             f"filas Fallido tras cancelar={sigue}")

        if MODO == "completo":
            # CP-541 · Reintentar → En espera
            filtrar("Fallido", "")
            abrir("H_QA27_F_11.dat")
            boton.click()
            expect(detalle.get_by_text("En espera", exact=True).first).to_be_visible(timeout=8000)
            foto("EV-CP-541_en-espera")
            caso("CP-541", "Reintentar registra la solicitud y pasa a «En espera»", True,
                 detalle.locator("li").first.inner_text().replace("\n", " "))
            cerrar()

            # CP-547/548 · worker real → Procesado
            fin = time.time() + 90
            while time.time() < fin:
                filtrar("Procesado", "QA27 Datalogger A")
                if filas.filter(has_text="H_QA27_F_11.dat").count():
                    break
                time.sleep(3)
            abrir("H_QA27_F_11.dat")
            txt = detalle.inner_text()
            foto("EV-CP-548_procesado")
            caso("CP-548", "Procesado con fecha y resumen (registros procesados)",
                 "Procesado" in txt and re.search(r"Registros procesados\s*1", txt) is not None, txt.replace("\n", " ")[:300])
            hist = detalle.locator("li").all_inner_texts()
            caso("CP-549", "Historial: solicitud manual del técnico con inicio y fin, conserva la automática",
                 len(hist) == 2 and "Solicitud manual" in hist[0] and "Inicio:" in hist[0] and "Fin:" in hist[0] and "Automático" in hist[1], hist)
            cerrar()

            # CP-544 · masivo confirmado, filtros conservados
            filtrar("Fallido", "QA27 Datalogger A")
            masivo.click()
            pag.get_by_role("dialog", name="Confirmar reproceso de archivos").get_by_role("button", name=re.compile("Confirmar")).click()
            aviso = pag.get_by_text(re.compile(r"archivo\(s\) en espera de reproceso"))
            expect(aviso).to_be_visible(timeout=8000)
            foto("EV-CP-544_masivo-confirmado")
            caso("CP-544", "Masivo registra los 12 elegibles restantes y conserva filtros",
                 "12 archivo" in aviso.inner_text() and estado.input_value() == "Fallido"
                 and datalogger.locator("option:checked").inner_text() == "QA27 Datalogger A", aviso.inner_text())

            fin = time.time() + 120
            while time.time() < fin:
                filtrar("", "QA27 Datalogger A")
                pend = filas.filter(has_text=re.compile("En espera|Procesando")).count()
                if pend == 0 and pag.get_by_text(re.compile(r"Página 1 de")).count():
                    break
                time.sleep(3)
            filtrar("Fallido", "")
            nombres = [t.split("\n")[0] for t in filas.locator("td:first-child").all_inner_texts()]
            foto("EV-CP-548_lote-fallido-no-bloquea")
            caso("CP-548", "Un fallido no impide el lote; solo quedan MALO, B_00 y el demo",
                 sorted(nombres) == sorted(["H_QA27_MALO.dat", "H_QA27_B_00.dat", "H_20260812_1100.dat"]), nombres)
            abrir("H_QA27_MALO.dat")
            txt = detalle.inner_text()
            foto("EV-CP-545_original-alterado")
            caso("CP-545", "Original alterado: vuelve a Fallido con la causa de integridad",
                 "huella" in txt, txt.replace("\n", " ")[:300])
            cerrar()

        caso("UI", "Sin errores JavaScript", not errores, errores)
        nav.close()
    with open(os.path.join(EVID, f"e2e-{MODO}-{ANCHO}.json"), "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
