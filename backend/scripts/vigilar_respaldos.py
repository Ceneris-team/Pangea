"""Monitor continuo independiente de Celery/Redis para contenedores Lightsail."""

import json
import logging
import time

from app.services.correo_ses import codigo_error
from app.services.vigilancia_respaldos import comprobar_respaldo


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            resultado = comprobar_respaldo()
            logging.info("Revision de respaldos: %s", json.dumps(resultado))
        except Exception as exc:
            logging.error("Fallo de vigilancia: %s", codigo_error(exc))
        time.sleep(3600)


if __name__ == "__main__":
    main()
