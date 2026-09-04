"""
HU49 CA5 - la creación automática de un mp_frmt (trama auto-detectada,
ver services/ingesta/mapeo.py) debe quedar en el log de auditoría
(lg_adtr, HT-11), identificable como automática y no como una creación
manual de un Técnico.

Mismo mecanismo de HT-11 (listener before_flush + marca en db.info), pero
sin request HTTP: se simula el contexto que en producción setea
tasks/ingesta.py vía marcar_contexto_auditoria(), con el id_usr de un
usuario Sistema de prueba (no el sembrado por la migración real - no hace
falta esa migración para este test, alcanza con cualquier Usuario válido
para satisfacer el FK NOT NULL de lg_adtr.id_usr).
"""

from app.models import LogAuditoria, MapeoFormato
from app.security.auditoria import limpiar_contexto_auditoria, marcar_contexto_auditoria
from tests.routers.test_mapeos import crear_dispositivo


class TestAuditoriaCreacionAutomaticaDeTrama:
    def test_creacion_automatica_genera_una_fila_de_auditoria(self, db_session, fabrica):
        usuario_sistema = fabrica.usuario(rol=fabrica.rol("Sistema"))
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)

        marcar_contexto_auditoria(db_session, usuario_sistema.id_usr)
        try:
            formato = MapeoFormato(
                id_dspstv=dispositivo.id_dspstv,
                tp_trm="AUTO",
                orgn_crcn="Automatico",
                dlmtdr=",",
                fl_inc_dts=2,
                frmt_fch="%Y-%m-%d %H:%M:%S",
            )
            db_session.add(formato)
            db_session.commit()
        finally:
            limpiar_contexto_auditoria(db_session)

        registros = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"mapeo_formato:{formato.id_mp}")
            .all()
        )
        assert len(registros) == 1
        registro = registros[0]
        assert registro.accn == "crear_trama_automatica"
        assert registro.id_usr == usuario_sistema.id_usr
        assert registro.vlrs_nvs["tp_trm"] == "AUTO"
        assert registro.vlrs_nvs["id_dspstv"] == dispositivo.id_dspstv
        assert registro.vlrs_nvs["orgn_crcn"] == "Automatico"
        assert registro.vlrs_antrrs == {}

    def test_creacion_manual_sin_contexto_no_genera_auditoria(self, db_session, fabrica):
        """Mismo criterio que test_no_se_audita_por_fuera_de_hu20_hu21: un
        POST /mapeos manual (routers/mapeos.py) no pasa por
        marcar_contexto_auditoria/auditar_cambios, así que crear un
        MapeoFormato sin ese contexto -como hace ese endpoint hoy- no
        debe generar ninguna fila."""
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)

        formato = MapeoFormato(
            id_dspstv=dispositivo.id_dspstv,
            tp_trm="MANUAL2",
            orgn_crcn="Manual",
            dlmtdr=",",
            fl_inc_dts=1,
            frmt_fch="%Y-%m-%d %H:%M:%S",
        )
        db_session.add(formato)
        db_session.commit()

        registros = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"mapeo_formato:{formato.id_mp}")
            .count()
        )
        assert registros == 0

    def test_orgn_crcn_manual_con_contexto_seteado_no_se_audita(self, db_session, fabrica):
        """Defensivo: aunque alguien setee el contexto de auditoría (caso
        hipotético hoy, ver comentario en security/auditoria.py), una
        trama con orgn_crcn='Manual' nunca debe registrarse como
        'crear_trama_automatica' - el filtro es sobre el dato real de la
        fila, no sobre la mera presencia de contexto."""
        usuario_sistema = fabrica.usuario(rol=fabrica.rol("Sistema"))
        sede = fabrica.sede()
        dispositivo = crear_dispositivo(db_session, sede)

        marcar_contexto_auditoria(db_session, usuario_sistema.id_usr)
        try:
            formato = MapeoFormato(
                id_dspstv=dispositivo.id_dspstv,
                tp_trm="MANUAL3",
                orgn_crcn="Manual",
                dlmtdr=",",
                fl_inc_dts=1,
                frmt_fch="%Y-%m-%d %H:%M:%S",
            )
            db_session.add(formato)
            db_session.commit()
        finally:
            limpiar_contexto_auditoria(db_session)

        registros = (
            db_session.query(LogAuditoria)
            .filter(LogAuditoria.entdd == f"mapeo_formato:{formato.id_mp}")
            .count()
        )
        assert registros == 0
