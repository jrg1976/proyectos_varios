"""Build the embedded assets for the Formigal 3D map.

Inputs (data_raw/):  mdt.tif (IGN MDT05, EPSG:4258), ortho.jpg (PNOA WMS, same bbox),
                     feats.json (from parse_osm.py)
Outputs (build/):    height.bin, normal.jpg, winter.jpg, summer.jpg, data.json
"""
import io, json, math, os, sys
import numpy as np
from PIL import Image, ImageFilter

RAW, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
LAT0, LAT1, LON0, LON1 = 42.735, 42.815, -0.455, -0.33
LATC = (LAT0 + LAT1) / 2
MX = 111320 * math.cos(math.radians(LATC))  # metres per degree lon
MY = 110950                                   # metres per degree lat
W_M = (LON1 - LON0) * MX
H_M = (LAT1 - LAT0) * MY

dem = np.array(Image.open(f'{RAW}/mdt.tif')).astype(np.float32)  # row 0 = north
dem[dem < 500] = np.nan
if np.isnan(dem).any():
    m = np.nanmean(dem); dem = np.where(np.isnan(dem), m, dem)
DH, DW = dem.shape
print('DEM', dem.shape, dem.min(), dem.max(), 'extent m', W_M, H_M)

def lonlat_to_xz(lon, lat):
    return ((lon - (LON0 + LON1) / 2) * MX, -((lat - LATC) * MY))

def sample(lon, lat):
    fx = (lon - LON0) / (LON1 - LON0) * (DW - 1)
    fy = (LAT1 - lat) / (LAT1 - LAT0) * (DH - 1)
    x0 = int(np.clip(math.floor(fx), 0, DW - 2)); y0 = int(np.clip(math.floor(fy), 0, DH - 2))
    tx, ty = fx - x0, fy - y0
    a, b, c, d = dem[y0, x0], dem[y0, x0 + 1], dem[y0 + 1, x0], dem[y0 + 1, x0 + 1]
    return float(a * (1 - tx) * (1 - ty) + b * tx * (1 - ty) + c * (1 - tx) * ty + d * tx * ty)

# ---------- mesh height grid ----------
GW, GH = 768, int(round(768 * H_M / W_M))
hg = np.array(Image.fromarray(dem).resize((GW, GH), Image.BILINEAR))
q = np.clip((hg - 1000) * 10, 0, 65535).astype('<u2')
rgb = np.zeros((GH, GW, 3), np.uint8); rgb[..., 0] = q >> 8; rgb[..., 1] = q & 255
Image.fromarray(rgb).save(f'{OUT}/height.png', optimize=True)  # R=high byte, G=low byte of (h-1000)*10
print('grid', GW, GH)

# ---------- normals / slope at texture res ----------
TW = 4096; TH = int(round(TW * H_M / W_M))
demT = np.array(Image.fromarray(dem).resize((TW, TH), Image.BILINEAR))
px = W_M / TW; py = H_M / TH
gy, gx = np.gradient(demT, py, px)  # gy: d/drow (south), gx: d/dcol (east)
nx, ny, nz = -gx, np.ones_like(gx), gy  # three: x east, y up, z south
n = np.sqrt(nx * nx + ny * ny + nz * nz)
nx, ny, nz = nx / n, ny / n, nz / n
slope = np.degrees(np.arccos(ny))
nm = np.stack([(nx * .5 + .5) * 255, (nz * .5 + .5) * 255, (ny * .5 + .5) * 255], -1).astype(np.uint8)
NW = 2048; NH = int(round(NW * H_M / W_M))
Image.fromarray(nm).resize((NW, NH), Image.BILINEAR).save(f'{OUT}/normal.jpg', quality=88)

# ---------- summer texture (PNOA) with French gap filled ----------
ortho = Image.open(f'{RAW}/ortho.jpg').convert('RGB').resize((TW, TH), Image.LANCZOS)
o = np.array(ortho).astype(np.float32)
white = (o.min(-1) > 245)
if white.any():
    blur = np.array(ortho.filter(ImageFilter.GaussianBlur(60))).astype(np.float32)
    # replace with a plausible alpine tone shaded by slope
    base = np.array([128, 124, 98], np.float32)
    fill = base * (0.75 + 0.25 * np.clip(ny, 0, 1))[..., None]
    o[white] = fill[white]
summer = np.clip(o, 0, 255).astype(np.uint8)
Image.fromarray(summer).save(f'{OUT}/summer.jpg', quality=78, optimize=True)

