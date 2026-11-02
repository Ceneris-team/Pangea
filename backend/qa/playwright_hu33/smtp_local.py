"""Servidor SMTP local de QA con STARTTLS (el correo del producto exige TLS). Guarda cada mensaje recibido como .eml.
Uso: python smtp_local.py <carpeta_salida> <cert.pem> <key.pem>"""
import asyncio
import ssl
import sys
import time
from pathlib import Path

from aiosmtpd.controller import Controller


class Recibir:
    def __init__(self, carpeta):
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)

    async def handle_DATA(self, server, session, envelope):
        nombre = self.carpeta / f"{time.strftime('%H%M%S')}_{len(list(self.carpeta.glob('*.eml'))) + 1:02d}.eml"
        nombre.write_bytes(envelope.original_content)
        print(f"recibido {nombre.name} para {envelope.rcpt_tos}", flush=True)
        return "250 OK"


if __name__ == "__main__":
    carpeta, cert, clave = sys.argv[1:4]
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(cert, clave)
    controlador = Controller(Recibir(carpeta), hostname="127.0.0.1", port=1025, tls_context=contexto, require_starttls=True)
    controlador.start()
    print("SMTP local con STARTTLS en 127.0.0.1:1025", flush=True)
    asyncio.get_event_loop().run_forever()
