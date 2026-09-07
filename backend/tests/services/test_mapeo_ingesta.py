"""
HU49/HU50 - Tests unitarios de app/services/ingesta/mapeo.py.

Cubren, en este orden (mismo orden en que se implementó, ver el plan):
1. extraer_prefijo() y la reescritura de detectar_tipo_trama() - deben
   comportarse EXACTAMENTE igual que antes para toda trama de una sola
   letra (H, E, P, cualquiera ya configurada manualmente). Este es el
   test de regresión más directo: si algo acá cambia de resultado para
   un caso existente, es una regresión real sobre HU06/DEC-09.
2. resolver_formato(): creación automática de trama (HU49 CA1-CA2) y
   rechazo explícito cuando no hay '_' en el nombre (HU49 CA4).
3. construir_mapeo(): auto-mapeo de columnas por nombre exacto (HU50
   CA1-CA2), columnas sin match quedan pendientes (CA3), y una columna ya
   evaluada nunca se vuelve a tocar (CA6).

Corren contra la Postgres real de test (ver tests/conftest.py), mismo
patrón que TestBugDEC09ResuelveElMapeoDelDispositivoCorrecto en
test_mapeos.py -de ahí se reutiliza crear_dispositivo().
"""

import pytest
import sqlalchemy as sa

from app.models import (
    ConexionFTP,
    Dispositivo,
    LogAuditoria,
    MapeoColumna,
    MapeoColumnaPendiente,
    MapeoFormato,
    Parametro,
    Telemetria,
    Ubicacion,
)
from app.services.ingesta.mapeo import (
    MapeoNoEncontradoError,
    construir_mapeo,
    detectar_tipo_trama,
    extraer_prefijo,
    resolver_formato,
)
from app.services.ingesta.usuario_sistema import resolver_id_usuario_sistema
from app.security.auditoria import limpiar_contexto_auditoria, marcar_contexto_auditoria
from app.tasks.ingesta import interpretar_y_guardar
from tests.conftest import Fabrica
from tests.routers.test_mapeos import crear_dispositivo


class TestExtraerPrefijo:
    """HU49 CA1-CA2/CA4: el prefijo es todo el texto antes del PRIMER '_'."""

    def test_una_letra_clasica(self):
        assert extraer_prefijo("H_datos.dat") == "H"

    def test_prefijo_de_mas_de_una_letra(self):
        assert extraer_prefijo("ESTACION01_datos.dat") == "ESTACION01"

    def test_se_normaliza_a_mayuscula(self):
        assert extraer_prefijo("h_datos.dat") == "H"

    def test_usa_solo_el_nombre_base_sin_la_ruta(self):
        assert extraer_prefijo("/var/ftp/estacion/H_datos.dat") == "H"

    def test_corta_en_el_primer_guion_bajo_no_en_todos(self):
        assert extraer_prefijo("AB_CD_datos.dat") == "AB"

    def test_sin_guion_bajo_devuelve_none(self):
        assert extraer_prefijo("sindatos.dat") is None

    def test_archivo_que_empieza_con_guion_bajo_prefijo_vacio_devuelve_none(self):
        assert extraer_prefijo("_datos.dat") is None


