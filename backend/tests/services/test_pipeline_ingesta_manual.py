"""
Test manual del pipeline PP-97 -> PP-98 -> PP-99 (HU06) usando los dos
.dat de ejemplo en backend/tests/fixtures/. No toca base de datos -por
eso no cubre PP-100-, solo parseo/estandarización/validación.

Correr con:
    cd backend
    ./venv/Scripts/python.exe tests/services/test_pipeline_ingesta_manual.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.services.ingesta.estandarizador import estandarizar_filas, mapeo_de_ejemplo
from app.services.ingesta.parser import ConfiguracionParseo, parsear_archivo_dat
from app.services.ingesta.validador import validar_lecturas

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures"


def correr(nombre_archivo: str, id_cnxn: int = 1):
    ruta = FIXTURES / nombre_archivo
    resultado_parseo = parsear_archivo_dat(str(ruta), ConfiguracionParseo())

    print(f"\n=== {nombre_archivo} ===")
    print(f"columnas detectadas ({len(resultado_parseo.columnas)}): {resultado_parseo.columnas}")
    print(f"filas de datos: {len(resultado_parseo.filas)}")
    for fila in resultado_parseo.filas:
        print(f"  fila {fila.numero_fila}: fecha={fila.fecha_hora} error={fila.error}")

    lecturas = estandarizar_filas(resultado_parseo, id_cnxn=id_cnxn, mapeo=mapeo_de_ejemplo())
    print(f"lecturas estandarizadas (mapeo mock): {len(lecturas)}")
    for l in lecturas:
        print(f"  {l.parametro} = {l.valor_crudo!r} (fila {l.numero_fila})")

    resultado_validacion = validar_lecturas(lecturas)
    print(f"válidas: {len(resultado_validacion.validas)}, con error: {len(resultado_validacion.errores)}")
    for v in resultado_validacion.validas:
        print(f"  OK  {v.parametro} = {v.valor} @ {v.fecha_hora}")
    for e in resultado_validacion.errores:
        print(f"  ERR fila={e.numero_fila} parametro={e.parametro} motivo={e.motivo}")

    assert resultado_parseo.filas, f"{nombre_archivo}: no se parseó ninguna fila"
    assert all(f.error is None for f in resultado_parseo.filas), f"{nombre_archivo}: fila con error de parseo inesperado"


if __name__ == "__main__":
    correr("ejemplo_estado_gabinete.dat")
    correr("ejemplo_calidad_agua.dat")
    print("\nOK: pipeline PP-97..99 corrió sin excepciones sobre los dos fixtures.")
