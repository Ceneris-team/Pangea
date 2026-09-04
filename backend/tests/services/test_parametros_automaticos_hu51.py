"""HU51: creación automática de parámetros para columnas sin match.

Cubre:
1. Inferencia de tipo_dato a partir de los valores reales del archivo -es
   lo que decide si el dato va a tlmtr o a evnt_txt, y equivocarse ahí
   pierde filas en silencio-.
2. Auto-alta del parámetro (CA1) y mapeo inmediato de la columna (CA2).
3. CA6: una columna ya resuelta automáticamente no vuelve a crear un
   parámetro duplicado.
4. Convergencia bajo concurrencia real (multiprocessing), el mismo
   escenario que hizo falta arreglar en HU49.
"""

import multiprocessing as mp

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    ConexionFTP,
    Dispositivo,
    MapeoColumna,
    MapeoColumnaPendiente,
    MapeoFormato,
    Parametro,
    Ubicacion,
)
from app.services.ingesta.mapeo import (
    _inferir_tipo_dato,
    construir_mapeo,
    resolver_formato,
)
from tests.conftest import Fabrica
from tests.services.test_mapeo_ingesta import (
    _limpiar_parametros_automaticos,
    crear_dispositivo,
)


class TestInferenciaDeTipoDato:
    """El tipo mal inferido no da error: manda el dato a la tabla
    equivocada y se pierde en silencio. Por eso se testea aparte."""

    def test_todos_numericos_da_numerico(self):
        assert _inferir_tipo_dato(["12.5", "13.1", "0"], ".") == "numerico"

    def test_un_valor_de_texto_fuerza_texto(self):
        # Basta UNO no numérico: si se eligiera 'numerico', esa fila se
        # perdería al intentar float("Puerta Abierta").
        assert _inferir_tipo_dato(["12.5", "Puerta Abierta"], ".") == "texto"

    def test_sin_muestras_cae_a_texto(self):
        """Sin evidencia no se puede afirmar que sea numérica, y
        equivocarse hacia 'texto' no pierde datos (evnt_txt acepta
        cualquier string)."""
        assert _inferir_tipo_dato([], ".") == "texto"

    def test_vacios_se_ignoran_y_no_fuerzan_texto(self):
        assert _inferir_tipo_dato(["", "  ", "42"], ".") == "numerico"

    def test_solo_vacios_cae_a_texto(self):
        assert _inferir_tipo_dato(["", "   "], ".") == "texto"

    def test_respeta_el_delimitador_decimal_europeo(self):
        """Con dlmtdr_dcml=',' un "23,5" es numérico -si se evaluara con
        el criterio de punto, se lo tomaría por texto y la medición
        terminaría en evnt_txt-."""
        assert _inferir_tipo_dato(["23,5"], ",") == "numerico"
        assert _inferir_tipo_dato(["23,5"], ".") == "texto"