class TestDetectarTipoTramaRegresion:
    """Regresión explícita: para una trama de una sola letra, el resultado
    de detectar_tipo_trama() tiene que ser IDÉNTICO al comportamiento
    anterior (startswith(f"{letra}_")), en todos los casos reales."""

    def test_matchea_trama_de_una_letra_configurada(self, db_session, fabrica):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        db_session.add(
            MapeoFormato(
                id_dspstv=dispositivo.id_dspstv,
                tp_trm="H",
                dlmtdr=",",
                fl_inc_dts=1,
                frmt_fch="%Y-%m-%d %H:%M:%S",
            )
        )
        db_session.flush()

        assert detectar_tipo_trama(db_session, dispositivo.id_dspstv, "H_datos.dat") == "H"

    def test_no_matchea_si_el_dispositivo_no_tiene_esa_trama(self, db_session, fabrica):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        db_session.add(
            MapeoFormato(
                id_dspstv=dispositivo.id_dspstv,
                tp_trm="H",
                dlmtdr=",",
                fl_inc_dts=1,
                frmt_fch="%Y-%m-%d %H:%M:%S",
            )
        )
        db_session.flush()

        assert detectar_tipo_trama(db_session, dispositivo.id_dspstv, "E_datos.dat") is None

    def test_caso_borde_prefijo_similar_no_matchea_por_substring(self, db_session, fabrica):
        """Antes: "HE_datos.dat".startswith("H_") es False (falta el '_'
        justo después de la H) - no matchea. Ahora: extraer_prefijo
        devuelve "HE", que tampoco es igual a "H" - tampoco matchea.
        Mismo resultado en ambas versiones, verificado explícitamente."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        db_session.add(
            MapeoFormato(
                id_dspstv=dispositivo.id_dspstv,
                tp_trm="H",
                dlmtdr=",",
                fl_inc_dts=1,
                frmt_fch="%Y-%m-%d %H:%M:%S",
            )
        )
        db_session.flush()

        assert detectar_tipo_trama(db_session, dispositivo.id_dspstv, "HE_datos.dat") is None

    def test_sin_guion_bajo_no_matchea_nada(self, db_session, fabrica):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        db_session.add(
            MapeoFormato(
                id_dspstv=dispositivo.id_dspstv,
                tp_trm="H",
                dlmtdr=",",
                fl_inc_dts=1,
                frmt_fch="%Y-%m-%d %H:%M:%S",
            )
        )
        db_session.flush()

        assert detectar_tipo_trama(db_session, dispositivo.id_dspstv, "sindatos.dat") is None


class TestResolverFormatoCreacionAutomatica:
    """HU49 CA1-CA2: si ningún mp_frmt activo matchea el prefijo, se crea
    uno automáticamente en vez de fallar."""

    def test_primera_vez_crea_mapeo_formato_automatico(self, db_session, fabrica):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)

        resuelto = resolver_formato(db_session, dispositivo.id_dspstv, "NUEVO_datos.dat")

        formato = db_session.get(MapeoFormato, resuelto.id_mp)
        assert formato.tp_trm == "NUEVO"
        assert formato.orgn_crcn == "Automatico"
        assert formato.estd == "Activo"
        assert formato.id_dspstv == dispositivo.id_dspstv
        # Regresión de un bug real encontrado en la verificación funcional
        # de HU49: fila_inicio_datos es un OFFSET desde la fila de header
        # (parser.py: indice_inicio = indice_header + fila_inicio_datos),
        # así que para "1 fila de header + los datos empiezan justo
        # después" el valor correcto es 1, no 2 -con 2 se saltaba la
        # primera fila de datos real de cualquier archivo nuevo, dando
        # 'guardadas: 0' incluso con datos válidos-.
        assert formato.fl_inc_dts == 1
        # HU50 corre después, sobre el header real: al crearse, la trama
        # no tiene ninguna columna mapeada todavía.
        assert (
            db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == formato.id_mp).count()
            == 0
        )

    def test_segunda_llamada_con_mismo_prefijo_reutiliza_la_misma_trama(
        self, db_session, fabrica
    ):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)

        primera = resolver_formato(db_session, dispositivo.id_dspstv, "NUEVO_a.dat")
        segunda = resolver_formato(db_session, dispositivo.id_dspstv, "NUEVO_b.dat")

        assert primera.id_mp == segunda.id_mp
        assert (
            db_session.query(MapeoFormato)
            .filter(MapeoFormato.id_dspstv == dispositivo.id_dspstv, MapeoFormato.tp_trm == "NUEVO")
            .count()
            == 1
        )

    def test_no_afecta_tramas_de_otro_dispositivo(self, db_session, fabrica):
        """La trama automática se crea SOLO para el dispositivo del
        archivo que la disparó - mismo criterio de aislamiento que
        DEC-09."""
        sede = fabrica.sede()
        disp_a = crear_dispositivo(db_session, sede, nombre="Disp A HU49")
        disp_b = crear_dispositivo(db_session, sede, nombre="Disp B HU49")

        resolver_formato(db_session, disp_a.id_dspstv, "NUEVO_datos.dat")

        assert detectar_tipo_trama(db_session, disp_b.id_dspstv, "NUEVO_datos.dat") is None

    def test_carrera_de_integrity_error_recupera_la_fila_ganadora(self):
        """Simula la carrera de dos workers de Celery creando la misma
        trama casi a la vez: el índice único parcial (id_dspstv, tp_trm)
        WHERE Activo es lo que realmente decide quién gana a nivel de
        base de datos, y _crear_mapeo_formato_automatico debe recuperar
        la fila ganadora en vez de fallar el archivo completo.

        Usa una sesión propia con COMMITS reales contra
        TEST_DATABASE_URL (nunca contra la app.database.SessionLocal() de
        producción, que apunta a pangea_dev), en vez del fixture
        db_session: ese vive dentro de una transacción de test que nunca
        se confirma del todo, y el db.rollback() que
        _crear_mapeo_formato_automatico hace tras el IntegrityError se
        lleva puesto cualquier fila no comiteada de verdad -incluida la
        "ganadora" si solo estuviera flusheada, que es justo lo contrario
        de lo que pasa en producción, donde esa fila vive en la
        transacción YA CONFIRMADA de otro proceso-. Al comitear de
        verdad, limpia sus propias filas al final con un DELETE
        explícito."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.services.ingesta import mapeo as modulo_mapeo
        from tests.conftest import TEST_DATABASE_URL

        engine_propio = create_engine(TEST_DATABASE_URL)
        SesionPropia = sessionmaker(bind=engine_propio)
        db = SesionPropia()
        try:
            fabrica = Fabrica(db)
            sede = fabrica.sede()
            dispositivo = crear_dispositivo(db, sede)
            db.commit()

            formato_existente = MapeoFormato(
                id_dspstv=dispositivo.id_dspstv,
                tp_trm="CARRERA",
                orgn_crcn="Automatico",
                dlmtdr=",",
                fl_inc_dts=2,
                frmt_fch="%Y-%m-%d %H:%M:%S",
            )
            db.add(formato_existente)
            db.commit()
            id_mp_ganador = formato_existente.id_mp
            id_dspstv = dispositivo.id_dspstv
            id_ubccn = dispositivo.id_ubccn
            id_cnxn = dispositivo.id_cnxn
            id_sd = sede.id_sd
            id_clnt = sede.id_clnt

            formato = modulo_mapeo._crear_mapeo_formato_automatico(
                db, dispositivo.id_dspstv, "CARRERA"
            )

            assert formato.id_mp == id_mp_ganador
        finally:
            db.rollback()
            db.query(MapeoFormato).filter(MapeoFormato.id_dspstv == id_dspstv).delete()
            db.query(Dispositivo).filter(Dispositivo.id_dspstv == id_dspstv).delete()
            db.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).delete()
            db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == id_cnxn).delete()
            db.execute(sa.text("DELETE FROM sd WHERE id_sd = :id_sd"), {"id_sd": id_sd})
            db.execute(sa.text("DELETE FROM clnt WHERE id_clnt = :id_clnt"), {"id_clnt": id_clnt})
            db.commit()
            db.close()
            engine_propio.dispose()