# ---------- winter texture: snow recreation from relief + ortho ----------
lum = (o[..., 0] * .3 + o[..., 1] * .59 + o[..., 2] * .11) / 255
g_dom = (o[..., 1] - (o[..., 0] + o[..., 2]) / 2) / 255
forest = np.clip((0.40 - lum) * 5, 0, 1) * np.clip(g_dom * 20 + .2, 0, 1) * np.clip((2000 - demT) / 200, 0, 1)
forest = np.array(Image.fromarray((forest * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1))).astype(np.float32) / 255
water = (o[..., 2] > o[..., 0] + 10) & (o[..., 1] > o[..., 0] + 5) & (slope < 4) & (demT < 1700)
elev_f = np.clip((demT - 1250) / 300, 0, 1)
rock = np.clip((slope - 36) / 14, 0, 1)
snow = elev_f * (1 - rock * .85) * (1 - forest * .7)
noise = np.array(Image.fromarray((np.random.default_rng(3).random((TH // 8, TW // 8)) * 255).astype(np.uint8)).resize((TW, TH), Image.BICUBIC)).astype(np.float32) / 255
snow = np.clip(snow * (0.9 + 0.2 * noise), 0, 1)
snowc = np.array([244, 247, 252], np.float32)
detail = (lum - lum.mean()) * 55  # keep a hint of ground texture under snow
snow_rgb = snowc[None, None, :] + detail[..., None] * .5
ground = o * np.array([0.78, 0.8, 0.86]) * 0.9
forest_rgb = np.array([30, 48, 40], np.float32)[None, None, :] * (0.55 + 1.6 * lum[..., None])
g = ground * (1 - forest[..., None]) + forest_rgb * forest[..., None]
w = g * (1 - snow[..., None]) + snow_rgb * snow[..., None]
w[water] = o[water] * np.array([0.55, 0.75, 0.9])
w = np.clip(w, 0, 255).astype(np.uint8)
Image.fromarray(w).save(f'{OUT}/winter.jpg', quality=80, optimize=True)

# ---------- vector data ----------
feats = json.load(open(f'{RAW}/feats.json'))

def densify(c, step=8.0):
    out = []
    for (a, b) in zip(c[:-1], c[1:]):
        ax, az = lonlat_to_xz(*a); bx, bz = lonlat_to_xz(*b)
        d = math.hypot(bx - ax, bz - az); n = max(1, int(d // step))
        for i in range(n):
            t = i / n; out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    out.append(tuple(c[-1]))
    return out

def line3d(c, step=8.0):
    pts = []
    for lon, lat in densify(c, step):
        x, z = lonlat_to_xz(lon, lat); pts.append((x, sample(lon, lat), z))
    return pts

def stats(p):
    # orient downhill
    if p[0][1] < p[-1][1]: p = p[::-1]
    d = [0.0]
    for a, b in zip(p[:-1], p[1:]):
        d.append(d[-1] + math.dist(a, b))
    hs = [q[1] for q in p]
    drop = max(hs) - min(hs)
    hd = sum(math.hypot(b[0] - a[0], b[2] - a[2]) for a, b in zip(p[:-1], p[1:])) or 1
    avg = math.degrees(math.atan2(hs[0] - hs[-1], hd)) if hs[0] > hs[-1] else math.degrees(math.atan2(drop, hd))
    mx = 0.0; j = 0
    for i in range(len(p)):
        while j < len(p) - 1 and d[j] - d[i] < 100: j += 1
        if d[j] - d[i] >= 60:
            hh = math.hypot(p[j][0] - p[i][0], p[j][2] - p[i][2]) or 1
            mx = max(mx, math.degrees(math.atan2(abs(p[i][1] - p[j][1]), hh)))
    # profile: 48 samples
    prof = []
    for k in range(48):
        t = d[-1] * k / 47
        i = min(range(len(d)), key=lambda ii: abs(d[ii] - t))
        prof.append(round(hs[i]))
    # aspect: direction of fall
    dx, dz = p[-1][0] - p[0][0], p[-1][2] - p[0][2]
    ang = (math.degrees(math.atan2(dx, -dz)) + 360) % 360
    aspect = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'][int((ang + 22.5) // 45) % 8]
    return p, dict(len=round(d[-1]), top=round(max(hs)), bot=round(min(hs)), drop=round(drop),
                   avg=round(avg, 1), max=round(mx, 1), prof=prof, aspect=aspect)

DIFF = {'novice': 'green', 'easy': 'blue', 'intermediate': 'red', 'advanced': 'black', 'expert': 'black', 'freeride': 'freeride'}
pistes = []
for f in feats:
    if f['k'] != 'piste': continue
    diff = DIFF.get(f['diff'], 'blue' if not f['diff'] else None)
    if diff is None: continue
    p, s = stats(line3d(f['c']))
    pistes.append(dict(id=f['id'], name=f['name'] or 'Sin nombre', diff=diff,
                       pts=[[round(a, 1), round(b, 1), round(c, 1)] for a, b, c in p], **s))

LIFT = {'chair_lift': 'Telesilla', 'drag_lift': 'Telesquí', 'magic_carpet': 'Cinta', 't-bar': 'Telesquí',
        'platter': 'Telesquí', 'gondola': 'Telecabina', 'rope_tow': 'Telecuerda'}
lifts = []
for f in feats:
    if f['k'] != 'lift': continue
    g = [(lonlat_to_xz(lon, lat), sample(lon, lat)) for lon, lat in (f['c'][0], f['c'][-1])]
    (x0, z0), h0 = g[0]; (x1, z1), h1 = g[1]
    if h0 > h1: (x0, z0, h0, x1, z1, h1) = (x1, z1, h1, x0, z0, h0)
    ground = [[round(x, 1), round(h, 1), round(z, 1)] for x, h, z in line3d([f['c'][0], f['c'][-1]], 25)]
    if ground[0][1] > ground[-1][1]: ground = ground[::-1]
    horiz = math.hypot(x1 - x0, z1 - z0)
    name = f['name'].replace('Telesquí ', '')
    lifts.append(dict(id=f['id'], name=name, type=f['type'], label=LIFT.get(f['type'], 'Remonte'),
                      seats=f['occupancy'], cap=f['cap'], a=[round(x0, 1), round(h0, 1), round(z0, 1)],
                      b=[round(x1, 1), round(h1, 1), round(z1, 1)], ground=ground,
                      len=round(math.hypot(horiz, h1 - h0)), drop=round(h1 - h0)))

def near_ski(x, z, r=150):
    for L in pistes:
        for q in L['pts'][::3]:
            if abs(q[0] - x) < r and abs(q[2] - z) < r and math.hypot(q[0] - x, q[2] - z) < r: return True
    for L in lifts:
        for q in (L['a'], L['b']):
            if math.hypot(q[0] - x, q[2] - z) < r: return True
    return False

pois = []
inside = lambda lon, lat: LON0 + .004 < lon < LON1 - .004 and LAT0 + .004 < lat < LAT1 - .004
for f in feats:
    lon, lat = f['c'][0]
    if not inside(lon, lat): continue
    x, z = lonlat_to_xz(lon, lat); h = sample(lon, lat)
    if f['k'] == 'peak':
        e = f['ele'].split('.')[0].replace(',', '') if f['ele'] else ''
        pois.append(dict(k='peak', name=f['name'], ele=int(e) if e.isdigit() else round(h), p=[round(x), round(h), round(z)]))
    elif f['k'] == 'food' and near_ski(x, z) and h > 1500:
        pois.append(dict(k='food', name=f['name'], amenity=f['amenity'], p=[round(x), round(h), round(z)]))
    elif f['k'] == 'place':
        pois.append(dict(k='place', name=f['name'], p=[round(x), round(h), round(z)]))
peaks = sorted([p for p in pois if p['k'] == 'peak'], key=lambda p: -p['ele'])[:16]
pois = [p for p in pois if p['k'] != 'peak'] + peaks
# Formigal village label (no place node inside OSM tiles)
fx, fz = lonlat_to_xz(-0.3605, 42.7755)
pois.append(dict(k='place', name='Formigal', p=[round(fx), round(sample(-0.3605, 42.7755)), round(fz)]))

def lift_by(name):
    return next((l for l in lifts if l['name'] == name), None)
SECT = [('Sextas', 'Sallent', 'a'), ('Tres Hombres', 'Furco', 'b'), ('Izas', 'Crestas', 'b'),
        ('Sarrios', 'Sarrios', 'a'), ('Anayet', 'Anayet', 'a'), ('Portalet', 'Batallero', 'a')]
sectors = []
for label, ln, end in SECT:
    l = lift_by(ln)
    if l: sectors.append(dict(name=label, p=l[end]))

data = dict(bbox=[LON0, LAT0, LON1, LAT1], size=[W_M, H_M], grid=[GW, GH], tex=[TW, TH],
            hmin=float(dem.min()), hmax=float(dem.max()), pistes=pistes, lifts=lifts, pois=pois, sectors=sectors)
json.dump(data, open(f'{OUT}/data.json', 'w'), ensure_ascii=False, separators=(',', ':'))
from collections import Counter
print('pistes', len(pistes), Counter(p['diff'] for p in pistes), 'lifts', len(lifts), 'pois', Counter(p['k'] for p in pois))
for f in os.listdir(OUT): print(f, os.path.getsize(f'{OUT}/{f}'))
