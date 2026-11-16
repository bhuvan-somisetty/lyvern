from PIL import Image, ImageDraw
import numpy as np

S = 3
N = 1024 * S
CREAM = (250, 243, 233)
INK = (22, 12, 16)
DEEP = (176, 20, 34)
GLOW = (255, 84, 72)


def P(pts):
    return [(x * S, y * S) for x, y in pts]


def M(pts):
    return [(1024 - x, y) for x, y in pts]


# background: soft radial red
yy, xx = np.mgrid[0:N, 0:N]
r = np.sqrt((xx - N * 0.5) ** 2 + (yy - N * 0.42) ** 2) / (N * 0.75)
t = np.clip(r, 0, 1)[..., None]
c0 = np.array([238, 52, 52])
c1 = np.array([158, 14, 32])
bg = (c0 * (1 - t) + c1 * t).astype("uint8")
im = Image.fromarray(bg)
d = ImageDraw.Draw(im)


def rr(box, rad, fill):
    d.rounded_rectangle([v * S for v in box], radius=rad * S, fill=fill)


def oval(cx, cy, rx, ry, fill):
    d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=fill)


# ears with tufts
ear = [(262, 360), (292, 150), (478, 285)]
d.polygon(P(ear), fill=CREAM)
d.polygon(P(M(ear)), fill=CREAM)
inner = [(312, 310), (322, 215), (420, 285)]
d.polygon(P(inner), fill=DEEP)
d.polygon(P(M(inner)), fill=DEEP)
tuft = [(292, 150), (262, 55), (338, 128)]
d.polygon(P(tuft), fill=INK)
d.polygon(P(M(tuft)), fill=INK)
# cheek ruffs
ruff = [(215, 540), (110, 640), (235, 700)]
d.polygon(P(ruff), fill=CREAM)
d.polygon(P(M(ruff)), fill=CREAM)
# head
rr((196, 262, 828, 812), 210, CREAM)
# visor
rr((258, 430, 766, 650), 110, INK)
# eyes
for cx in (400, 624):
    oval(cx, 540, 58, 66, GLOW)
    oval(cx - 16, 518, 18, 22, (255, 235, 225))
# nose + smile
d.polygon(P([(480, 690), (544, 690), (512, 730)]), fill=INK)
d.arc([x * S for x in (452, 700, 512, 772)], 20, 170, fill=INK, width=12 * S)
d.arc([x * S for x in (512, 700, 572, 772)], 10, 160, fill=INK, width=12 * S)
# forehead status light
oval(512, 340, 22, 22, DEEP)
oval(512, 340, 10, 10, GLOW)
im = im.resize((1024, 1024), Image.LANCZOS)
im.save("lyvern-bot-logo-v4-1024.png")
im.resize((512, 512), Image.LANCZOS).save("lyvern-bot-logo-v4-512.png")
p = Image.new("RGB", (330, 110), (13, 17, 23))
x = 10
for px in (96, 40, 24):
    p.paste(im.resize((px, px), Image.LANCZOS), (x, 10))
    x += px + 14
p.resize((990, 330), Image.NEAREST).save("preview5.png")
