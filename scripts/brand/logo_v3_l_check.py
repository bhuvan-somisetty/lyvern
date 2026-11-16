from PIL import Image, ImageDraw

S = 4
N = 1024 * S
INK = (14, 14, 18)
CREAM = (247, 240, 230)
RED = (224, 32, 45)
OX, OY, K = -99, -9, 1.32


def T(x, y):
    return (512 + (x + OX - 512) * K, 512 + (y + OY - 512) * K)


def P(pts):
    return [(T(x, y)[0] * S, T(x, y)[1] * S) for x, y in pts]


def circle(d, cx, cy, r, fill):
    X, Y = T(cx, cy)
    r = r * K
    d.ellipse([((X - r) * S, (Y - r) * S), ((X + r) * S, (Y + r) * S)], fill=fill)


im = Image.new("RGB", (N, N), INK)
d = ImageDraw.Draw(im)
# L stem + foot (stem top cut at an angle like a blade)
d.polygon(P([(330, 275), (470, 235), (470, 620), (680, 620), (680, 760), (330, 760)]), fill=CREAM)
# commit nodes on the branch line
circle(d, 775, 690, 118, RED)
d.line(P([(715, 692), (752, 730), (830, 640)]), fill=CREAM, width=int(30 * K * S), joint="curve")
for pt in ((715, 692), (830, 640)):
    circle(d, pt[0], pt[1], 15, CREAM)
im = im.resize((1024, 1024), Image.LANCZOS)
im.save("lyvern-bot-logo-v3-1024.png")
im.resize((512, 512), Image.LANCZOS).save("lyvern-bot-logo-v3-512.png")
p = Image.new("RGB", (330, 110), (40, 44, 52))
x = 10
for px in (96, 40, 24):
    p.paste(im.resize((px, px), Image.LANCZOS), (x, 10))
    x += px + 14
p.resize((990, 330), Image.NEAREST).save("preview4.png")
