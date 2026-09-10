"""
R-05 del RAID log: verifica que scripts/rotar_ftp_credential_key.py pueda
re-cifrar cnxn_ftp.crdncl_cfrd de una llave vieja a una nueva sin perder
ninguna credencial y sin dejar filas mezcladas si algo falla.

Corre contra la Postgres real de test (ver tests/conftest.py), igual que
el resto de los tests de este repo.
"""

from cryptography.fernet import Fernet

from app.models.ubicacion_conexion import ConexionFTP
from scripts.rotar_ftp_credential_key import rotar_credenciales

KEY_A = Fernet.generate_key()
KEY_B = Fernet.generate_key()


def crear_conexion_ftp(db, sede, nombre, credencial_plana, fernet):
    conexion = ConexionFTP(
        id_sd=sede.id_sd,
        nmbr=nombre,
        prtcl="FTP",
        hst="ftp.pangea-test.com",
        prt=21,
        usr_ftp="usuario_ftp",
        crdncl_cfrd=fernet.encrypt(credencial_plana.encode("utf-8")).decode("utf-8"),
        rt_rmt="/datalogger",
    )
    db.add(conexion)
    db.flush()
    return conexion


class TestRotarCredenciales:
    def test_dry_run_no_escribe_nada(self, db_session, fabrica):
        sede = fabrica.sede()
        fernet_a = Fernet(KEY_A)
        conexion = crear_conexion_ftp(db_session, sede, "FTP Norte", "clave-secreta-1", fernet_a)
        valor_original = conexion.crdncl_cfrd

        resultado = rotar_credenciales(db_session, fernet_a, Fernet(KEY_B), aplicar=False)

        assert resultado.total == 1
        assert resultado.migradas == 1
        assert resultado.fallidas == 0
        db_session.refresh(conexion)
        assert conexion.crdncl_cfrd == valor_original

    def test_aplicar_re_cifra_todas_las_filas_incluidas_inactivas(self, db_session, fabrica):
        sede = fabrica.sede()
        fernet_a = Fernet(KEY_A)
        fernet_b = Fernet(KEY_B)

        credenciales_planas = {
            "FTP Norte": "clave-secreta-1",
            "FTP Sur": "clave-secreta-2",
            "TCP Este": "clave-secreta-3",
        }
        conexiones = [
            crear_conexion_ftp(db_session, sede, nombre, plana, fernet_a)
            for nombre, plana in credenciales_planas.items()
        ]
        # Una de las conexiones está Inactiva: igual debe re-cifrarse (el
        # script no filtra por estd).
        conexiones[1].estd = "Inactiva"
        db_session.flush()

        resultado = rotar_credenciales(db_session, fernet_a, fernet_b, aplicar=True)

        assert resultado.total == 3
        assert resultado.migradas == 3
        assert resultado.fallidas == 0

        for conexion in conexiones:
            db_session.refresh(conexion)
            plana_esperada = credenciales_planas[conexion.nmbr]
            # Ya no se puede descifrar con la llave vieja...
            assert conexion.crdncl_cfrd != fernet_a.encrypt(plana_esperada.encode("utf-8"))
            # ...pero sí con la nueva, y el valor coincide con el original.
            descifrada = fernet_b.decrypt(conexion.crdncl_cfrd.encode("utf-8")).decode("utf-8")
            assert descifrada == plana_esperada

    def test_una_fila_con_llave_incorrecta_aborta_sin_modificar_nada(self, db_session, fabrica):
        sede = fabrica.sede()
        fernet_a = Fernet(KEY_A)
        fernet_b = Fernet(KEY_B)
        fernet_otra = Fernet(Fernet.generate_key())

        buena = crear_conexion_ftp(db_session, sede, "FTP Norte", "clave-secreta-1", fernet_a)
        # Esta fila quedó cifrada con una llave distinta a OLD (dato corrupto
        # o llave equivocada): el dry-run debe reportarla y --aplicar no debe
        # tocar ninguna fila, ni siquiera la que sí hubiera migrado bien.
        mala = crear_conexion_ftp(db_session, sede, "FTP Sur", "clave-secreta-2", fernet_otra)
        id_buena, id_mala = buena.id_cnxn, mala.id_cnxn
        valor_original_buena = buena.crdncl_cfrd
        valor_original_mala = mala.crdncl_cfrd
        # rotar_credenciales hace su propio rollback() cuando --aplicar
        # encuentra fallos, y un rollback deshace cualquier flush() previo
        # que no haya sido confirmado. Se confirma el fixture con commit()
        # (create_savepoint hace que esto opere sobre un SAVEPOINT interno,
        # no sobre la transacción externa del test) para que ese rollback
        # solo afecte lo que haga rotar_credenciales, no el setup del test.
        db_session.commit()

        dry_run = rotar_credenciales(db_session, fernet_a, fernet_b, aplicar=False)
        assert dry_run.total == 2
        assert dry_run.migradas == 1
        assert dry_run.fallidas == 1
        assert dry_run.ids_fallidos == [id_mala]

        aplicado = rotar_credenciales(db_session, fernet_a, fernet_b, aplicar=True)
        assert aplicado.fallidas == 1

        # rotar_credenciales hizo rollback() al fallar una fila en modo
        # --aplicar: las instancias `buena`/`mala` quedan detached (aunque
        # sus filas sigan intactas en la BD), así que se releen por id en
        # vez de refresh() sobre las referencias viejas.
        db_session.expire_all()
        buena_relida = db_session.get(ConexionFTP, id_buena)
        mala_relida = db_session.get(ConexionFTP, id_mala)
        assert buena_relida.crdncl_cfrd == valor_original_buena
        assert mala_relida.crdncl_cfrd == valor_original_mala

    def test_nunca_expone_la_credencial_en_ids_fallidos(self, db_session, fabrica):
        sede = fabrica.sede()
        fernet_otra = Fernet(Fernet.generate_key())
        mala = crear_conexion_ftp(db_session, sede, "FTP Sur", "clave-secreta-2", fernet_otra)

        resultado = rotar_credenciales(db_session, Fernet(KEY_A), Fernet(KEY_B), aplicar=False)

        assert resultado.ids_fallidos == [mala.id_cnxn]
        assert "clave-secreta-2" not in str(resultado.ids_fallidos)
