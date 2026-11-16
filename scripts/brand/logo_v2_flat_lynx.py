from PIL import Image, ImageDraw

S = 4
N = 1024 * S
RED = (224, 32, 45)
CREAM = (247, 240, 230)
INK = (20, 9, 10)
DEEP = (150, 16, 28)


def P(pts):
    return [(x * S, y * S) for x, y in pts]


def mirror(pts):
    return [(1024 - x, y) for x, y in reversed(pts)]


im = Image.new("RGB", (N, N), RED)
d = ImageDraw.Draw(im)
# subtle flat depth: darker lower band shape behind head
left = [
    (512, 300),
    (400, 285),
    (318, 150),
    (262, 395),
    (170, 520),
    (232, 610),
    (190, 725),
    (335, 700),
    (410, 800),
    (512, 885),
]
head = left + mirror(left)[: -0 or None]
# build full polygon: left half down to chin then mirrored back up
full = left + [(1024 - x, y) for x, y in reversed(left[:-1])]
d.polygon(P(full), fill=CREAM)
# ear inner
for pts in ([(322, 235), (375, 300), (300, 385)],):
    d.polygon(P(pts), fill=DEEP)
    d.polygon(P(mirror(pts)), fill=DEEP)
# forehead stripe marks
for pts in ([(512, 345), (486, 420), (512, 470), (538, 420)],):
    d.polygon(P(pts), fill=RED)
# eyes (angled slits)
eye = [(318, 520), (470, 560), (440, 610), (330, 575)]
d.polygon(P(eye), fill=INK)
d.polygon(P(mirror(eye)), fill=INK)
glint = [(400, 556), (455, 572), (443, 592), (398, 580)]
d.polygon(P(glint), fill=RED)
d.polygon(P(mirror(glint)), fill=RED)
# nose and mouth
d.polygon(P([(478, 655), (546, 655), (512, 705)]), fill=INK)
d.line(P([(512, 705), (512, 765)]), fill=INK, width=14 * S)
d.line(P([(512, 765), (455, 800)]), fill=INK, width=14 * S)
d.line(P([(512, 765), (569, 800)]), fill=INK, width=14 * S)
# cheek tufts
for pts in ([(250, 600), (330, 640), (270, 690)],):
    d.polygon(P(pts), fill=DEEP)
    d.polygon(P(mirror(pts)), fill=DEEP)
im = im.resize((1024, 1024), Image.LANCZOS)
im.save("lyvern-bot-logo-v2-1024.png")
im.resize((512, 512), Image.LANCZOS).save("lyvern-bot-logo-v2-512.png")
p = Image.new("RGB", (330, 110), (13, 17, 23))
x = 10
for px in (96, 40, 24):
    p.paste(im.resize((px, px), Image.LANCZOS), (x, 10))
    x += px + 14
p.resize((990, 330), Image.NEAREST).save("preview3.png")
