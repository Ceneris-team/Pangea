"""
HT-09: pruebas de la dependencia genérica de autorización, ya conectada a
prms_usr_sd (HT-03) en vez de la matriz en memoria que usaba la primera
versión. Cubren los 5 criterios de aceptación de la HT a nivel de la
dependencia; los tests de endpoints concretos están en
tests/routers/test_autorizacion_endpoints.py, para los endpoints que ya
existen (HU07, HU09, HU03/HU04). CA1 sigue pendiente para HU08/HU10-HU13
porque esos endpoints todavía no están implementados -ver el resumen de
cierre de HT-09-.

Corre contra la Postgres real de test (ver tests/conftest.py); por eso los
IDs de usuario/sede son los que devuelve la fábrica, no valores fijos como
en la primera versión de este archivo (esa versión no necesitaba FKs
reales porque tiene_permiso() todavía no tocaba la base de datos).
"""

import logging

import pytest
from fastapi import HTTPException

from app.models.suscripcion import PermisoUsuarioSede
from app.security.permisos import (
    EDICION,
    LECTURA,
    require_permiso,
    tiene_permiso,
    verificar_sede,
)


def usuario_jwt(usuario_db, rol_nombre, sede_id=None, scope="por_sede"):
    """Arma el dict que produce get_current_user (payload del JWT de HT-04)
    a partir de una fila real de Usuario."""
    return {"sub": str(usuario_db.id_usr), "sede_id": sede_id, "scope": scope, "rol": rol_nombre}


def agregar_permiso(db, usuario_db, sede_db, modulo, nivel, rol_db):
    db.add(
        PermisoUsuarioSede(
            id_usr=usuario_db.id_usr, id_sd=sede_db.id_sd, id_rl=rol_db.id_rl, mdl=modulo, nvl=nivel
        )
    )
    db.flush()


class TestTienePermiso:
    """CA2: el permiso ahora sale de prms_usr_sd, no de un diccionario."""

    def test_lectura_permite_leer_pero_no_editar(self, db_session, fabrica):
        rol = fabrica.rol()
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Dispositivos", "Lectura", rol)

        assert tiene_permiso(db_session, usuario.id_usr, sede.id_sd, "Dispositivos", LECTURA)
        assert not tiene_permiso(db_session, usuario.id_usr, sede.id_sd, "Dispositivos", EDICION)

    def test_edicion_permite_leer_y_editar(self, db_session, fabrica):
        rol = fabrica.rol()
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Dispositivos", "Edición", rol)

        assert tiene_permiso(db_session, usuario.id_usr, sede.id_sd, "Dispositivos", LECTURA)
        assert tiene_permiso(db_session, usuario.id_usr, sede.id_sd, "Dispositivos", EDICION)

    def test_nivel_ninguno_no_permite_nada(self, db_session, fabrica):
        rol = fabrica.rol()
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Dispositivos", "Ninguno", rol)

        assert not tiene_permiso(db_session, usuario.id_usr, sede.id_sd, "Dispositivos", LECTURA)
        assert not tiene_permiso(db_session, usuario.id_usr, sede.id_sd, "Dispositivos", EDICION)

    def test_sin_registro_en_prms_usr_sd_no_permite_nada(self, db_session, fabrica):
        # Ningún INSERT para este usuario/módulo: CA2 pide 403, no una
        # excepción o un permiso implícito.
        usuario = fabrica.usuario()
        sede = fabrica.sede()
        assert not tiene_permiso(db_session, usuario.id_usr, sede.id_sd, "Dispositivos", LECTURA)

    def test_permiso_de_otro_modulo_no_aplica(self, db_session, fabrica):
        rol = fabrica.rol()
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario, sede, "Ubicaciones", "Edición", rol)

        assert not tiene_permiso(db_session, usuario.id_usr, sede.id_sd, "Dispositivos", LECTURA)

    def test_scope_por_sede_no_usa_permiso_de_otra_sede(self, db_session, fabrica):
        rol = fabrica.rol()
        cliente = fabrica.cliente()
        sede_propia = fabrica.sede(cliente=cliente)
        sede_ajena = fabrica.sede(cliente=cliente)
        usuario = fabrica.usuario(rol=rol)
        # La fila existe, pero en la sede ajena; se consulta con la propia.
        agregar_permiso(db_session, usuario, sede_ajena, "Dispositivos", "Edición", rol)

        assert not tiene_permiso(
            db_session, usuario.id_usr, sede_propia.id_sd, "Dispositivos", LECTURA
        )

    def test_scope_global_con_registro_en_cualquier_sede_alcanza(self, db_session, fabrica):
        # CA4: id_sd=None (scope global) -> no se filtra por sede, alcanza
        # con una fila en cualquiera de las sedes del usuario.
        rol = fabrica.rol()
        sede = fabrica.sede()
        usuario = fabrica.usuario(rol=rol, scp="global")
        agregar_permiso(db_session, usuario, sede, "Dispositivos", "Edición", rol)

        assert tiene_permiso(db_session, usuario.id_usr, None, "Dispositivos", EDICION)

    def test_scope_global_sin_ningun_registro_igual_deniega(self, db_session, fabrica):
        # CA4, decisión conservadora: scope='global' exime del filtro de
        # SEDE (eso lo hace verificar_sede), pero no del de módulo/nivel.
        # Sin ninguna fila en prms_usr_sd para el módulo, se deniega igual
        # que a un usuario por_sede.
        usuario = fabrica.usuario(scp="global")
        assert not tiene_permiso(db_session, usuario.id_usr, None, "Dispositivos", LECTURA)