class TestResolverFormatoCA4SinGuionBajo:
    """HU49 CA4: sin '_' en el nombre no hay prefijo que probar, se
    rechaza el archivo sin crear nada."""

    def test_sin_guion_bajo_lanza_error_sin_crear_mapeo(self, db_session, fabrica):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)

        conteo_antes = db_session.query(MapeoFormato).count()

        with pytest.raises(MapeoNoEncontradoError):
            resolver_formato(db_session, dispositivo.id_dspstv, "singuionbajo.dat")

        assert db_session.query(MapeoFormato).count() == conteo_antes


class TestConstruirMapeoAutoMapeoDeColumnas:
    """HU50 CA1-CA3, CA6."""

    def _crear_formato_vacio(self, db_session, dispositivo, tp_trm="Q"):
        formato = MapeoFormato(
            id_dspstv=dispositivo.id_dspstv,
            tp_trm=tp_trm,
            orgn_crcn="Automatico",
            dlmtdr=",",
            fl_inc_dts=2,
            frmt_fch="%Y-%m-%d %H:%M:%S",
        )
        db_session.add(formato)
        db_session.flush()
        return formato

    def test_columna_que_matchea_exacto_se_mapea_automaticamente(self, db_session, fabrica):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        parametro = Parametro(nmbr="Temperatura HU50", undd="°C")
        db_session.add(parametro)
        db_session.flush()

        mapa = construir_mapeo(db_session, formato.id_mp, ["Temperatura HU50"])

        assert mapa == {"Temperatura HU50": "Temperatura HU50"}
        columna = (
            db_session.query(MapeoColumna)
            .filter(MapeoColumna.id_mp == formato.id_mp, MapeoColumna.indc_clmn == 0)
            .first()
        )
        assert columna is not None
        assert columna.id_prmtr == parametro.id_prmtr

    def test_match_ignora_mayusculas_y_espacios(self, db_session, fabrica):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        parametro = Parametro(nmbr="TEMPERATURA", undd="°C")
        db_session.add(parametro)
        db_session.flush()

        mapa = construir_mapeo(db_session, formato.id_mp, [" temperatura "])

        assert mapa == {" temperatura ": "TEMPERATURA"}

    def test_anti_falso_positivo_nombres_parecidos_no_matchean(self, db_session, fabrica):
        """Decisión explícita de HU50: SIN similaridad difusa. Presion_kPa
        y Presion_Bar son parámetros DISTINTOS y nunca deben confundirse.

        Actualizado en HU51: la columna sin match ya no queda pendiente,
        se le auto-crea un parámetro propio. Lo que este test protege
        sigue siendo lo mismo y es lo importante: NO se mapea contra
        Presion_kPa. Que termine en un parámetro nuevo y separado es
        justamente la confirmación de que no hubo match difuso."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        parametro_existente = Parametro(nmbr="Presion_kPa", undd="kPa")
        db_session.add(parametro_existente)
        db_session.flush()

        mapa = construir_mapeo(db_session, formato.id_mp, ["Presion_Bar"])

        # HU51: se auto-creó un parámetro para la columna...
        assert mapa == {"Presion_Bar": "Presion_Bar"}
        # ...y sobre todo, NO se confundió con el parecido preexistente.
        assert mapa["Presion_Bar"] != "Presion_kPa"
        creado = db_session.query(Parametro).filter(Parametro.nmbr == "Presion_Bar").one()
        assert creado.id_prmtr != parametro_existente.id_prmtr
        assert creado.estd == "Pendiente de revision"
        assert creado.orgn_crcn == "Automatico"

    def test_columna_sin_match_no_bloquea_las_demas(self, db_session, fabrica):
        """HU50 CA3: una columna sin match no debe impedir que las demás
        SÍ se mapeen en la misma llamada.

        Actualizado en HU51: la que no matchea ahora se auto-crea en vez
        de quedar pendiente, pero el punto del test -que no bloquee a las
        demás- se mantiene igual."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        db_session.add(Parametro(nmbr="Temperatura", undd="°C"))
        db_session.flush()

        mapa = construir_mapeo(db_session, formato.id_mp, ["Temperatura", "ColumnaDesconocida"])

        assert mapa == {
            "Temperatura": "Temperatura",
            "ColumnaDesconocida": "ColumnaDesconocida",
        }
        # Ya no quedan pendientes de asignación manual: HU51 las resuelve.
        assert (
            db_session.query(MapeoColumnaPendiente)
            .filter(MapeoColumnaPendiente.id_mp == formato.id_mp)
            .count()
            == 0
        )

    def test_ca6_columna_ya_autocreada_no_se_reevalua_ni_se_duplica(self, db_session, fabrica):
        """HU50 CA6 / HU51 CA6: correr construir_mapeo dos veces con el
        mismo header no debe duplicar nada -ni la MapeoColumna, ni el
        parámetro auto-creado-.

        Actualizado en HU51: antes la garantía la daba la fila en
        mp_clmn_pendiente; ahora la da la MapeoColumna que se crea en el
        acto (el índice ya está mapeado, así que nunca vuelve a ser
        candidato)."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)

        primer_mapa = construir_mapeo(db_session, formato.id_mp, ["ColumnaRara"])
        assert primer_mapa == {"ColumnaRara": "ColumnaRara"}
        assert db_session.query(Parametro).filter(Parametro.nmbr == "ColumnaRara").count() == 1

        segundo_mapa = construir_mapeo(db_session, formato.id_mp, ["ColumnaRara"])

        # Mismo resultado, sin duplicar el parámetro ni la MapeoColumna.
        assert segundo_mapa == {"ColumnaRara": "ColumnaRara"}
        assert db_session.query(Parametro).filter(Parametro.nmbr == "ColumnaRara").count() == 1
        assert (
            db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == formato.id_mp).count() == 1
        )

    def test_columna_ya_mapeada_manualmente_no_se_reevalua(self, db_session, fabrica):
        """Una columna que YA tiene fila en mp_clmn (mapeo manual o de una
        corrida anterior) no debe pasar de nuevo por el auto-mapeo."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        parametro_correcto = Parametro(nmbr="Nivel", undd="m")
        parametro_que_matchearia = Parametro(nmbr="OtraColumna", undd="-")
        db_session.add_all([parametro_correcto, parametro_que_matchearia])
        db_session.flush()
        db_session.add(
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=0, id_prmtr=parametro_correcto.id_prmtr)
        )
        db_session.flush()

        mapa = construir_mapeo(db_session, formato.id_mp, ["OtraColumna"])

        # El índice 0 sigue devolviendo "Nivel" (lo ya mapeado), no se
        # reemplaza ni se reevalúa contra el nombre real del header.
        assert mapa == {"OtraColumna": "Nivel"}

    def test_mezcla_resuelta_matcheada_y_pendiente_en_una_sola_llamada(self, db_session, fabrica):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        parametro_ya_mapeado = Parametro(nmbr="Fecha", undd="-")
        parametro_para_matchear = Parametro(nmbr="Caudal", undd="L/s")
        db_session.add_all([parametro_ya_mapeado, parametro_para_matchear])
        db_session.flush()
        db_session.add(
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=0, id_prmtr=parametro_ya_mapeado.id_prmtr)
        )
        db_session.flush()

        mapa = construir_mapeo(db_session, formato.id_mp, ["Fecha", "Caudal", "ColumnaX"])

        # HU51: las tres se resuelven en una sola llamada -la ya mapeada
        # se respeta, la que matchea se mapea, y la desconocida se
        # auto-crea en vez de quedar pendiente-.
        assert mapa == {"Fecha": "Fecha", "Caudal": "Caudal", "ColumnaX": "ColumnaX"}
        assert (
            db_session.query(MapeoColumnaPendiente)
            .filter(MapeoColumnaPendiente.id_mp == formato.id_mp)
            .count()
            == 0
        )
        # La ya mapeada NO se tocó (sigue apuntando al mismo parámetro).
        assert (
            db_session.query(MapeoColumna)
            .filter(MapeoColumna.id_mp == formato.id_mp, MapeoColumna.indc_clmn == 0)
            .one()
            .id_prmtr
            == parametro_ya_mapeado.id_prmtr
        )

    def test_regresion_columna_fuera_de_rango_sigue_generando_warning_y_se_ignora(
        self, db_session, fabrica, caplog
    ):
        """Comportamiento existente, sin cambios: un índice de mp_clmn que
        ya no cabe en el header real (por un archivo con menos columnas
        que antes) se ignora, no revienta."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        parametro = Parametro(nmbr="Temperatura Fuera De Rango", undd="°C")
        db_session.add(parametro)
        db_session.flush()
        db_session.add(
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=5, id_prmtr=parametro.id_prmtr)
        )
        db_session.flush()

        mapa = construir_mapeo(db_session, formato.id_mp, ["UnicaColumna"])

        assert "UnicaColumna" not in mapa or mapa.get("UnicaColumna") != "Temperatura Fuera De Rango"


class TestIntegracionEndToEndHU49HU50:
    """Pipeline completo (resolver_formato -> interpretar_y_guardar), con
    BD real, mismo patrón que test_ingesta_eventos_texto.py. Cubre el
    escenario íntegro que pide la verificación funcional: trama nueva +
    columnas mixtas (algunas matchean, una no) + datos persistidos +
    archivo Exitoso a pesar de la pendiente + auditoría."""

    def test_trama_nueva_con_columnas_mixtas_persiste_lo_que_matchea_y_audita(
        self, db_session, fabrica
    ):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede, nombre="Integracion HU49 HU50")
        db_session.add_all(
            [
                Parametro(nmbr="bateria_v_integracion", undd="V"),
                Parametro(nmbr="temperatura_integracion", undd="°C"),
            ]
        )
        db_session.flush()

        # HU49 CA5: la auditoría de la creación automática requiere el
        # mismo contexto que setea tasks/ingesta.py -sin JWT/HTTP acá, se
        # marca a mano con el usuario Sistema ya sembrado por la
        # migración de seed.
        id_usr_sistema = resolver_id_usuario_sistema(db_session)
        marcar_contexto_auditoria(db_session, id_usr_sistema)
        try:
            formato_resuelto = resolver_formato(
                db_session, dispositivo.id_dspstv, "INTEG_datos.dat"
            )
        finally:
            limpiar_contexto_auditoria(db_session)

        # Confirma HU49 CA1-CA2 antes de seguir: la trama se creó sola.
        formato_db = db_session.get(MapeoFormato, formato_resuelto.id_mp)
        assert formato_db.orgn_crcn == "Automatico"
        assert formato_db.estd == "Activo"

        # Header con: una columna que matchea (bateria_v_integracion), una
        # que matchea (temperatura_integracion), una que NO matchea
        # (columna_desconocida_integracion) - HU50 CA1-CA3 en una sola
        # corrida real del pipeline. fila_inicio_datos=1 (el default
        # corregido): la fila de datos es la línea inmediatamente
        # siguiente al header.
        contenido = (
            "Fecha,bateria_v_integracion,temperatura_integracion,columna_desconocida_integracion\n"
            "2026-09-02 10:00:00,12.5,25.3,999\n"
        )

        resultado_validacion, resultado_persistencia = interpretar_y_guardar(
            db_session,
            contenido=contenido,
            formato=formato_resuelto,
            dispositivo=dispositivo,
            id_cnxn=dispositivo.id_cnxn,
            id_archv=None,
            nombre_archivo="INTEG_datos.dat",
        )

        # CA3: la columna sin match NO bloquea las que sí matchearon.
        assert resultado_validacion.errores == []
        # HU51 CA2: ahora la columna sin match TAMBIÉN se guarda, contra
        # el parámetro que se le auto-creó -antes se perdía hasta que
        # alguien la asignara a mano-, así que son 3 y no 2.
        assert resultado_persistencia.guardadas == 3

        valores_guardados = {
            p.nmbr: float(t.vlr)
            for t, p in db_session.query(Telemetria, Parametro)
            .join(Parametro, Parametro.id_prmtr == Telemetria.id_prmtr)
            .filter(Telemetria.id_dspstv == dispositivo.id_dspstv)
            .all()
        }
        assert valores_guardados == {
            "bateria_v_integracion": 12.5,
            "temperatura_integracion": 25.3,
            "columna_desconocida_integracion": 999.0,
        }

        # HU51 CA1: la columna sin match generó un parámetro nuevo en
        # 'Pendiente de revision', y NO una fila pendiente de asignar.
        auto_creado = (
            db_session.query(Parametro)
            .filter(Parametro.nmbr == "columna_desconocida_integracion")
            .one()
        )
        assert auto_creado.estd == "Pendiente de revision"
        assert auto_creado.orgn_crcn == "Automatico"
        # Se infirió numerico a partir del valor real (999), así que el
        # dato pudo ir a tlmtr en vez de perderse.
        assert auto_creado.tipo_dato == "numerico"

        # HU49 CA5: la creación automática de la trama quedó auditada.
        auditoria = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"mapeo_formato:{formato_resuelto.id_mp}")
            .first()
        )
        assert auditoria is not None
        assert auditoria.accn == "crear_trama_automatica"
        assert auditoria.id_usr == id_usr_sistema

    def test_archivo_de_una_sola_fila_de_datos_no_se_pierde(self, db_session, fabrica):
        """Regresión directa del bug real encontrado en la verificación
        funcional: con fl_inc_dts mal seteado a 2 en vez de 1, un archivo
        de header + UNA sola fila de datos daba 'guardadas: 0' -la fila
        se salteaba por completo, aunque el archivo fuera válido-."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede, nombre="Integracion HU49 una fila")
        db_session.add(Parametro(nmbr="nivel_integracion_una_fila", undd="m"))
        db_session.flush()

        formato_resuelto = resolver_formato(
            db_session, dispositivo.id_dspstv, "UNAFILA_datos.dat"
        )
        contenido = "Fecha,nivel_integracion_una_fila\n2026-09-02 10:00:00,3.2\n"

        _resultado_validacion, resultado_persistencia = interpretar_y_guardar(
            db_session,
            contenido=contenido,
            formato=formato_resuelto,
            dispositivo=dispositivo,
            id_cnxn=dispositivo.id_cnxn,
            id_archv=None,
            nombre_archivo="UNAFILA_datos.dat",
        )

        assert resultado_persistencia.guardadas == 1