class TestAutoAltaDeParametro:
    @staticmethod
    def _crear_formato_vacio(db, dispositivo, tipo_trama="Z"):
        formato = MapeoFormato(
            id_dspstv=dispositivo.id_dspstv,
            tp_trm=tipo_trama,
            dlmtdr=",",
            dlmtdr_dcml=".",
            fl_inc_dts=1,
            frmt_fch="%Y-%m-%d %H:%M:%S",
            estd="Activo",
        )
        db.add(formato)
        db.flush()
        return formato

    def test_columna_sin_match_crea_parametro_pendiente_y_mapea(self, db_session, fabrica):
        """HU51 CA1-CA2: el parámetro nace 'Pendiente de revision' +
        'Automatico', y la columna queda mapeada contra él en el acto."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)

        mapa = construir_mapeo(
            db_session,
            formato.id_mp,
            ["caudal_hu51"],
            filas_archivo=[type("F", (), {"valores": {"caudal_hu51": "12.5"}})()],
        )

        assert mapa == {"caudal_hu51": "caudal_hu51"}
        creado = db_session.query(Parametro).filter(Parametro.nmbr == "caudal_hu51").one()
        assert creado.estd == "Pendiente de revision"
        assert creado.orgn_crcn == "Automatico"
        assert creado.tipo_dato == "numerico"
        # CA2: la columna quedó mapeada, no pendiente de asignar.
        assert (
            db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == formato.id_mp).count()
            == 1
        )
        assert (
            db_session.query(MapeoColumnaPendiente)
            .filter(MapeoColumnaPendiente.id_mp == formato.id_mp)
            .count()
            == 0
        )

    def test_nombre_se_guarda_exacto_sin_normalizar(self, db_session, fabrica):
        """CA1: el nombre se persiste TAL CUAL viene del header -con
        espacios y mayúsculas-; la normalización es solo para comparar."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)

        construir_mapeo(db_session, formato.id_mp, ["  Caudal Raro (m3/s)  "])

        assert (
            db_session.query(Parametro)
            .filter(Parametro.nmbr == "  Caudal Raro (m3/s)  ")
            .count()
            == 1
        )

    def test_columna_de_texto_se_crea_como_texto(self, db_session, fabrica):
        """El caso que el docstring de Parametro documenta como bug ya
        sufrido: una columna de mensajes no debe quedar como numérica."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)

        construir_mapeo(
            db_session,
            formato.id_mp,
            ["MensajeHU51"],
            filas_archivo=[
                type("F", (), {"valores": {"MensajeHU51": "Puerta Abierta"}})()
            ],
        )

        creado = db_session.query(Parametro).filter(Parametro.nmbr == "MensajeHU51").one()
        assert creado.tipo_dato == "texto"

    def test_ca6_segunda_corrida_no_duplica_el_parametro(self, db_session, fabrica):
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)

        construir_mapeo(db_session, formato.id_mp, ["repetida_hu51"])
        construir_mapeo(db_session, formato.id_mp, ["repetida_hu51"])

        assert db_session.query(Parametro).filter(Parametro.nmbr == "repetida_hu51").count() == 1
        assert (
            db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == formato.id_mp).count()
            == 1
        )

    def test_columna_que_matchea_un_parametro_existente_no_crea_nada(
        self, db_session, fabrica
    ):
        """Regresión de HU50: si YA existe el parámetro, se reutiliza -no
        se auto-crea un duplicado-."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        existente = Parametro(nmbr="ya_existe_hu51", undd="m")
        db_session.add(existente)
        db_session.flush()

        construir_mapeo(db_session, formato.id_mp, ["ya_existe_hu51"])

        assert db_session.query(Parametro).filter(Parametro.nmbr == "ya_existe_hu51").count() == 1
        columna = (
            db_session.query(MapeoColumna).filter(MapeoColumna.id_mp == formato.id_mp).one()
        )
        assert columna.id_prmtr == existente.id_prmtr

    def test_columna_de_fecha_no_genera_parametro(self, db_session, fabrica):
        """La columna de fecha es la marca temporal de la lectura, no una
        medición: crearle un parámetro guardaría la fecha como dato."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)

        mapa = construir_mapeo(
            db_session, formato.id_mp, ["Fecha", "otra_hu51"], columna_fecha="Fecha"
        )

        assert "Fecha" not in mapa
        assert db_session.query(Parametro).filter(Parametro.nmbr == "Fecha").count() == 0
        # Y tampoco queda como pendiente de asignar: no hay nada que
        # resolver a mano ahí.
        assert (
            db_session.query(MapeoColumnaPendiente)
            .filter(MapeoColumnaPendiente.id_mp == formato.id_mp)
            .count()
            == 0
        )

    def test_nombre_demasiado_largo_cae_al_flujo_pendiente_de_hu50(
        self, db_session, fabrica
    ):
        """Un header de más de 100 chars no entra en prmtr.nmbr y NO se
        trunca (truncar podría fusionar dos columnas distintas): se
        deriva al flujo manual que HU50 ya sabía manejar."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        nombre_largo = "C" * 150

        mapa = construir_mapeo(db_session, formato.id_mp, [nombre_largo])

        assert mapa == {}
        assert db_session.query(Parametro).filter(Parametro.nmbr == nombre_largo).count() == 0
        pendiente = (
            db_session.query(MapeoColumnaPendiente)
            .filter(MapeoColumnaPendiente.id_mp == formato.id_mp)
            .one()
        )
        assert pendiente.estd == "Pendiente"

    def test_columna_con_nombre_de_parametro_fusionado_queda_pendiente(
        self, db_session, fabrica
    ):
        """CA5: un parámetro fusionado quedó vacío a propósito y no debe
        resucitar.

        El auto-mapeo lo excluye del catálogo, así que no matchea. Pero
        tampoco se le puede auto-crear un reemplazo con el mismo nombre:
        el UNIQUE de prmtr.nmbr es global e incluye a los fusionados. La
        columna se deriva entonces al flujo manual de HU50, para que un
        humano decida (probablemente asignarla al parámetro destino de la
        fusión)."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)
        formato = self._crear_formato_vacio(db_session, dispositivo)
        fusionado = Parametro(nmbr="fusionado_hu51", undd="m", estd="Fusionado")
        db_session.add(fusionado)
        db_session.flush()

        mapa = construir_mapeo(db_session, formato.id_mp, ["fusionado_hu51"])

        # No se mapeó contra el fusionado (no lo resucitó)...
        assert mapa == {}
        # ...y sigue habiendo UN solo parámetro con ese nombre: el
        # fusionado, intacto.
        assert (
            db_session.query(Parametro).filter(Parametro.nmbr == "fusionado_hu51").count() == 1
        )
        assert fusionado.estd == "Fusionado"
        # La columna quedó para resolución manual.
        pendiente = (
            db_session.query(MapeoColumnaPendiente)
            .filter(MapeoColumnaPendiente.id_mp == formato.id_mp)
            .one()
        )
        assert pendiente.nmbr_clmn_orgn == "fusionado_hu51"
        assert pendiente.estd == "Pendiente"


def _procesar_columna_para_test_concurrencia(args):
    """Función de MÓDULO (multiprocessing no puede picklear una anidada):
    cada proceso procesa un archivo con la MISMA columna sin match."""
    id_dspstv, nombre_archivo, contenido = args
    from app.models import Dispositivo as _Dispositivo
    from app.services.ingesta.mapeo import resolver_formato as _resolver
    from app.tasks.ingesta import ErrorDatosNoRecuperable, interpretar_y_guardar
    from tests.conftest import TEST_DATABASE_URL

    engine = create_engine(TEST_DATABASE_URL)
    Sesion = sessionmaker(bind=engine)
    db = Sesion()
    try:
        dispositivo = db.get(_Dispositivo, id_dspstv)
        formato_resuelto = _resolver(db, id_dspstv, nombre_archivo)
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
            db.commit()
        except ErrorDatosNoRecuperable:
            db.rollback()
        fila = db.execute(
            sa.text("SELECT id_prmtr FROM prmtr WHERE nmbr = 'columna_concurrente_hu51'")
        ).first()
        return fila[0] if fila else None
    finally:
        db.close()
        engine.dispose()


class TestConvergenciaDelAutoAlta:
    """Mismo escenario que obligó al fix de HU49, ahora sobre prmtr: si
    varios workers procesan a la vez archivos con la misma columna sin
    match, debe quedar UN solo parámetro, no uno por worker."""

    def test_cuatro_archivos_concurrentes_convergen_a_un_solo_parametro(self):
        from tests.conftest import TEST_DATABASE_URL

        engine_propio = create_engine(TEST_DATABASE_URL)
        SesionPropia = sessionmaker(bind=engine_propio)
        db = SesionPropia()
        try:
            fabrica = Fabrica(db)
            sede = fabrica.sede()
            dispositivo = crear_dispositivo(db, sede, nombre="Concurrencia HU51")
            db.commit()
            id_dspstv = dispositivo.id_dspstv

            contenido = (
                "Fecha,columna_concurrente_hu51\n2026-09-02 10:00:00,7\n"
            )
            tareas = [
                (id_dspstv, f"CONCHU51_{i}.dat", contenido) for i in range(4)
            ]

            with mp.Pool(4) as pool:
                ids = pool.map(_procesar_columna_para_test_concurrencia, tareas)

            ids_no_nulos = [i for i in ids if i is not None]
            assert ids_no_nulos, "ningún proceso llegó a crear el parámetro"
            assert len(set(ids_no_nulos)) == 1, (
                f"se crearon {len(set(ids_no_nulos))} parámetros distintos en vez de "
                f"converger a uno solo: {ids}"
            )
            # Y en la base quedó efectivamente uno solo.
            total = db.execute(
                sa.text(
                    "SELECT count(*) FROM prmtr WHERE nmbr = 'columna_concurrente_hu51'"
                )
            ).scalar()
            assert total == 1
        finally:
            db.rollback()
            id_ubccn = dispositivo.id_ubccn
            id_cnxn = dispositivo.id_cnxn
            id_sd = sede.id_sd
            id_clnt = sede.id_clnt
            db.execute(
                sa.text(
                    "DELETE FROM tlmtr WHERE id_dspstv = :d",
                ),
                {"d": id_dspstv},
            )
            db.execute(
                sa.text("DELETE FROM evnt_txt WHERE id_dspstv = :d"), {"d": id_dspstv}
            )
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
