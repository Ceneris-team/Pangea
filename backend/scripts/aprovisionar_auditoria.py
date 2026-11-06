"""Crea la cuenta de ejecucion sin privilegios; requiere las dos URLs en el entorno.

DATABASE_URL: cuenta de migraciones; DATABASE_RUNTIME_URL: cuenta de API/workers.
La contrasena solo viaja a PostgreSQL y nunca se imprime ni se guarda en archivos.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def aprovisionar(admin_url, runtime_url):
    runtime = make_url(runtime_url)
    admin = make_url(admin_url)
    if (runtime.host, runtime.port, runtime.database) != (admin.host, admin.port, admin.database):
        raise ValueError("Las URLs deben apuntar a la misma base de datos")
    nombre = runtime.username
    if (
        not nombre
        or nombre in {admin.username, "pangea_app", "pangea_auditoria"}
        or not runtime.password
    ):
        raise ValueError("Define una cuenta de ejecucion independiente con contrasena")
    with create_engine(admin_url, hide_parameters=True).begin() as conexion:
        quoted = conexion.dialect.identifier_preparer.quote(nombre)
        existente = conexion.execute(
            text(
                "SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls FROM pg_roles WHERE rolname=:nombre"
            ),
            {"nombre": nombre},
        ).scalar_one_or_none()
        if existente:
            raise ValueError("La cuenta existente tiene privilegios administrativos")
        if existente is None:
            conexion.execute(
                text(
                    f"CREATE ROLE {quoted} LOGIN PASSWORD :password NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
                ),
                {"password": runtime.password},
            )
        else:
            conexion.execute(
                text(f"ALTER ROLE {quoted} LOGIN PASSWORD :password"),
                {"password": runtime.password},
            )
        if conexion.execute(
            text("SELECT pg_has_role(:nombre,'pangea_auditoria','MEMBER')"), {"nombre": nombre}
        ).scalar_one():
            raise ValueError("La cuenta de ejecucion no puede pertenecer al rol propietario")
        conexion.exec_driver_sql(f"GRANT pangea_app TO {quoted}")
        conexion.exec_driver_sql(
            f"GRANT CONNECT ON DATABASE {conexion.dialect.identifier_preparer.quote(runtime.database)} TO {quoted}"
        )


if __name__ == "__main__":
    aprovisionar(os.environ["DATABASE_URL"], os.environ["DATABASE_RUNTIME_URL"])
    print("Cuenta de ejecucion configurada. Usa DATABASE_RUNTIME_URL en API y workers.")