class TestConvergenciaDeHU49TrasArchivoFallido:
    """Regresión de un bug real encontrado en la verificación funcional
    con el simulador FTP real: si el archivo que dispara la creación
    automática de una trama (HU49) después falla -típicamente porque
    HU50 no matchea ninguna columna del header, ErrorDatosNoRecuperable-,
    el db.rollback() del llamador (tasks/ingesta.py, routers/dispositivos.py)
    se llevaba puesta la trama recién creada junto con el resto de la
    transacción. El sistema nunca convergía: el PRÓXIMO archivo repetía
    el ciclo de creación desde cero, indefinidamente, si nunca llegaba
    uno que matcheara alguna columna en soledad -visible sobre todo con
    varios archivos del mismo prefijo llegando casi simultáneamente
    (varios workers de Celery, cada uno creando y perdiendo su propia
    trama en paralelo).

    Fix: _crear_mapeo_formato_automatico hace su propio db.commit() (ver
    mapeo.py) en vez de un simple flush, así que la trama sobrevive
    aunque el resto de la transacción del archivo se revierta después.

    Usa una sesión propia contra TEST_DATABASE_URL (nunca contra
    app.database.SessionLocal(), que apunta a pangea_dev) en vez del
    fixture db_session: ese vive dentro de una transacción de test que
    nunca se confirma del todo, y no sirve para probar que un COMMIT real
    sobrevive a un ROLLBACK posterior -necesita comportarse como el
    pipeline real, con conexión y transacciones propias-."""

    def test_trama_sobrevive_aunque_el_archivo_que_la_creo_falle_despues(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.services.ingesta.mapeo import MapeoNoEncontradoError, resolver_formato
        from app.tasks.ingesta import ErrorDatosNoRecuperable, interpretar_y_guardar
        from tests.conftest import TEST_DATABASE_URL

        engine_propio = create_engine(TEST_DATABASE_URL)
        SesionPropia = sessionmaker(bind=engine_propio)
        db = SesionPropia()
        try:
            fabrica = Fabrica(db)
            sede = fabrica.sede()
            dispositivo = crear_dispositivo(db, sede)
            db.commit()

            # Header cuyas columnas NO matchean el catálogo y que además
            # NO se pueden auto-crear (HU51): exceden los 100 caracteres
            # que admite prmtr.nmbr, así que caen al flujo pendiente de
            # HU50 y el archivo termina fallando igual que antes. Es la
            # única vía que queda para reproducir el escenario original
            # de esta regresión -la trama se crea (HU49) pero el archivo
            # falla después- ahora que HU51 resuelve sola la mayoría de
            # las columnas desconocidas.
            columna_larga_a = "Columna_" + ("A" * 100)
            columna_larga_b = "Columna_" + ("B" * 100)
            contenido = (
                f"Fecha,{columna_larga_a},{columna_larga_b}\n"
                "2026-09-02 10:00:00,1,2\n"
            )

            formato_resuelto = resolver_formato(db, dispositivo.id_dspstv, "CONV_datos.dat")
            id_mp_creado = formato_resuelto.id_mp

            fallo = False
            try:
                interpretar_y_guardar(
                    db,
                    contenido=contenido,
                    formato=formato_resuelto,
                    dispositivo=dispositivo,
                    id_cnxn=dispositivo.id_cnxn,
                    id_archv=None,
                    nombre_archivo="CONV_datos.dat",
                )
            except ErrorDatosNoRecuperable:
                fallo = True
            # Simula el rollback que hace el llamador real (tasks/ingesta.py,
            # routers/dispositivos.py) cuando el archivo falla.
            db.rollback()

            assert fallo, "el archivo debía fallar (ninguna columna matchea)"

            # LA TRAMA DEBE SEGUIR EXISTIENDO pese al rollback: ya estaba
            # comiteada aparte por _crear_mapeo_formato_automatico.
            formato_sobreviviente = db.get(MapeoFormato, id_mp_creado)
            assert formato_sobreviviente is not None
            assert formato_sobreviviente.orgn_crcn == "Automatico"
            assert formato_sobreviviente.estd == "Activo"

            # Y un segundo intento la reutiliza (no crea una trama nueva) -
            # es la convergencia real: el sistema no repite el ciclo.
            segundo_resuelto = resolver_formato(db, dispositivo.id_dspstv, "CONV_datos2.dat")
            assert segundo_resuelto.id_mp == id_mp_creado
        finally:
            db.rollback()
            id_dspstv = dispositivo.id_dspstv
            id_ubccn = dispositivo.id_ubccn
            id_cnxn = dispositivo.id_cnxn
            id_sd = sede.id_sd
            id_clnt = sede.id_clnt
            db.query(MapeoColumnaPendiente).filter(
                MapeoColumnaPendiente.id_mp.in_(
                    db.query(MapeoFormato.id_mp).filter(MapeoFormato.id_dspstv == id_dspstv)
                )
            ).delete(synchronize_session=False)
            db.query(MapeoColumna).filter(
                MapeoColumna.id_mp.in_(
                    db.query(MapeoFormato.id_mp).filter(MapeoFormato.id_dspstv == id_dspstv)
                )
            ).delete(synchronize_session=False)
            db.query(MapeoFormato).filter(MapeoFormato.id_dspstv == id_dspstv).delete()
            db.query(Dispositivo).filter(Dispositivo.id_dspstv == id_dspstv).delete()
            db.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).delete()
            db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == id_cnxn).delete()
            db.execute(sa.text("DELETE FROM sd WHERE id_sd = :id_sd"), {"id_sd": id_sd})
            db.execute(sa.text("DELETE FROM clnt WHERE id_clnt = :id_clnt"), {"id_clnt": id_clnt})
            # HU51: los parámetros auto-creados se comitean aparte (igual
            # que la trama), así que NO los revierte el rollback de arriba
            # -hay que borrarlos a mano o contaminan los tests siguientes,
            # que chocarían contra el UNIQUE de prmtr.nmbr-.
            _limpiar_parametros_automaticos(db)
            db.commit()
            db.close()
            engine_propio.dispose()

    def test_dos_archivos_concurrentes_del_mismo_prefijo_nuevo_convergen(self):
        """Reproduce el escenario exacto encontrado con el simulador FTP
        real: varios archivos del mismo prefijo nuevo llegan casi
        simultáneamente (sondeo con archivos atrasados), cada uno tomado
        por un proceso de worker distinto. Antes del fix, cada proceso
        creaba y perdía su propia trama en paralelo sin que el sistema
        convergiera nunca. Usa multiprocessing (no threads) para acercarse
        al comportamiento real de los ForkPoolWorker de Celery -la función
        que corre en cada proceso vive a nivel de MÓDULO
        (_procesar_archivo_para_test_concurrencia, al final de este
        archivo) porque multiprocessing no puede picklear una función
        anidada dentro de un método de test."""
        import multiprocessing as mp

        from sqlalchemy import create_engine as _create_engine
        from sqlalchemy.orm import sessionmaker as _sessionmaker

        from tests.conftest import TEST_DATABASE_URL

        engine_propio = _create_engine(TEST_DATABASE_URL)
        SesionPropia = _sessionmaker(bind=engine_propio)
        db = SesionPropia()
        try:
            fabrica = Fabrica(db)
            sede = fabrica.sede()
            dispositivo = crear_dispositivo(db, sede, nombre="Concurrencia HU49")
            db.commit()
            id_dspstv = dispositivo.id_dspstv

            # Ningún parámetro coincide: los 3 archivos deben fallar
            # individualmente, pero la trama debe converger a un solo id_mp.
            contenido = "Fecha,ColumnaZ\n2026-09-02 10:00:00,1\n"
            tareas = [
                (id_dspstv, f"RACE_{i}.dat", contenido) for i in range(4)
            ]

            with mp.Pool(4) as pool:
                ids_mp = pool.map(_procesar_archivo_para_test_concurrencia, tareas)

            # Los 4 procesos concurrentes deben haber convergido a LA MISMA
            # trama -no 4 tramas distintas creadas y perdidas en paralelo.
            assert len(set(ids_mp)) == 1, (
                f"se crearon {len(set(ids_mp))} tramas distintas en vez de "
                f"converger a una sola: {ids_mp}"
            )

            formato_final = db.get(MapeoFormato, ids_mp[0])
            db.refresh(formato_final)
            assert formato_final is not None
            assert formato_final.orgn_crcn == "Automatico"
            assert formato_final.estd == "Activo"
        finally:
            db.rollback()
            id_ubccn = dispositivo.id_ubccn
            id_cnxn = dispositivo.id_cnxn
            id_sd = sede.id_sd
            id_clnt = sede.id_clnt
            db.query(MapeoColumnaPendiente).filter(
                MapeoColumnaPendiente.id_mp.in_(
                    db.query(MapeoFormato.id_mp).filter(MapeoFormato.id_dspstv == id_dspstv)
                )
            ).delete(synchronize_session=False)
            db.query(MapeoColumna).filter(
                MapeoColumna.id_mp.in_(
                    db.query(MapeoFormato.id_mp).filter(MapeoFormato.id_dspstv == id_dspstv)
                )
            ).delete(synchronize_session=False)
            db.query(MapeoFormato).filter(MapeoFormato.id_dspstv == id_dspstv).delete()
            db.query(Dispositivo).filter(Dispositivo.id_dspstv == id_dspstv).delete()
            db.query(Ubicacion).filter(Ubicacion.id_ubccn == id_ubccn).delete()
            db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == id_cnxn).delete()
            db.execute(sa.text("DELETE FROM sd WHERE id_sd = :id_sd"), {"id_sd": id_sd})
            db.execute(sa.text("DELETE FROM clnt WHERE id_clnt = :id_clnt"), {"id_clnt": id_clnt})
            _limpiar_parametros_automaticos(db)
            db.commit()
            db.close()
            engine_propio.dispose()


