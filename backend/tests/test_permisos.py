"""
HT-09: pruebas de la dependencia genérica de autorización (matriz de
permisos + aislamiento entre sedes). Cubren los criterios de aceptación de
la HT a nivel de la dependencia; cuando se implementen HU08/HU10-HU13 hay
que sumar, además, un caso autorizado y uno denegado por cada endpoint
nuevo, como pide la HT.
"""
import logging

import pytest
from fastapi import HTTPException

from app.security.permisos import (
    EDICION,
    LECTURA,
    require_permiso,
    tiene_permiso,
    verificar_sede,
)


def usuario(rol, sede_id=1, scope="por_sede", sub="1"):
    return {"sub": sub, "sede_id": sede_id, "scope": scope, "rol": rol}


class TestMatrizPermisos:
    def test_administrador_tiene_lectura_y_edicion(self):
        assert tiene_permiso("Administrador", "Dispositivos", LECTURA)
        assert tiene_permiso("Administrador", "Dispositivos", EDICION)

    def test_cliente_final_solo_lectura(self):
        assert tiene_permiso("Cliente Final", "Dispositivos", LECTURA)
        assert not tiene_permiso("Cliente Final", "Dispositivos", EDICION)

    def test_rol_o_modulo_desconocido_no_tiene_permiso(self):
        assert not tiene_permiso("Rol Inexistente", "Dispositivos", LECTURA)
        assert not tiene_permiso("Administrador", "Modulo Inexistente", LECTURA)


class TestRequirePermiso:
    def test_caso_autorizado_devuelve_el_usuario(self):
        dependencia = require_permiso("Dispositivos", LECTURA)
        u = usuario("Administrador")
        assert dependencia(u) == u

    def test_caso_denegado_lanza_403_no_401(self):
        # CA HT-09: Cliente con solo lectura en Dispositivos -> 403 al
        # intentar la acción de HU11 (Añadir dispositivo == edición).
        dependencia = require_permiso("Dispositivos", EDICION)
        with pytest.raises(HTTPException) as exc:
            dependencia(usuario("Cliente Final"))
        assert exc.value.status_code == 403
        assert exc.value.status_code != 401

    def test_caso_denegado_queda_registrado_en_el_log(self, caplog):
        dependencia = require_permiso("Dispositivos", EDICION)
        with caplog.at_level(logging.WARNING, logger="auditoria.autorizacion"):
            with pytest.raises(HTTPException):
                dependencia(usuario("Cliente Final", sede_id=7, sub="42"))

        [registro] = caplog.records
        assert "42" in registro.getMessage()
        assert "7" in registro.getMessage()
        assert "Dispositivos" in registro.getMessage()
        assert EDICION in registro.getMessage()


class TestVerificarSede:
    def test_misma_sede_no_lanza(self):
        verificar_sede(usuario("Cliente Final", sede_id=1), sede_id_recurso=1)

    def test_sede_distinta_lanza_403(self):
        # CA HT-09: usuario de la Sede A no accede a recursos de la Sede B.
        with pytest.raises(HTTPException) as exc:
            verificar_sede(usuario("Cliente Final", sede_id=1), sede_id_recurso=2)
        assert exc.value.status_code == 403

    def test_permiso_de_edicion_no_evita_el_aislamiento_de_sede(self):
        # CA HT-09: "incluso si tiene permisos de edición en su propia sede".
        u = usuario("Técnico CENERIS", sede_id=1, scope="por_sede")
        assert tiene_permiso(u["rol"], "Dispositivos", EDICION)
        with pytest.raises(HTTPException):
            verificar_sede(u, sede_id_recurso=99)

    def test_scope_global_ignora_la_sede(self):
        u = usuario("Administrador", sede_id=None, scope="global")
        verificar_sede(u, sede_id_recurso=99)  # no debe lanzar
