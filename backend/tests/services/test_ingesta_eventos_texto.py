"""
Integración end-to-end (con BD real) de parámetros de tipo 'texto': una
trama P real de campo (Fecha,R,MensajeP,MensajeA) donde R es numérico
pero MensajeP/MensajeA son mensajes de texto ("Puerta Abierta", "Llave No
Encontrada"). Antes de agregar prmtr.tipo_dato, esas dos columnas se
perdían en silencio porque validador._parsear_numero exige float() para
todo parámetro. Cubre el pipeline completo: resolver_formato ->
interpretar_y_guardar (parseo + estandarización + validación +
persistencia), verificando que:

  - R (numérico) termina en tlmtr con su valor numérico.
  - MensajeP/MensajeA (texto) terminan en evnt_txt con su texto tal cual,
    NO se pierden y NO revientan el resto de la fila.
"""

import pathlib

from app.models import ConexionFTP, Dispositivo, MapeoColumna, MapeoFormato, Ubicacion
from app.models.evento_texto import EventoTexto
from app.models.mapeo_dispositivo import Parametro
from app.models.telemetria import Telemetria
from app.services.ingesta.mapeo import resolver_formato
from app.tasks.ingesta import interpretar_y_guardar

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
POLIGONO_DUMMY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


def _crear_dispositivo(db_session, sede, nombre="Gabinete demo P"):
    ubicacion = Ubicacion(
        id_sd=sede.id_sd, nmbr=f"Ubicacion de {nombre}", lttd=0, lngtd=0, plgn_gjsn=POLIGONO_DUMMY
    )
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=f"Conexion de {nombre}",
        hst="127.0.0.1",
        usr_ftp="usr",
        rt_rmt="/data",
        crdncl_cfrd="cifrado-de-prueba",
    )
    db_session.add_all([ubicacion, conexion])
    db_session.flush()

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn, id_cnxn=conexion.id_cnxn, nmbr=nombre, mrc="Campbell",
        lttd=0, lngtd=0,
    )
    db_session.add(dispositivo)
    db_session.flush()
    return dispositivo


def test_trama_p_guarda_numerico_en_tlmtr_y_texto_en_evnt_txt(db_session, fabrica):
    sede = fabrica.sede()
    dispositivo = _crear_dispositivo(db_session, sede)

    param_r = Parametro(nmbr="contador_r_p_texto", undd="N/A", tipo_dato="numerico")
    param_mensaje_p = Parametro(nmbr="mensaje_puerta_p_texto", undd="N/A", tipo_dato="texto")
    param_mensaje_a = Parametro(nmbr="mensaje_alarma_p_texto", undd="N/A", tipo_dato="texto")
    db_session.add_all([param_r, param_mensaje_p, param_mensaje_a])
    db_session.flush()

    formato = MapeoFormato(
        id_dspstv=dispositivo.id_dspstv,
        tp_trm="P",
        dlmtdr=",",
        dlmtdr_dcml=".",
        fl_inc_dts=1,
        frmt_fch="%Y-%m-%d %H:%M:%S",
        estd="Activo",
    )
    db_session.add(formato)
    db_session.flush()
    db_session.add_all(
        [
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=1, id_prmtr=param_r.id_prmtr),
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=2, id_prmtr=param_mensaje_p.id_prmtr),
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=3, id_prmtr=param_mensaje_a.id_prmtr),
        ]
    )
    db_session.flush()

    contenido = (FIXTURES / "P_demo_gabinete.dat").read_text(encoding="utf-8")
    formato_resuelto = resolver_formato(db_session, dispositivo.id_dspstv, "P_demo_gabinete.dat")

    # id_archv se deja en None: este test no ejercita archv_ingst, solo
    # el tramo de interpretación/persistencia (PP-97..100).
    resultado_validacion, resultado_persistencia = interpretar_y_guardar(
        db_session,
        contenido=contenido,
        formato=formato_resuelto,
        dispositivo=dispositivo,
        id_cnxn=dispositivo.id_cnxn,
        id_archv=None,
        nombre_archivo="P_demo_gabinete.dat",
    )

    assert resultado_validacion.errores == []
    assert resultado_persistencia.guardadas == 3

    fila_r = (
        db_session.query(Telemetria)
        .filter(Telemetria.id_prmtr == param_r.id_prmtr, Telemetria.id_dspstv == dispositivo.id_dspstv)
        .first()
    )
    assert fila_r is not None
    assert float(fila_r.vlr) == 875.0

    fila_mensaje_p = (
        db_session.query(EventoTexto)
        .filter(
            EventoTexto.id_prmtr == param_mensaje_p.id_prmtr,
            EventoTexto.id_dspstv == dispositivo.id_dspstv,
        )
        .first()
    )
    assert fila_mensaje_p is not None
    assert fila_mensaje_p.vlr == "Puerta Abierta"

    fila_mensaje_a = (
        db_session.query(EventoTexto)
        .filter(
            EventoTexto.id_prmtr == param_mensaje_a.id_prmtr,
            EventoTexto.id_dspstv == dispositivo.id_dspstv,
        )
        .first()
    )
    assert fila_mensaje_a is not None
    assert fila_mensaje_a.vlr == "Llave No Encontrada"

    # Regresión explícita del bug que motivó el cambio: nada del texto
    # terminó en tlmtr (rompería el Numeric NOT NULL) y nada del número
    # terminó en evnt_txt.
    assert (
        db_session.query(Telemetria)
        .filter(Telemetria.id_prmtr.in_([param_mensaje_p.id_prmtr, param_mensaje_a.id_prmtr]))
        .count()
        == 0
    )
    assert (
        db_session.query(EventoTexto).filter(EventoTexto.id_prmtr == param_r.id_prmtr).count() == 0
    )
