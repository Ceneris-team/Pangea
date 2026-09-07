"""
DEC-09 / IMP-06 - Ficha del dispositivo.

Cubre lo que el rediseño movió al dispositivo, y que antes se resolvía por
sede+marca:

  Aislamiento del mapeo   dos dispositivos, MISMA marca y MISMA sede, cada
                          uno con su mapeo: no se mezclan (era el bug que
                          originó DEC-09)
  H y E a la vez          un mismo dispositivo con mapeo H y mapeo E
                          simultáneos; cada archivo cae en el suyo según el
                          prefijo H_/E_ del nombre
  Carga de datos (3c)     sube un .dat y lo procesa por el pipeline real
  Carga manual (3d)       un punto de telemetría sin archivo
  Logs (3e)               archv_ingst filtrado por este dispositivo
  Delimitador decimal     "23,5" se guarda como 23.5 cuando el mapeo lo
                          declara, y no como error de validación

Reusa las factorías de test_dispositivos.py (misma cadena Ubicacion ->
ConexionFTP -> Dispositivo) para no duplicar el armado del escenario.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import LogAuditoria, MapeoFormato
from app.models.archivo_ingesta import ArchivoIngesta
from app.models.mapeo_dispositivo import MapeoColumna, Parametro
from app.models.telemetria import Telemetria
from app.security.dependencies import get_current_user
from app.services.ingesta.mapeo import resolver_formato
from tests.routers.test_dispositivos import (
    agregar_permiso,
    preparar_dispositivo,
    usuario_jwt,
)


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def tecnico(db_session, fabrica):
    """Técnico CENERIS con Edición sobre Dispositivos e Ingesta.

    Las pestañas de la ficha tocan los dos módulos: Dispositivos (la ficha
    y las cargas) e Ingesta (los mapeos, vía /mapeos de HU06)."""
    rol = fabrica.rol("Técnico CENERIS")
    sede = fabrica.sede()
    usuario = fabrica.usuario(rol=rol)
    agregar_permiso(db_session, usuario, sede, "Dispositivos", "Edición", rol)
    agregar_permiso(db_session, usuario, sede, "Ingesta", "Edición", rol)
    app.dependency_overrides[get_current_user] = lambda: usuario_jwt(
        usuario, rol.nmbr, sede_id=sede.id_sd
    )
    return sede, rol


def crear_parametro(db_session, nombre, unidad="u"):
    parametro = Parametro(nmbr=nombre, undd=unidad)
    db_session.add(parametro)
    db_session.flush()
    return parametro


def crear_mapeo_con_columnas(
    db_session,
    dispositivo,
    tp_trm,
    columnas,
    dlmtdr=",",
    dlmtdr_dcml=".",
):
    """mp_frmt + sus mp_clmn. `columnas` es {indice: Parametro}."""
    mapeo = MapeoFormato(
        id_dspstv=dispositivo.id_dspstv,
        tp_trm=tp_trm,
        dlmtdr=dlmtdr,
        dlmtdr_dcml=dlmtdr_dcml,
        fl_inc_dts=1,
        frmt_fch="%Y-%m-%d %H:%M:%S",
        estd="Activo",
    )
    db_session.add(mapeo)
    db_session.flush()
    for indice, parametro in columnas.items():
        db_session.add(
            MapeoColumna(id_mp=mapeo.id_mp, indc_clmn=indice, id_prmtr=parametro.id_prmtr)
        )
    db_session.flush()
    return mapeo


def fecha_en_particion() -> dt.datetime:
    """Un timestamp pasado dentro del mes corriente.

    tlmtr está particionada por rango mensual (HT-08) y el colchón de
    particiones se crea alrededor de hoy, así que una fecha fija del
    calendario haría fallar el test cuando la partición de ese mes ya no
    exista. Se resta una hora para no caer en "timestamp futuro", que el
    validador rechaza."""
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)


def contenido_dat(fecha: dt.datetime, valor: str, columna="Temp") -> str:
    return f"Fecha,{columna}\n" f"{fecha:%Y-%m-%d %H:%M:%S},{valor}\n"


# ---------------------------------------------------------------------------
# El bug que originó DEC-09: misma marca + misma sede, mapeos distintos
# ---------------------------------------------------------------------------


class TestMapeoAisladoPorDispositivo:
    def test_dos_dispositivos_misma_marca_y_sede_no_comparten_mapeo(self, db_session, tecnico):
        """Con el diseño anterior (sede+marca) estos dos dataloggers
        resolvían el MISMO mp_frmt y las lecturas del segundo se guardaban
        bajo el parámetro del primero, sin error visible."""
        sede, _ = tecnico
        temperatura = crear_parametro(db_session, "temperatura", "C")
        ph = crear_parametro(db_session, "ph", "pH")

        uno = preparar_dispositivo(db_session, sede, nombre="CR1000-A", marca="Campbell")
        dos = preparar_dispositivo(db_session, sede, nombre="CR1000-B", marca="Campbell")
        assert uno.mrc == dos.mrc

        crear_mapeo_con_columnas(db_session, uno, "H", {1: temperatura})
        crear_mapeo_con_columnas(db_session, dos, "H", {1: ph})

        formato_uno = resolver_formato(db_session, uno.id_dspstv, "H_lectura.dat")
        formato_dos = resolver_formato(db_session, dos.id_dspstv, "H_lectura.dat")

        assert formato_uno.id_mp != formato_dos.id_mp

        columnas_uno = (
            db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == formato_uno.id_mp).all()
        )
        columnas_dos = (
            db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == formato_dos.id_mp).all()
        )
        assert [c.id_prmtr for c in columnas_uno] == [temperatura.id_prmtr]
        assert [c.id_prmtr for c in columnas_dos] == [ph.id_prmtr]

    def test_un_dispositivo_con_mapeo_h_y_e_aplica_el_del_prefijo(self, db_session, tecnico):
        """El prefijo H_/E_ del nombre del archivo sigue decidiendo el tipo
        de trama; lo que cambió es que el mapeo se busca por dispositivo."""
        sede, _ = tecnico
        temperatura = crear_parametro(db_session, "temperatura", "C")
        estado = crear_parametro(db_session, "estado_gabinete", "bool")

        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-HE")
        mapeo_h = crear_mapeo_con_columnas(db_session, dispositivo, "H", {1: temperatura})
        mapeo_e = crear_mapeo_con_columnas(db_session, dispositivo, "E", {1: estado})

        resuelto_h = resolver_formato(db_session, dispositivo.id_dspstv, "H_datos.dat")
        resuelto_e = resolver_formato(db_session, dispositivo.id_dspstv, "E_eventos.dat")

        assert resuelto_h.id_mp == mapeo_h.id_mp
        assert resuelto_h.tipo_trama == "H"
        assert resuelto_e.id_mp == mapeo_e.id_mp
        assert resuelto_e.tipo_trama == "E"


# ---------------------------------------------------------------------------
# 3c - Carga de datos (.dat subido a mano por el MISMO pipeline)
# ---------------------------------------------------------------------------


class TestCargaArchivo:
    def test_caso_feliz_guarda_en_tlmtr_y_deja_log(self, client, db_session, tecnico):
        sede, _ = tecnico
        temperatura = crear_parametro(db_session, "temperatura", "C")
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-carga")
        crear_mapeo_con_columnas(db_session, dispositivo, "H", {1: temperatura})

        fecha = fecha_en_particion()
        resp = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-archivo",
            files={"archivo": ("H_manual.dat", contenido_dat(fecha, "23.5"), "text/plain")},
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["tipo_trama"] == "H"
        assert body["guardadas"] == 1

        filas = (
            db_session.query(Telemetria).filter(Telemetria.id_dspstv == dispositivo.id_dspstv).all()
        )
        assert len(filas) == 1
        assert float(filas[0].vlr) == pytest.approx(23.5)
        assert filas[0].id_prmtr == temperatura.id_prmtr

        # Queda registrado en archv_ingst para la pestaña Logs.
        log = (
            db_session.query(ArchivoIngesta)
            .filter(ArchivoIngesta.id_archv == body["id_archv"])
            .first()
        )
        assert log is not None
        assert log.estd == "Exitoso"
        assert log.nmbr_archv == "H_manual.dat"

    def test_carga_con_prefijo_nuevo_crea_trama_automatica_y_la_audita(
        self, client, db_session, tecnico
    ):
        """HU49 CA5, regresión de un gap encontrado en la verificación
        funcional: la carga manual de archivo (IMP-06) comparte
        resolver_formato con la ingesta automática por FTP, así que
        también puede disparar la creación automática de una trama -y esa
        creación debe auditarse igual, sin importar el canal de entrada.
        Al principio esto NO auditaba nada porque routers/dispositivos.py
        no marcaba el contexto de auditoría antes de llamar a
        resolver_formato (sí lo hacía tasks/ingesta.py, pero este endpoint
        no pasa por ahí).

        La columna del header SÍ tiene que matchear un parámetro real: si
        el auto-mapeo de HU50 no encuentra ninguna columna mapeable, todo
        el pipeline aborta con ErrorDatosNoRecuperable y la transacción se
        revierte ENTERA (ver el except de abajo en este mismo router) -
        incluida la trama recién creada y su fila de auditoría. Eso es
        correcto (evita un mp_frmt fantasma de un archivo que ni siquiera
        pudo interpretarse), pero significa que la auditoría solo se
        puede observar cuando el archivo SÍ llega a persistir algo."""
        sede, _ = tecnico
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-prefijo-nuevo")
        temperatura = crear_parametro(db_session, "temperatura", "C")

        fecha = fecha_en_particion()
        resp = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-archivo",
            files={
                "archivo": (
                    "NUEVOCA_datos.dat",
                    contenido_dat(fecha, "23.5", columna=temperatura.nmbr),
                    "text/plain",
                )
            },
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["guardadas"] == 1

        formato = (
            db_session.query(MapeoFormato)
            .filter(
                MapeoFormato.id_dspstv == dispositivo.id_dspstv,
                MapeoFormato.tp_trm == "NUEVOCA",
            )
            .first()
        )
        assert formato is not None
        assert formato.orgn_crcn == "Automatico"

        auditoria = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"mapeo_formato:{formato.id_mp}")
            .first()
        )
        assert auditoria is not None
        assert auditoria.accn == "crear_trama_automatica"

    def test_trama_nueva_con_columna_desconocida_autocrea_parametro_y_guarda(
        self, client, db_session, tecnico
    ):
        """HU49 + HU50 + HU51 end-to-end por HTTP: el dispositivo tiene
        mapeo H pero llega un E_ nunca visto.

        Antes de HU49 esto era un 422 de "trama no reconocida"; entre
        HU49 y HU50 pasó a ser un 422 de "ninguna columna mapeada"
        -la trama se creaba sola pero el archivo igual se perdía-.
        Con HU51 la carga YA NO FALLA: la columna desconocida ('Temp')
        genera un parámetro nuevo en 'Pendiente de revision' y su dato se
        guarda desde este primer archivo (CA1-CA2)."""
        sede, _ = tecnico
        temperatura = crear_parametro(db_session, "temperatura", "C")
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-soloH")
        crear_mapeo_con_columnas(db_session, dispositivo, "H", {1: temperatura})

        fecha = fecha_en_particion()
        resp = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-archivo",
            files={"archivo": ("E_eventos.dat", contenido_dat(fecha, "1"), "text/plain")},
        )

        assert resp.status_code == 201, resp.text
        # CA2: el dato de la columna desconocida se guardó en esta misma
        # carga, no quedó pendiente ni se perdió.
        assert resp.json()["guardadas"] == 1

        # HU51 CA1: se auto-creó el parámetro para la columna 'Temp'.
        from app.models import Parametro

        auto_creado = db_session.query(Parametro).filter(Parametro.nmbr == "Temp").one()
        assert auto_creado.estd == "Pendiente de revision"
        assert auto_creado.orgn_crcn == "Automatico"
        # El valor "1" es numérico, así que pudo inferirse bien el tipo.
        assert auto_creado.tipo_dato == "numerico"

    def test_nombre_sin_prefijo_conocido_devuelve_422(self, client, db_session, tecnico):
        sede, _ = tecnico
        temperatura = crear_parametro(db_session, "temperatura", "C")
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-sinprefijo")
        crear_mapeo_con_columnas(db_session, dispositivo, "H", {1: temperatura})

        resp = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-archivo",
            files={
                "archivo": (
                    "lectura.dat",
                    contenido_dat(fecha_en_particion(), "1"),
                    "text/plain",
                )
            },
        )
        assert resp.status_code == 422
        assert "prefijo" in resp.json()["detail"]

    def test_respeta_el_delimitador_decimal_del_mapeo(self, client, db_session, tecnico):
        """Con dlmtdr_dcml=',' el valor "23,5" es un número, no un error.
        El delimitador de columna se cambia a ';' para que la coma no parta
        la fila en dos campos."""
        sede, _ = tecnico
        temperatura = crear_parametro(db_session, "temperatura", "C")
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-europeo")
        crear_mapeo_con_columnas(
            db_session,
            dispositivo,
            "H",
            {1: temperatura},
            dlmtdr=";",
            dlmtdr_dcml=",",
        )

        fecha = fecha_en_particion()
        contenido = f"Fecha;Temp\n{fecha:%Y-%m-%d %H:%M:%S};23,5\n"
        resp = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-archivo",
            files={"archivo": ("H_eu.dat", contenido, "text/plain")},
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["guardadas"] == 1
        fila = (
            db_session.query(Telemetria)
            .filter(Telemetria.id_dspstv == dispositivo.id_dspstv)
            .first()
        )
        assert float(fila.vlr) == pytest.approx(23.5)


# ---------------------------------------------------------------------------
# 3d - Carga manual (sin archivo)
# ---------------------------------------------------------------------------


class TestCargaManual:
    def test_caso_feliz_guarda_el_punto(self, client, db_session, tecnico):
        sede, _ = tecnico
        temperatura = crear_parametro(db_session, "temperatura", "C")
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-manual")
        crear_mapeo_con_columnas(db_session, dispositivo, "H", {1: temperatura})

        fecha = fecha_en_particion()
        resp = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-manual",
            json={
                "fch_hr": fecha.isoformat(),
                "valores": [{"id_prmtr": temperatura.id_prmtr, "vlr": 19.25}],
            },
        )

        assert resp.status_code == 201, resp.text
        fila = (
            db_session.query(Telemetria)
            .filter(Telemetria.id_dspstv == dispositivo.id_dspstv)
            .first()
        )
        assert fila is not None
        assert float(fila.vlr) == pytest.approx(19.25)
        # Sin archivo de origen: la carga manual no inventa una fila en
        # archv_ingst.
        assert fila.id_archv is None
        assert db_session.query(ArchivoIngesta).count() == 0

    def test_parametro_no_mapeado_devuelve_422(self, client, db_session, tecnico):
        sede, _ = tecnico
        temperatura = crear_parametro(db_session, "temperatura", "C")
        ajeno = crear_parametro(db_session, "conductividad", "uS/cm")
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-ajeno")
        crear_mapeo_con_columnas(db_session, dispositivo, "H", {1: temperatura})

        resp = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-manual",
            json={
                "fch_hr": fecha_en_particion().isoformat(),
                "valores": [{"id_prmtr": ajeno.id_prmtr, "vlr": 1.0}],
            },
        )

        assert resp.status_code == 422
        assert "no están mapeados" in resp.json()["detail"]
        assert db_session.query(Telemetria).count() == 0

    def test_sin_mapeo_h_devuelve_422(self, client, db_session, tecnico):
        """Un dispositivo con solo mapeo E no admite carga manual: la
        captura a mano es de datos periódicos."""
        sede, _ = tecnico
        estado = crear_parametro(db_session, "estado_gabinete", "bool")
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-soloE")
        crear_mapeo_con_columnas(db_session, dispositivo, "E", {1: estado})

        resp = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-manual",
            json={
                "fch_hr": fecha_en_particion().isoformat(),
                "valores": [{"id_prmtr": estado.id_prmtr, "vlr": 1.0}],
            },
        )
        assert resp.status_code == 422
        assert "datos periódicos" in resp.json()["detail"]

    def test_fecha_futura_devuelve_422(self, client, db_session, tecnico):
        sede, _ = tecnico
        temperatura = crear_parametro(db_session, "temperatura", "C")
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-futuro")
        crear_mapeo_con_columnas(db_session, dispositivo, "H", {1: temperatura})

        futuro = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
        resp = client.post(
            f"/dispositivos/{dispositivo.id_dspstv}/carga-manual",
            json={
                "fch_hr": futuro.isoformat(),
                "valores": [{"id_prmtr": temperatura.id_prmtr, "vlr": 1.0}],
            },
        )
        assert resp.status_code == 422
        assert "futura" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 3e - Logs y cabecera de la ficha
# ---------------------------------------------------------------------------


class TestFichaYLogs:
    def test_detalle_expone_la_frecuencia_de_polling_como_referencia(
        self, client, db_session, tecnico
    ):
        sede, _ = tecnico
        dispositivo = preparar_dispositivo(db_session, sede, nombre="CR1000-ficha")

        resp = client.get(f"/dispositivos/{dispositivo.id_dspstv}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["nmbr"] == "CR1000-ficha"
        assert body["id_sd"] == sede.id_sd
        # Viene de la Conexión FTP (HU05), no de una copia en el dispositivo.
        assert body["conexion_frcnc_mnts"] == 1

    def test_logs_solo_trae_los_de_este_dispositivo(self, client, db_session, tecnico):
        sede, _ = tecnico
        uno = preparar_dispositivo(db_session, sede, nombre="CR1000-log-A")
        dos = preparar_dispositivo(db_session, sede, nombre="CR1000-log-B")

        db_session.add(ArchivoIngesta(id_cnxn=uno.id_cnxn, nmbr_archv="H_de_A.dat"))
        db_session.add(ArchivoIngesta(id_cnxn=dos.id_cnxn, nmbr_archv="H_de_B.dat"))
        db_session.flush()

        resp = client.get(f"/dispositivos/{uno.id_dspstv}/logs")
        assert resp.status_code == 200
        nombres = [fila["nmbr_archv"] for fila in resp.json()]
        assert nombres == ["H_de_A.dat"]

    def test_dispositivo_inexistente_devuelve_404(self, client, db_session, tecnico):
        resp = client.get("/dispositivos/999999")
        assert resp.status_code == 404
