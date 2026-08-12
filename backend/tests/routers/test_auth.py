"""
HU01 - Iniciar sesión / HU02 - Gestionar contraseña: tests de /auth.

Cobertura por CA:
  HU01 CA1  login correcto devuelve token + rol; credenciales malas -> 401
  HU01 CA4  GET /auth/perfil devuelve los datos de cuenta y el rol
  HU02 CA1  solicitud de recuperación: 200 y respuesta idéntica exista o no
            el correo (no filtra qué cuentas están registradas)
  HU02 CA2  reset con token válido cambia la contraseña; token vencido o ya
            usado se rechaza
  HU02 CA3  cambio de contraseña autenticado desde "Mi perfil"

  CRÍTICO: el cambio de contraseña invalida TODAS las sesiones previas
  (security/dependencies.py compara el `iat` del JWT contra
  usr.fch_cntrsn_actlzd). Se verifica con DOS tokens emitidos antes del
  cambio, no solo con el de la sesión que hizo el cambio.
"""

import datetime as dt

import jwt
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.main import limiter as limiter_app
from app.models import TokenRecuperacion, Usuario
from app.routers.auth import limiter as limiter_auth
from app.security.hashing import hash_password
from app.security.jwt_auth import ALGORITHM, SECRET_KEY, create_access_token

PASSWORD_ORIGINAL = "Pangea2026"
PASSWORD_NUEVA = "Pangea2027"


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    # Los endpoints de /auth tienen rate limiting (login 5/5min,
    # olvide-contrasena 5/15min, restablecer 10/15min). Los tests hacen
    # muchos más intentos que un usuario real y comparten la IP del
    # TestClient, así que se desactiva: lo que se prueba acá son los CA de
    # las HU, no HT-04/T43.
    #
    # Son DOS instancias distintas de Limiter: la de main.py (registrada en
    # app.state) y la que routers/auth.py crea para sus propios decoradores.
    # Desactivar solo una deja el rate limit activo por la otra.
    limiter_app.enabled = False
    limiter_auth.enabled = False
    try:
        yield TestClient(app)
    finally:
        limiter_app.enabled = True
        limiter_auth.enabled = True
        app.dependency_overrides.clear()


@pytest.fixture()
def usuario_con_password(db_session, fabrica):
    """Usuario Activo cuya contraseña en claro conocemos, para poder hacer
    login de verdad (no con get_current_user sobreescrito)."""
    rol = fabrica.rol("Administrador")
    usuario = fabrica.usuario(rol=rol)
    usuario.cntrsn_hsh = hash_password(PASSWORD_ORIGINAL)
    db_session.flush()
    return usuario, rol


