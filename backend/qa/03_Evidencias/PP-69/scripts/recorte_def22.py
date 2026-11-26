import sys
from PIL import Image
d = sys.argv[1]
a = Image.open(f"{d}/e2e_real/EV-CP-556_listado-columnas-1365.png")
a.crop((288, 338, 1334, 462)).save(f"{d}/defectos/EV-CP-556_DEF-22_rotulo-unidad.png")