class TestRequirePermiso:
    def test_caso_autorizado_devuelve_el_usuario(self, db_session, fabrica):
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario_db, sede, "Dispositivos", "Lectura", rol)

        dependencia = require_permiso("Dispositivos", LECTURA)
        u = usuario_jwt(usuario_db, rol.nmbr, sede_id=sede.id_sd)
        assert dependencia(usuario=u, db=db_session) == u

    def test_caso_denegado_lanza_403_no_401(self, db_session, fabrica):
        # CA HT-09 / CA2: Cliente con solo lectura en Dispositivos -> 403 al
        # intentar la acción de HU11 (Añadir dispositivo == edición).
        rol = fabrica.rol("Cliente Final")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario_db, sede, "Dispositivos", "Lectura", rol)

        dependencia = require_permiso("Dispositivos", EDICION)
        u = usuario_jwt(usuario_db, rol.nmbr, sede_id=sede.id_sd)
        with pytest.raises(HTTPException) as exc:
            dependencia(usuario=u, db=db_session)
        assert exc.value.status_code == 403
        assert exc.value.status_code != 401

    def test_caso_denegado_queda_registrado_en_el_log(self, db_session, fabrica, caplog):
        # CA5: el intento denegado queda registrado con usuario, sede,
        # módulo y acción, igual que antes de conectar la BD.
        usuario_db = fabrica.usuario()
        sede = fabrica.sede()
        dependencia = require_permiso("Dispositivos", EDICION)
        u = usuario_jwt(usuario_db, "Cliente Final", sede_id=sede.id_sd)

        with caplog.at_level(logging.WARNING, logger="auditoria.autorizacion"):
            with pytest.raises(HTTPException):
                dependencia(usuario=u, db=db_session)

        [registro] = caplog.records
        assert str(usuario_db.id_usr) in registro.getMessage()
        assert str(sede.id_sd) in registro.getMessage()
        assert "Dispositivos" in registro.getMessage()
        assert EDICION in registro.getMessage()


class TestVerificarSede:
    def usuario(self, sede_id=1, scope="por_sede", sub="1", rol="Cliente Final"):
        return {"sub": sub, "sede_id": sede_id, "scope": scope, "rol": rol}

    def test_misma_sede_no_lanza(self):
        verificar_sede(self.usuario(sede_id=1), sede_id_recurso=1)

    def test_sede_distinta_lanza_403(self):
        # CA3: usuario de la Sede A no accede a recursos de la Sede B.
        with pytest.raises(HTTPException) as exc:
            verificar_sede(self.usuario(sede_id=1), sede_id_recurso=2)
        assert exc.value.status_code == 403

    def test_permiso_de_edicion_no_evita_el_aislamiento_de_sede(self, db_session, fabrica):
        # CA3: "incluso si tiene permisos de edición en su propia sede".
        rol = fabrica.rol("Técnico CENERIS")
        sede = fabrica.sede()
        usuario_db = fabrica.usuario(rol=rol)
        agregar_permiso(db_session, usuario_db, sede, "Dispositivos", "Edición", rol)

        assert tiene_permiso(db_session, usuario_db.id_usr, sede.id_sd, "Dispositivos", EDICION)

        u = self.usuario(sede_id=sede.id_sd, sub=str(usuario_db.id_usr), rol=rol.nmbr)
        with pytest.raises(HTTPException):
            verificar_sede(u, sede_id_recurso=sede.id_sd + 1000)

    def test_scope_global_ignora_la_sede(self):
        # CA4: scope='global' puede operar sobre cualquier sede sin
        # asignación previa -esto es solo el filtro de sede; el de
        # módulo/nivel lo sigue exigiendo tiene_permiso() (ver arriba).
        u = self.usuario(sede_id=None, scope="global", rol="Administrador")
        verificar_sede(u, sede_id_recurso=99)  # no debe lanzar