def token_de(usuario) -> str:
    return create_access_token(
        user_id=usuario.id_usr, sede_id=None, scope=usuario.scp, rol=usuario.rol.nmbr
    )


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# HU01 CA1 - Iniciar sesión
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_correcto_devuelve_token_y_rol(self, client, usuario_con_password):
        usuario, rol = usuario_con_password

        resp = client.post(
            "/auth/login", json={"correo": usuario.crr, "contrasena": PASSWORD_ORIGINAL}
        )

        assert resp.status_code == 200
        cuerpo = resp.json()
        assert cuerpo["access_token"]
        assert cuerpo["token_type"] == "bearer"
        assert cuerpo["rol"] == rol.nmbr
        assert cuerpo["nombre_completo"] == usuario.nmbr_cmplt

    def test_contrasena_incorrecta_devuelve_401(self, client, usuario_con_password):
        usuario, _ = usuario_con_password

        resp = client.post(
            "/auth/login", json={"correo": usuario.crr, "contrasena": "NoEsLaClave1"}
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Correo o contraseña incorrectos"

    def test_correo_inexistente_devuelve_401_con_el_mismo_mensaje(
        self, client, usuario_con_password
    ):
        """El mensaje es idéntico al de contraseña incorrecta: no se revela
        si la cuenta existe (HT-04)."""
        resp = client.post(
            "/auth/login",
            json={"correo": "no-existe@pangea-test.com", "contrasena": PASSWORD_ORIGINAL},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Correo o contraseña incorrectos"

    def test_usuario_inactivo_no_puede_entrar(self, client, db_session, usuario_con_password):
        usuario, _ = usuario_con_password
        usuario.estd = "Inactivo"
        db_session.flush()

        resp = client.post(
            "/auth/login", json={"correo": usuario.crr, "contrasena": PASSWORD_ORIGINAL}
        )
        assert resp.status_code == 401

    def test_expone_debe_cambiar_contrasena(self, client, db_session, usuario_con_password):
        """HU04: la contraseña temporal debe cambiarse en el primer login;
        el frontend usa este flag para forzarlo (ver Login.tsx)."""
        usuario, _ = usuario_con_password
        usuario.dbe_cmbr_pswrd = True
        db_session.flush()

        resp = client.post(
            "/auth/login", json={"correo": usuario.crr, "contrasena": PASSWORD_ORIGINAL}
        )
        assert resp.json()["debe_cambiar_contrasena"] is True


# ---------------------------------------------------------------------------
# HU01 CA4 - Mi perfil
# ---------------------------------------------------------------------------


class TestPerfil:
    def test_perfil_devuelve_datos_de_cuenta_y_rol(self, client, usuario_con_password):
        usuario, rol = usuario_con_password

        resp = client.get("/auth/perfil", headers=auth(token_de(usuario)))

        assert resp.status_code == 200
        cuerpo = resp.json()
        assert cuerpo["nombre_completo"] == usuario.nmbr_cmplt
        assert cuerpo["correo"] == usuario.crr
        assert cuerpo["rol"] == rol.nmbr
        assert cuerpo["estado"] == "Activo"

    def test_perfil_sin_token_devuelve_401(self, client):
        assert client.get("/auth/perfil").status_code == 401

    def test_perfil_con_token_invalido_devuelve_401(self, client):
        assert client.get("/auth/perfil", headers=auth("no-es-un-jwt")).status_code == 401


# ---------------------------------------------------------------------------
# HU02 CA1 - Olvidé mi contraseña
# ---------------------------------------------------------------------------


class TestOlvideContrasena:
    def test_correo_existente_devuelve_200_y_crea_token(
        self, client, db_session, usuario_con_password
    ):
        usuario, _ = usuario_con_password

        resp = client.post("/auth/olvide-contrasena", json={"correo": usuario.crr})

        assert resp.status_code == 200
        assert "instrucciones" in resp.json()["mensaje"].lower()
        creados = (
            db_session.query(TokenRecuperacion)
            .filter(TokenRecuperacion.id_usr == usuario.id_usr)
            .count()
        )
        assert creados == 1

    def test_no_revela_si_el_correo_existe(self, client, db_session, usuario_con_password):
        """Práctica de seguridad (anti-enumeración de cuentas): la respuesta
        de un correo registrado y uno que no existe debe ser idéntica en
        status y cuerpo. Confirmado implementado así en auth.py."""
        usuario, _ = usuario_con_password

        existente = client.post("/auth/olvide-contrasena", json={"correo": usuario.crr})
        inexistente = client.post(
            "/auth/olvide-contrasena", json={"correo": "fantasma@pangea-test.com"}
        )

        assert existente.status_code == inexistente.status_code == 200
        assert existente.json() == inexistente.json()

        # ...y sin embargo no se emite ningún token para la cuenta inexistente.
        assert db_session.query(TokenRecuperacion).count() == 1


# ---------------------------------------------------------------------------
# HU02 CA2 - Restablecer con el enlace
# ---------------------------------------------------------------------------


def crear_token_recuperacion(db_session, usuario, minutos_validez=30, usado=False):
    token = TokenRecuperacion(
        id_usr=usuario.id_usr,
        tkn=f"token-de-prueba-{usuario.id_usr}-{minutos_validez}-{usado}",
        fch_exp=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutos_validez),
        usad=usado,
    )
    db_session.add(token)
    db_session.flush()
    return token


class TestRestablecerContrasena:
    def test_token_valido_cambia_la_contrasena(self, client, db_session, usuario_con_password):
        usuario, _ = usuario_con_password
        token = crear_token_recuperacion(db_session, usuario)

        resp = client.post(
            "/auth/restablecer-contrasena",
            json={
                "token": token.tkn,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )

        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "Tu contraseña ha sido actualizada correctamente"

        # La contraseña nueva sirve para entrar y la vieja ya no.
        assert (
            client.post(
                "/auth/login", json={"correo": usuario.crr, "contrasena": PASSWORD_NUEVA}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/auth/login", json={"correo": usuario.crr, "contrasena": PASSWORD_ORIGINAL}
            ).status_code
            == 401
        )

    def test_token_queda_marcado_como_usado(self, client, db_session, usuario_con_password):
        usuario, _ = usuario_con_password
        token = crear_token_recuperacion(db_session, usuario)

        client.post(
            "/auth/restablecer-contrasena",
            json={
                "token": token.tkn,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )

        db_session.refresh(token)
        assert token.usad is True

    def test_token_ya_usado_es_rechazado(self, client, db_session, usuario_con_password):
        """CA: el enlace es de un solo uso."""
        usuario, _ = usuario_con_password
        token = crear_token_recuperacion(db_session, usuario, usado=True)

        resp = client.post(
            "/auth/restablecer-contrasena",
            json={
                "token": token.tkn,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )
        assert resp.status_code == 400

    def test_token_vencido_es_rechazado(self, client, db_session, usuario_con_password):
        """CA: el enlace vive 30 minutos."""
        usuario, _ = usuario_con_password
        token = crear_token_recuperacion(db_session, usuario, minutos_validez=-1)

        resp = client.post(
            "/auth/restablecer-contrasena",
            json={
                "token": token.tkn,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )
        assert resp.status_code == 400
        assert "expirado" in resp.json()["detail"].lower()

    def test_token_inexistente_es_rechazado(self, client, usuario_con_password):
        resp = client.post(
            "/auth/restablecer-contrasena",
            json={
                "token": "token-que-nunca-existio",
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )
        assert resp.status_code == 400

    def test_confirmacion_que_no_coincide_es_rechazada(
        self, client, db_session, usuario_con_password
    ):
        usuario, _ = usuario_con_password
        token = crear_token_recuperacion(db_session, usuario)

        resp = client.post(
            "/auth/restablecer-contrasena",
            json={
                "token": token.tkn,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": "OtraCosa123",
            },
        )
        assert resp.status_code == 400
        assert "no coinciden" in resp.json()["detail"].lower()

    @pytest.mark.parametrize(
        "password_debil",
        ["corta1A", "sinmayuscula1", "SINMINUSCULANINUMERO", "SinNumeroAqui"],
    )
    def test_password_que_no_cumple_la_politica_es_rechazada(
        self, client, db_session, usuario_con_password, password_debil
    ):
        """CA: mínimo 8 caracteres, 1 mayúscula y 1 número."""
        usuario, _ = usuario_con_password
        token = crear_token_recuperacion(db_session, usuario)

        resp = client.post(
            "/auth/restablecer-contrasena",
            json={
                "token": token.tkn,
                "nueva_contrasena": password_debil,
                "confirmar_contrasena": password_debil,
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# HU02 CA3 - Cambiar contraseña desde "Mi perfil"
# ---------------------------------------------------------------------------


class TestCambiarContrasena:
    def test_cambio_exitoso_devuelve_el_mensaje_del_ca(self, client, usuario_con_password):
        usuario, _ = usuario_con_password

        resp = client.put(
            "/auth/cambiar-contrasena",
            headers=auth(token_de(usuario)),
            json={
                "contrasena_actual": PASSWORD_ORIGINAL,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )

        assert resp.status_code == 200
        assert resp.json()["mensaje"] == "Contraseña actualizada exitosamente"

    def test_contrasena_actual_incorrecta_es_rechazada(self, client, usuario_con_password):
        usuario, _ = usuario_con_password

        resp = client.put(
            "/auth/cambiar-contrasena",
            headers=auth(token_de(usuario)),
            json={
                "contrasena_actual": "NoEsLaActual1",
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )
        assert resp.status_code == 400
        assert "actual es incorrecta" in resp.json()["detail"].lower()

    def test_sin_token_devuelve_401(self, client, usuario_con_password):
        resp = client.put(
            "/auth/cambiar-contrasena",
            json={
                "contrasena_actual": PASSWORD_ORIGINAL,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# HU04 - El cambio apaga la exigencia de cambiar la contraseña temporal
# ---------------------------------------------------------------------------


class TestFlagDebeCambiarContrasena:
    """Regresión: `dbe_cmbr_pswrd` se ponía en True al crear el usuario
    (HU04) y NADIE lo volvía a poner en False. Mientras el flag era solo
    informativo el defecto no se notaba; al forzarse el cambio en el primer
    login, el usuario quedaba en bucle: cambiaba la contraseña, volvía a
    entrar, y el sistema se la seguía pidiendo.
    """

    def test_cambiar_contrasena_apaga_el_flag(self, client, db_session, usuario_con_password):
        usuario, _ = usuario_con_password
        usuario.dbe_cmbr_pswrd = True
        db_session.flush()

        resp = client.put(
            "/auth/cambiar-contrasena",
            headers=auth(token_de(usuario)),
            json={
                "contrasena_actual": PASSWORD_ORIGINAL,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )
        assert resp.status_code == 200

        db_session.refresh(usuario)
        assert usuario.dbe_cmbr_pswrd is False

    def test_restablecer_por_enlace_apaga_el_flag(self, client, db_session, usuario_con_password):
        usuario, _ = usuario_con_password
        usuario.dbe_cmbr_pswrd = True
        db_session.flush()
        token = crear_token_recuperacion(db_session, usuario)

        resp = client.post(
            "/auth/restablecer-contrasena",
            json={
                "token": token.tkn,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )
        assert resp.status_code == 200

        db_session.refresh(usuario)
        assert usuario.dbe_cmbr_pswrd is False

    def test_el_login_siguiente_ya_no_exige_cambiar_la_contrasena(
        self, client, db_session, usuario_con_password
    ):
        """El caso reportado de punta a punta: usuario con contraseña
        temporal -> primer login pide cambio -> cambia -> vuelve a entrar
        con la contraseña nueva y YA NO se le pide otra vez."""
        usuario, _ = usuario_con_password
        usuario.dbe_cmbr_pswrd = True
        db_session.flush()

        primer_login = client.post(
            "/auth/login", json={"correo": usuario.crr, "contrasena": PASSWORD_ORIGINAL}
        )
        assert primer_login.json()["debe_cambiar_contrasena"] is True

        client.put(
            "/auth/cambiar-contrasena",
            headers=auth(primer_login.json()["access_token"]),
            json={
                "contrasena_actual": PASSWORD_ORIGINAL,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )

        segundo_login = client.post(
            "/auth/login", json={"correo": usuario.crr, "contrasena": PASSWORD_NUEVA}
        )
        assert segundo_login.status_code == 200
        assert segundo_login.json()["debe_cambiar_contrasena"] is False


# ---------------------------------------------------------------------------
# CRÍTICO - El cambio de contraseña invalida TODAS las sesiones previas
# ---------------------------------------------------------------------------


class TestInvalidacionDeSesionesPrevias:
    """Detalle de conversación de HU02: "el cambio de contraseña invalida
    todas las sesiones activas previas del usuario".

    Implementado en security/dependencies.py comparando el `iat` del JWT
    contra usr.fch_cntrsn_actlzd. Este es el caso que la auditoría marcó
    como implementado pero sin protección de regresión.
    """

    def test_dos_sesiones_previas_quedan_invalidas_tras_cambiar_contrasena(
        self, client, usuario_con_password
    ):
        usuario, _ = usuario_con_password

        # Dos sesiones abiertas ANTES del cambio (p. ej. laptop y celular).
        token_sesion_a = token_de(usuario)
        token_sesion_b = token_de(usuario)

        # Ambas funcionan mientras la contraseña no cambie.
        assert client.get("/auth/perfil", headers=auth(token_sesion_a)).status_code == 200
        assert client.get("/auth/perfil", headers=auth(token_sesion_b)).status_code == 200

        # La sesión A cambia la contraseña...
        cambio = client.put(
            "/auth/cambiar-contrasena",
            headers=auth(token_sesion_a),
            json={
                "contrasena_actual": PASSWORD_ORIGINAL,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )
        assert cambio.status_code == 200

        # ...y AMBAS sesiones previas quedan invalidadas, no solo la otra.
        for token_previo in (token_sesion_a, token_sesion_b):
            resp = client.get("/auth/perfil", headers=auth(token_previo))
            assert resp.status_code == 401
            assert "contraseña fue actualizada" in resp.json()["detail"].lower()

    def test_el_token_emitido_despues_del_cambio_si_funciona(
        self, client, db_session, usuario_con_password
    ):
        """Volver a entrar después de cambiar la contraseña tiene que dar
        una sesión utilizable: la invalidación es de las sesiones PREVIAS.

        HALLAZGO (ver resumen de cierre): el `iat` de un JWT se serializa en
        segundos enteros, mientras `fch_cntrsn_actlzd` guarda microsegundos.
        Un login dentro del MISMO segundo del cambio produce
        iat < fch_cntrsn_actlzd por hasta ~1s de truncamiento, y
        get_current_user rechaza ese token recién emitido. Para que el test
        mida la regla de negocio y no la carrera de relojes, se retrocede
        fch_cntrsn_actlzd un segundo antes de pedir el token nuevo.
        """
        usuario, _ = usuario_con_password

        cambio = client.put(
            "/auth/cambiar-contrasena",
            headers=auth(token_de(usuario)),
            json={
                "contrasena_actual": PASSWORD_ORIGINAL,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )
        assert cambio.status_code == 200

        login = client.post(
            "/auth/login", json={"correo": usuario.crr, "contrasena": PASSWORD_NUEVA}
        )
        assert login.status_code == 200
        token_nuevo = login.json()["access_token"]

        # Se retrocede fch_cntrsn_actlzd por debajo del segundo del `iat`
        # del token nuevo, para medir la regla de negocio y no el
        # truncamiento (ver el test del borde, más abajo).
        db_session.refresh(usuario)
        iat_nuevo = dt.datetime.fromtimestamp(
            jwt.decode(token_nuevo, SECRET_KEY, algorithms=[ALGORITHM])["iat"],
            tz=dt.timezone.utc,
        )
        usuario.fch_cntrsn_actlzd = iat_nuevo - dt.timedelta(seconds=1)
        db_session.flush()

        assert client.get("/auth/perfil", headers=auth(token_nuevo)).status_code == 200

    def test_token_emitido_en_el_mismo_segundo_del_cambio_queda_invalidado(
        self, client, db_session, usuario_con_password
    ):
        """Documenta el borde encontrado al escribir estos tests (NO es el
        comportamiento deseado, ver resumen de cierre): `iat` viaja en
        segundos enteros y fch_cntrsn_actlzd guarda microsegundos, así que
        un token emitido en el mismo segundo del cambio -pero unos
        microsegundos antes, según el reloj de la BD- se rechaza.

        La condición se fuerza explícitamente (fch_cntrsn_actlzd al final
        del mismo segundo del iat) en vez de depender de dónde caiga el
        reloj durante la corrida: escrito como carrera real, el test pasa o
        falla según el momento en que se ejecute.

        Si algún día se corrige (truncando fch_cntrsn_actlzd a segundos o
        dando un margen de tolerancia), este test falla y obliga a
        actualizar la expectativa de forma consciente.
        """
        usuario, _ = usuario_con_password
        token = token_de(usuario)

        # Momento exacto en que se emitió el token, tal como lo ve el
        # backend al decodificarlo (segundos enteros).
        iat = dt.datetime.fromtimestamp(
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])["iat"], tz=dt.timezone.utc
        )

        # Contraseña cambiada dentro de ESE MISMO segundo, 999 ms después.
        usuario.fch_cntrsn_actlzd = iat + dt.timedelta(microseconds=999_000)
        db_session.flush()

        resp = client.get("/auth/perfil", headers=auth(token))
        assert resp.status_code == 401

    def test_restablecer_por_enlace_tambien_invalida_sesiones_previas(
        self, client, db_session, usuario_con_password
    ):
        """El mismo criterio aplica al flujo de "olvidé mi contraseña"
        (CA2), no solo al cambio autenticado (CA3)."""
        usuario, _ = usuario_con_password
        token_sesion = token_de(usuario)
        assert client.get("/auth/perfil", headers=auth(token_sesion)).status_code == 200

        token_recuperacion = crear_token_recuperacion(db_session, usuario)
        client.post(
            "/auth/restablecer-contrasena",
            json={
                "token": token_recuperacion.tkn,
                "nueva_contrasena": PASSWORD_NUEVA,
                "confirmar_contrasena": PASSWORD_NUEVA,
            },
        )

        assert client.get("/auth/perfil", headers=auth(token_sesion)).status_code == 401


def test_usuario_borrado_invalida_su_token(client, db_session, usuario_con_password):
    """get_current_user resuelve el usuario en cada request: si dejó de
    existir, el token deja de servir aunque no haya expirado."""
    usuario, _ = usuario_con_password
    token = token_de(usuario)
    assert client.get("/auth/perfil", headers=auth(token)).status_code == 200

    db_session.query(Usuario).filter(Usuario.id_usr == usuario.id_usr).delete()
    db_session.flush()

    assert client.get("/auth/perfil", headers=auth(token)).status_code == 401
