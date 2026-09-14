"""
HU 29 CA3 - integración end-to-end (con BD real): un archivo .dat real
que trae un valor por encima del umbral configurado dispara la alarma.

Cubre el cableado completo interpretar_y_guardar -> evaluar_alarmas tal
como lo hace app/tasks/ingesta.py (persistir telemetría, confirmar con
commit, y solo entonces evaluar). tests/services/test_motor_alarmas.py ya
cubre las reglas de evaluar_alarmas() en detalle; este test solo verifica
que el cableado con el pipeline real de ingesta funciona.
"""

import pathlib

from app.models import ConexionFTP, Dispositivo, MapeoColumna, MapeoFormato, Ubicacion
from app.models.alarma import Alarma, CondicionAlarma
from app.models.mapeo_dispositivo import Parametro
from app.services.alarmas.motor import evaluar_alarmas
from app.services.ingesta.mapeo import resolver_formato
from app.tasks.ingesta import interpretar_y_guardar

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"
POLIGONO_DUMMY = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}


def test_un_dat_con_valor_por_encima_del_umbral_dispara_la_alarma(db_session, fabrica):
    sede = fabrica.sede()
    usuario = fabrica.usuario()
    ubicacion = Ubicacion(
        id_sd=sede.id_sd,
        nmbr="Ubicación H_demo_gabinete",
        lttd=0,
        lngtd=0,
        plgn_gjsn=POLIGONO_DUMMY,
    )
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr="Conexion H_demo_gabinete",
        hst="127.0.0.1",
        usr_ftp="usr",
        rt_rmt="/data",
        crdncl_cfrd="cifrado-de-prueba",
    )
    db_session.add_all([ubicacion, conexion])
    db_session.flush()

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr="Gabinete H_demo",
        mrc="Campbell",
        lttd=0,
        lngtd=0,
    )
    db_session.add(dispositivo)
    db_session.flush()

    param_temp = Parametro(nmbr="temperatura_dispara_hu29", undd="°C", tipo_dato="numerico")
    param_batt = Parametro(nmbr="bateria_dispara_hu29", undd="V", tipo_dato="numerico")
    db_session.add_all([param_temp, param_batt])
    db_session.flush()

    formato = MapeoFormato(
        id_dspstv=dispositivo.id_dspstv,
        tp_trm="H",
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
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=1, id_prmtr=param_temp.id_prmtr),
            MapeoColumna(id_mp=formato.id_mp, indc_clmn=2, id_prmtr=param_batt.id_prmtr),
        ]
    )
    db_session.flush()

    # El último registro de H_demo_gabinete.dat es Temperatura=23.00.
    alarma = Alarma(
        id_usr=usuario.id_usr,
        id_sd=ubicacion.id_sd,
        nmbr="Temperatura alta gabinete",
        id_prmtr=param_temp.id_prmtr,
        id_ubccn=ubicacion.id_ubccn,
    )
    db_session.add(alarma)
    db_session.flush()
    db_session.add(CondicionAlarma(id_alrm=alarma.id_alrm, oprdr=">", vlr_umbrl=22.5))
    db_session.flush()

    contenido = (FIXTURES / "H_demo_gabinete.dat").read_text(encoding="utf-8")
    formato_resuelto = resolver_formato(db_session, dispositivo.id_dspstv, "H_demo_gabinete.dat")

    _resultado_validacion, resultado_persistencia = interpretar_y_guardar(
        db_session,
        contenido=contenido,
        formato=formato_resuelto,
        dispositivo=dispositivo,
        id_cnxn=dispositivo.id_cnxn,
        id_archv=None,
        nombre_archivo="H_demo_gabinete.dat",
    )
    db_session.commit()

    evaluar_alarmas(
        db_session, resultado_persistencia.id_ubccn, resultado_persistencia.ultimos_por_parametro
    )

    db_session.refresh(alarma)
    assert alarma.estd == "Disparada"