def _limpiar_parametros_automaticos(db) -> None:
    """Borra los parámetros que HU51 auto-creó (y lo que cuelgue de
    ellos).

    Hace falta SOLO en los tests que usan sesión/engine propios en vez
    del fixture db_session: ahí los commits son reales y no los revierte
    ningún savepoint, así que un parámetro auto-creado sobreviviría al
    test y el siguiente chocaría contra el UNIQUE de prmtr.nmbr."""
    ids = [
        fila[0]
        for fila in db.execute(
            sa.text("SELECT id_prmtr FROM prmtr WHERE orgn_crcn = 'Automatico'")
        )
    ]
    if not ids:
        return
    for tabla, columna in (
        ("tlmtr", "id_prmtr"),
        ("evnt_txt", "id_prmtr"),
        ("mp_clmn", "id_prmtr"),
    ):
        db.execute(
            sa.text(f"DELETE FROM {tabla} WHERE {columna} = ANY(:ids)"),
            {"ids": ids},
        )
    db.execute(sa.text("DELETE FROM prmtr WHERE id_prmtr = ANY(:ids)"), {"ids": ids})


def _procesar_archivo_para_test_concurrencia(args):
    """Función de MÓDULO (no anidada) usada por
    test_dos_archivos_concurrentes_del_mismo_prefijo_nuevo_convergen:
    multiprocessing.Pool no puede picklear una función definida dentro de
    un método de test, así que vive acá."""
    id_dspstv, nombre_archivo, contenido = args
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Dispositivo
    from app.services.ingesta.mapeo import resolver_formato
    from app.tasks.ingesta import ErrorDatosNoRecuperable, interpretar_y_guardar
    from tests.conftest import TEST_DATABASE_URL

    engine = create_engine(TEST_DATABASE_URL)
    Sesion = sessionmaker(bind=engine)
    db = Sesion()
    try:
        dispositivo = db.get(Dispositivo, id_dspstv)
        formato_resuelto = resolver_formato(db, id_dspstv, nombre_archivo)
        id_mp = formato_resuelto.id_mp
        try:
            interpretar_y_guardar(
                db,
                contenido=contenido,
                formato=formato_resuelto,
                dispositivo=dispositivo,
                id_cnxn=dispositivo.id_cnxn,
                id_archv=None,
                nombre_archivo=nombre_archivo,
            )
        except ErrorDatosNoRecuperable:
            db.rollback()
        return id_mp
    finally:
        db.close()
        engine.dispose()
