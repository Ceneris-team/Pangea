import sys
from PIL import Image
d = sys.argv[1]
a = Image.open(f"{d}/e2e_real/EV-CP-540_filtro-fallido-1365.png")
b = Image.open(f"{d}/e2e_real/EV-CP-549_historial-automatico-1365.png")
titulo = a.crop((270, 130, 1340, 295))
menu = a.crop((0, 835, 260, 890))
boton = b.crop((440, 780, 925, 840))
W = titulo.width
out = Image.new("RGB", (W, titulo.height + menu.height + boton.height + 30), (11, 17, 28))
out.paste(titulo, (0, 0)); out.paste(menu, (0, titulo.height + 15)); out.paste(boton, (300, titulo.height + 15))
out.paste(boton, (300, titulo.height + 15))
y = titulo.height + menu.height + 25
out = out.crop((0, 0, W, max(y, titulo.height + 15 + boton.height) + 5))
out.save(f"{d}/defectos/EV-CP-540_DEF-21_rotulos.png")
print(out.size)
