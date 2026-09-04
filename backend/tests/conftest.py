"""
Fixtures compartidas para los tests de HT-09 (y futuros tests de routers).

Corre contra una Postgres real (`TEST_DATABASE_URL`, por defecto
`pangea_test` en localhost) con las migraciones de Alembic ya aplicadas,
en vez de SQLite: el esquema real usa tipos (`JSONB`) e índices (BRIN,
partición por rango) específicos de Postgres que SQLite no puede
compilar, y HT-09 justamente necesita validar contra `prms_usr_sd` tal
como lo define la migración de HT-03, no una recreación aproximada.

Cada test corre dentro de una transacción que se revierte al final
(`rollback()`), así que no hace falta limpiar datos entre tests ni
volver a correr las migraciones.

Antes de correr los tests hay que tener la base de datos de test creada
y migrada una vez:

    createdb pangea_test
    DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/pangea_test \
        python -m alembic upgrade head
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Cliente, Rol, Sede, Usuario
from app.security.hashing import hash_password

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/pangea_test"
)


@pytest.fixture(scope="session")
def _engine():
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(_engine):
    conexion = _engine.connect()
    transaccion = conexion.begin()
    # Los endpoints reales hacen su propio db.commit() (p. ej. crear_usuario
    # en HU04) y algunos scripts hacen su propio db.rollback() (p. ej.
    # rotar_ftp_credential_key.py). Para que eso no termine ni revierta la
    # transacción externa -y así poder deshacer todo al final del test con
    # un solo rollback()-, join_transaction_mode="create_savepoint" hace
    # que cada commit()/rollback() de la sesión opere sobre un SAVEPOINT
    # interno en vez de la transacción de `conexion`.
    SessionLocalPrueba = sessionmaker(bind=conexion, join_transaction_mode="create_savepoint")
    session = SessionLocalPrueba()

    try:
        yield session
    finally:
        session.close()
        transaccion.rollback()
        conexion.close()


class Fabrica:
    """Crea filas mínimas válidas (Postgres real exige las FK de verdad,
    a diferencia de SQLite) para no repetir el boilerplate de
    Rol/Cliente/Sede/Usuario en cada test."""

    def __init__(self, db):
        self.db = db
        self._n = 0

    def _siguiente(self) -> int:
        self._n += 1
        return self._n

    def rol(self, nombre: str | None = None) -> Rol:
        # La migración de HT-03 ya siembra los 4 roles base (Administrador,
        # Técnico CENERIS, Cliente Final, Administrador Comercial) con
        # nombre UNIQUE. Si el test pide uno de esos, se reusa la fila
        # migrada en vez de intentar duplicarla.
        if nombre is not None:
            existente = self.db.query(Rol).filter(Rol.nmbr == nombre).first()
            if existente is not None:
                return existente
        n = self._siguiente()
        rol = Rol(nmbr=nombre or f"Rol de prueba {n}", dscrpcn="rol creado por los tests")
        self.db.add(rol)
        self.db.flush()
        return rol

    def cliente(self) -> Cliente:
        n = self._siguiente()
        cliente = Cliente(
            rzn_scl=f"Cliente de prueba {n}",
            rc=f"{n:011d}",
            crr_cntct=f"cliente{n}@pangea-test.com",
        )
        self.db.add(cliente)
        self.db.flush()
        return cliente

    def sede(self, cliente: Cliente | None = None) -> Sede:
        n = self._siguiente()
        cliente = cliente or self.cliente()
        sede = Sede(id_clnt=cliente.id_clnt, nmbr=f"Sede de prueba {n}")
        self.db.add(sede)
        self.db.flush()
        return sede

    def usuario(self, rol: Rol | None = None, scp: str = "por_sede") -> Usuario:
        n = self._siguiente()
        rol = rol or self.rol()
        usuario = Usuario(
            id_rl=rol.id_rl,
            scp=scp,
            nmbr_cmplt=f"Usuario de prueba {n}",
            crr=f"usuario{n}@pangea-test.com",
            cntrsn_hsh=hash_password("Pangea2026"),
        )
        self.db.add(usuario)
        self.db.flush()
        return usuario


@pytest.fixture()
def fabrica(db_session):
    return Fabrica(db_session)
