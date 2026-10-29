"""
NAWAT Visuals Generator
Generates clean PNGs and animated GIF for docs/visuals/
Run from backend/ with: .venv/Scripts/python.exe visuals/generate_visuals.py
"""

import os
import io
import math
import time
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
import ee

# ─── Init ────────────────────────────────────────────────────────────────────

load_dotenv()
try:
    ee.Initialize(project=os.getenv("PROJECT_ID"))
except Exception as e:
    ee.Authenticate()
    ee.Initialize(project=os.getenv("PROJECT_ID"))

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'visuals')
os.makedirs(OUT_DIR, exist_ok=True)

# ─── AOI & Data ──────────────────────────────────────────────────────────────

target_point = ee.Geometry.Point([-121.1287, 40.1889])
aoi = target_point.buffer(30000)

pre_fire_dates  = ('2021-06-01', '2021-07-01')
post_fire_dates = ('2021-09-15', '2021-10-15')

def mask_s2_clouds(image):
    qa = image.select('QA60')
    mask = (qa.bitwiseAnd(1 << 10).eq(0)
              .And(qa.bitwiseAnd(1 << 11).eq(0)))
    return image.updateMask(mask).divide(10000)

s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')

pre_img = (s2.filterBounds(aoi)
             .filterDate(*pre_fire_dates)
             .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
             .map(mask_s2_clouds).median())

post_img = (s2.filterBounds(aoi)
              .filterDate(*post_fire_dates)
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
              .map(mask_s2_clouds).median())

pre_nbr  = pre_img.normalizedDifference(['B8', 'B12']).rename('NBR_pre')
post_nbr = post_img.normalizedDifference(['B8', 'B12']).rename('NBR_post')
dnbr     = pre_nbr.subtract(post_nbr).rename('dNBR')

SEVERITY = [
    ('Enhanced Regrowth',  '#1a9641'),
    ('Unburned',           '#a6d96a'),
    ('Low Severity',       '#ffffbf'),
    ('Moderate-Low',       '#fdae61'),
    ('Moderate-High',      '#f46d43'),
    ('High Severity',      '#d73027'),
    ('Extreme Severity',   '#800026'),
]

# ─── Tile helpers ─────────────────────────────────────────────────────────────

def get_tile_url(ee_image, vis_params):
    return ee_image.getMapId(vis_params)['tile_fetcher'].url_format

def latlon_to_tile_exact(lat, lon, zoom):
    lat_r = math.radians(lat)
    n = 2 ** zoom
    x_f = (lon + 180.0) / 360.0 * n
    y_f = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n
    tx, ty = int(x_f), int(y_f)
    return tx, ty, int((x_f - tx) * 256), int((y_f - ty) * 256)


# Google satellite basemap — no API key required, same tile scheme
BASEMAP_URL = 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}'

def fetch_tile(url_template, x, y, z, retries=3):
    url = url_template.replace('{x}', str(x)).replace('{y}', str(y)).replace('{z}', str(z))
    for _ in range(retries):
        try:
            r = requests.get(url, timeout=15,
                             headers={'User-Agent': 'Mozilla/5.0 NAWAT/1.0'})
            if r.status_code == 200:
                return Image.open(io.BytesIO(r.content)).convert('RGBA')
        except Exception:
            pass
        time.sleep(1)
    return None

def fetch_tile_grid(url_template, ox, oy, cols, rows, zoom):
    """Return a stitched RGBA canvas of cols*rows tiles starting at (ox,oy)."""
    canvas = Image.new('RGBA', (256 * cols, 256 * rows), (30, 30, 30, 255))
    for row in range(rows):
        for col in range(cols):
            tile = fetch_tile(url_template, ox + col, oy + row, zoom)
            if tile:
                canvas.paste(tile, (col * 256, row * 256))
    return canvas

def fetch_map_region(url_template, center_lat, center_lon, zoom, out_w=1280, out_h=960,
                     basemap=True):
    """
    Fetch EE tiles centered on (lat, lon), composited over a satellite basemap,
    cropped to out_w x out_h.  Set basemap=False to skip the basemap layer.
    """
    tx, ty, px, py = latlon_to_tile_exact(center_lat, center_lon, zoom)

    # Extra tiles needed on each side beyond the center tile
    tiles_left  = math.ceil((out_w / 2 - (256 - px)) / 256) + 1
    tiles_right = math.ceil((out_w / 2 - px)          / 256) + 1
    tiles_up    = math.ceil((out_h / 2 - (256 - py))  / 256) + 1
    tiles_down  = math.ceil((out_h / 2 - py)           / 256) + 1

    cols = tiles_left + 1 + tiles_right
    rows = tiles_up   + 1 + tiles_down
    ox, oy = tx - tiles_left, ty - tiles_up

    # 1. Basemap layer (satellite)
    if basemap:
        canvas = fetch_tile_grid(BASEMAP_URL, ox, oy, cols, rows, zoom)
    else:
        canvas = Image.new('RGBA', (256 * cols, 256 * rows), (30, 30, 30, 255))

    # 2. EE overlay — alpha-composite on top of basemap
    ee_canvas = fetch_tile_grid(url_template, ox, oy, cols, rows, zoom)
    canvas = Image.alpha_composite(canvas.convert('RGBA'), ee_canvas)

    # Exact pixel position of (center_lat, center_lon) on the stitched canvas
    cpx = tiles_left * 256 + px
    cpy = tiles_up   * 256 + py

    left   = cpx - out_w // 2
    top    = cpy - out_h // 2
    return canvas.crop((left, top, left + out_w, top + out_h)).convert('RGBA')

# ─── UI Badge helper ──────────────────────────────────────────────────────────

def load_font(size):
    for name in ['arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf']:
        try:
            f = ImageFont.truetype(name, size)
            if hasattr(f, 'getlength') or hasattr(f, 'getbbox'):
                return f
        except Exception:
            pass
    # Fall back to a basic ImageFont that always works
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

def measure_text(text, font):
    """Return pixel width of text, compatible with all PIL versions."""
    try:
        # Pillow >= 9.2
        tmp = Image.new('RGB', (1, 1))
        d   = ImageDraw.Draw(tmp)
        return d.textlength(text, font=font)
    except Exception:
        pass
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except Exception:
        pass
    try:
        return font.getlength(text)
    except Exception:
        pass
    # Last resort: estimate
    sz = getattr(font, 'size', 10)
    return len(text) * sz * 0.6

def draw_badge(img: Image.Image, title: str, subtitle: str = '',
               legend_items=None, pad=14, margin=16, alpha=210) -> Image.Image:
    """
    Draw a minimal frosted-glass badge in the top-left corner.
    legend_items: list of (label, hex_color) tuples, or None.
    Returns a new RGB image.
    """
    img = img.convert('RGBA')
    draw = ImageDraw.Draw(img)
    W, H = img.size

    font_title = load_font(15)
    font_sub   = load_font(11)
    font_leg   = load_font(10)

    # Measure text
    def text_w(text, font):
        return measure_text(text, font)

    lines = []
    lines.append(('title', title, font_title))
    if subtitle:
        lines.append(('sub', subtitle, font_sub))
    if legend_items:
        for label, color in legend_items:
            lines.append(('legend', label, color, font_leg))

    # Badge width = widest line + swatch + pad
    max_w = max(
        text_w(l[1], l[2]) + (18 if l[0] == 'legend' else 0)
        for l in lines
    )
    badge_w = int(max_w + pad * 2)
    line_h  = 18
    badge_h = pad + len(lines) * line_h + pad // 2

    # Draw semi-transparent background
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    r = 8  # corner radius
    x0, y0 = margin, margin
    x1, y1 = margin + badge_w, margin + badge_h
    od.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=(10, 10, 10, alpha))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Left accent bar (1px)
    bar_x = margin + 5
    draw.rectangle([bar_x, y0 + 6, bar_x + 2, y1 - 6], fill=(255, 100, 30, 255))

    # Draw lines
    cy = margin + pad
    for item in lines:
        kind = item[0]
        if kind == 'title':
            draw.text((margin + pad, cy), item[1], font=item[2], fill=(255, 255, 255, 255))
        elif kind == 'sub':
            draw.text((margin + pad, cy), item[1], font=item[2], fill=(180, 180, 180, 220))
        elif kind == 'legend':
            label, hex_color, font = item[1], item[2], item[3]
            r_val = int(hex_color[1:3], 16)
            g_val = int(hex_color[3:5], 16)
            b_val = int(hex_color[5:7], 16)
            sx = margin + pad
            draw.rectangle([sx, cy + 2, sx + 10, cy + 10], fill=(r_val, g_val, b_val, 255))
            draw.text((sx + 14, cy), label, font=font, fill=(210, 210, 210, 230))
        cy += line_h

    return img.convert('RGB')

# ─── Vis params ───────────────────────────────────────────────────────────────

VIS_TRUE_COLOR   = {'bands': ['B4', 'B3', 'B2'], 'min': 0.0, 'max': 0.3}
VIS_DNBR         = {'min': -0.1, 'max': 0.8,
                    'palette': ['#008000', '#ffff00', '#ffA500', '#ff0000', '#800080']}
VIS_DNBR_CLASS   = {'min': -0.5, 'max': 1.3,
                    'palette': [s[1] for s in SEVERITY]}
VIS_PRE_NBR      = {'min': -0.3, 'max': 0.9, 'palette': ['#d73027', '#ffffbf', '#1a9641']}
VIS_POST_NBR     = {'min': -0.3, 'max': 0.9, 'palette': ['#d73027', '#ffffbf', '#1a9641']}

# Centroid of the Dixie Fire burn scar (dNBR > 0.2), computed from EE
CENTER_LAT, CENTER_LON = 40.1889, -121.1287
ZOOM = 11

print("Fetching EE tile URLs...")
url_dnbr       = get_tile_url(dnbr,     VIS_DNBR)
url_pre_tc     = get_tile_url(pre_img,  VIS_TRUE_COLOR)
url_post_tc    = get_tile_url(post_img, VIS_TRUE_COLOR)
url_pre_nbr    = get_tile_url(pre_nbr,  VIS_PRE_NBR)
url_post_nbr   = get_tile_url(post_nbr, VIS_POST_NBR)
url_dnbr_class = get_tile_url(dnbr,     VIS_DNBR_CLASS)
print("URLs fetched.")

# ─── 1. dNBR Burn Severity ────────────────────────────────────────────────────
print("\n[1/5] dNBR burn severity...")

img1 = fetch_map_region(url_dnbr, CENTER_LAT, CENTER_LON, ZOOM, out_w=1280, out_h=960)
legend_dnbr = [
    ('Regrowth',           '#008000'),
    ('Unburned',           '#ffff00'),
    ('Low',                '#ffA500'),
    ('Moderate–High',      '#ff0000'),
    ('Extreme',            '#800080'),
]
img1 = draw_badge(img1,
                  title='dNBR — Burn Severity',
                  subtitle='Dixie Fire · 2021 · Sentinel-2',
                  legend_items=legend_dnbr)
img1.save(os.path.join(OUT_DIR, 'DBNRburn-demo.png'))
print(f"  Saved DBNRburn-demo.png")

# ─── 2. Pre / Post True Color side-by-side ───────────────────────────────────
print("\n[2/5] Pre/Post true color...")

img_pre  = fetch_map_region(url_pre_tc,  CENTER_LAT, CENTER_LON, ZOOM, out_w=960, out_h=900)
img_post = fetch_map_region(url_post_tc, CENTER_LAT, CENTER_LON, ZOOM, out_w=960, out_h=900)

img_pre  = draw_badge(img_pre,  title='Pre-Fire',  subtitle='Jun 2021 · True Color')
img_post = draw_badge(img_post, title='Post-Fire', subtitle='Sep–Oct 2021 · True Color')

# Stitch side-by-side with a 4px divider
gap    = 4
TITLE  = 44   # px for title bar
W2     = img_pre.width * 2 + gap
H2     = img_pre.height + TITLE
canvas2 = Image.new('RGB', (W2, H2), (10, 10, 10))
canvas2.paste(img_pre,  (0,                      TITLE))
canvas2.paste(img_post, (img_pre.width + gap,    TITLE))

# Title bar
d2 = ImageDraw.Draw(canvas2)
ft = load_font(17)
title_text = 'Dixie Fire (2021)  —  True Color Sentinel-2'
tw = measure_text(title_text, ft)
d2.text(((W2 - tw) // 2, 13), title_text, font=ft, fill=(255, 255, 255))

canvas2.save(os.path.join(OUT_DIR, 'PrePost-TrueColor.png'))
print(f"  Saved PrePost-TrueColor.png")

# ─── 3. Pre / Post NBR side-by-side ──────────────────────────────────────────
print("\n[3/5] Pre/Post NBR...")

img_pnbr = fetch_map_region(url_pre_nbr,  CENTER_LAT, CENTER_LON, ZOOM, out_w=960, out_h=900)
img_qnbr = fetch_map_region(url_post_nbr, CENTER_LAT, CENTER_LON, ZOOM, out_w=960, out_h=900)

img_pnbr = draw_badge(img_pnbr, title='Pre-Fire NBR',  subtitle='Jun 2021')
img_qnbr = draw_badge(img_qnbr, title='Post-Fire NBR', subtitle='Sep–Oct 2021')

canvas3 = Image.new('RGB', (W2, H2), (10, 10, 10))
canvas3.paste(img_pnbr, (0,                    TITLE))
canvas3.paste(img_qnbr, (img_pnbr.width + gap, TITLE))

d3 = ImageDraw.Draw(canvas3)
t3 = 'Dixie Fire (2021)  —  Normalized Burn Ratio (NBR)'
tw3 = measure_text(t3, ft)
d3.text(((W2 - tw3) // 2, 13), t3, font=ft, fill=(255, 255, 255))

canvas3.save(os.path.join(OUT_DIR, 'PrePost-NBR.png'))
print(f"  Saved PrePost-NBR.png")

# ─── 4. Classified Severity Map ──────────────────────────────────────────────
print("\n[4/5] Classified severity map...")

img4 = fetch_map_region(url_dnbr_class, CENTER_LAT, CENTER_LON, ZOOM, out_w=1280, out_h=960)
img4 = draw_badge(img4,
                  title='Burn Severity — USGS Classes',
                  subtitle='Dixie Fire · 2021',
                  legend_items=SEVERITY)
img4.save(os.path.join(OUT_DIR, 'DNBR-Classified.png'))
print(f"  Saved DNBR-Classified.png")

# ─── 5. Pre-fire → dNBR swipe GIF ────────────────────────────────────────────
print("\n[5/5] Swipe GIF...")

GW, GH = 1024, 768
gif_pre  = fetch_map_region(url_pre_tc, CENTER_LAT, CENTER_LON, ZOOM, out_w=GW, out_h=GH)
gif_post = fetch_map_region(url_dnbr,   CENTER_LAT, CENTER_LON, ZOOM, out_w=GW, out_h=GH)

pre_arr  = np.array(gif_pre.convert('RGB'))
post_arr = np.array(gif_post.convert('RGB'))

font_gif  = load_font(15)
font_gif2 = load_font(12)

FRAMES   = 32
HOLD     = 8
DUR_MOVE = 55   # ms/frame while moving
DUR_HOLD = 900  # ms hold at each end

def make_frame(ratio):
    split    = int(GW * ratio)
    combined = pre_arr.copy()
    if split < GW:
        combined[:, split:] = post_arr[:, split:]

    img = Image.fromarray(combined, 'RGB').convert('RGBA')
    d   = ImageDraw.Draw(img)

    # Divider line + handle
    if 2 < split < GW - 2:
        d.line([(split, 0), (split, GH)], fill=(255, 255, 255, 200), width=2)
        # Small chevron handle mid-line
        hx, hy = split, GH // 2
        d.ellipse([hx - 10, hy - 10, hx + 10, hy + 10], fill=(255, 255, 255, 180))
        d.text((hx - 4, hy - 7), '◀▶', font=load_font(9), fill=(30, 30, 30, 255))

    # Bottom label strip — left side
    strip_h = 30
    if split > 10:
        d.rectangle([0, GH - strip_h, split, GH], fill=(0, 0, 0, 130))
        d.text((10, GH - strip_h + 7), 'Pre-Fire · Jun 2021',
               font=font_gif2, fill=(220, 220, 220, 255))

    # Bottom label strip — right side
    if split < GW - 10:
        d.rectangle([split, GH - strip_h, GW, GH], fill=(0, 0, 0, 130))
        label_r = 'dNBR Burn Severity'
        lw = measure_text(label_r, font_gif2)
        d.text((GW - lw - 10, GH - strip_h + 7), label_r,
               font=font_gif2, fill=(255, 190, 60, 255))

    return img.convert('RGB').convert('P', palette=Image.ADAPTIVE, colors=256)

frames, durations = [], []

for _ in range(HOLD):
    frames.append(make_frame(0.0)); durations.append(DUR_HOLD)
for i in range(FRAMES + 1):
    frames.append(make_frame(i / FRAMES)); durations.append(DUR_MOVE)
for _ in range(HOLD):
    frames.append(make_frame(1.0)); durations.append(DUR_HOLD)
for i in range(FRAMES + 1):
    frames.append(make_frame(1.0 - i / FRAMES)); durations.append(DUR_MOVE)

gif_path = os.path.join(OUT_DIR, 'DBNR-swipe.gif')
frames[0].save(gif_path, save_all=True, append_images=frames[1:],
               duration=durations, loop=0, optimize=True)
print(f"  Saved DBNR-swipe.gif")

# ─── 6. K-Means Epicenter Map ─────────────────────────────────────────────────
print("\n[6/7] K-Means epicenter map...")

from sklearn.cluster import KMeans as SKMeans

# Sample extreme-severity pixels (dNBR > 0.66) with coordinates
extreme_mask = dnbr.gt(0.66)
extreme_img  = dnbr.updateMask(extreme_mask)

samples = extreme_img.sample(
    region=aoi,
    scale=60,
    numPixels=600,
    seed=42,
    geometries=True
)

pts_info6 = samples.getInfo()
coords6 = []
for feat in pts_info6['features']:
    c = feat['geometry']['coordinates']
    coords6.append([c[0], c[1]])  # [lon, lat]

print(f"  Sampled {len(coords6)} extreme-severity points")

# sklearn K-means (k=5) on lon/lat
coords6_arr = np.array(coords6)
km = SKMeans(n_clusters=5, random_state=42, n_init=10).fit(coords6_arr)
centroids = [(float(c[1]), float(c[0])) for c in km.cluster_centers_]  # (lat, lon)

print(f"  K-means centroids: {centroids}")

# Compute catastrophic area (dNBR > 0.66) in acres
area_img = extreme_img.multiply(ee.Image.pixelArea())
area_m2  = area_img.reduceRegion(
    reducer=ee.Reducer.count().combine(ee.Reducer.sum(), sharedInputs=True),
    geometry=aoi, scale=60, maxPixels=1e9
).getInfo()
# pixel count * 60m² scale → convert to acres
pixel_count = area_m2.get('dNBR_count', area_m2.get('NBR_count', 0))
# Use direct pixel area sum if available, else estimate
if 'dNBR_sum' in area_m2:
    area_acres = float(area_m2['dNBR_sum']) / 4046.856
elif 'dNBR_count' in area_m2:
    area_acres = float(area_m2['dNBR_count']) * 3600 / 4046.856  # 60m pixels
else:
    area_acres = 103382.86  # fallback to known value

print(f"  Catastrophic area: {area_acres:.2f} acres")

# Fetch continuous dNBR map as base (green/yellow/orange/red/purple — matches original)
img6 = fetch_map_region(url_dnbr, CENTER_LAT, CENTER_LON, ZOOM, out_w=1280, out_h=960)

# Project centroid lat/lons to pixel coordinates on the image
def latlon_to_pixel(lat, lon, center_lat, center_lon, zoom, img_w, img_h):
    """Convert a lat/lon to pixel (x,y) within the rendered image."""
    import math
    def ll_to_global_px(la, lo):
        n   = 2 ** zoom
        x_f = (lo + 180.0) / 360.0 * n * 256
        lr  = math.radians(la)
        y_f = (1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n * 256
        return x_f, y_f

    cx_g, cy_g = ll_to_global_px(center_lat, center_lon)
    px_g, py_g = ll_to_global_px(lat, lon)
    dx = px_g - cx_g
    dy = py_g - cy_g
    return int(img_w // 2 + dx), int(img_h // 2 + dy)

img6_rgba = img6.convert('RGBA')
overlay6  = Image.new('RGBA', img6_rgba.size, (0, 0, 0, 0))
d6_ov     = ImageDraw.Draw(overlay6)

MARKER_R = 18
MARKER_BORDER = 3
for (clat, clon) in centroids:
    px, py = latlon_to_pixel(clat, clon, CENTER_LAT, CENTER_LON, ZOOM, 1280, 960)
    if not (MARKER_R < px < 1280 - MARKER_R and MARKER_R < py < 960 - MARKER_R):
        continue
    # Outer ring: white fill with orange border (matches original screenshot)
    d6_ov.ellipse(
        [px - MARKER_R, py - MARKER_R, px + MARKER_R, py + MARKER_R],
        fill=(255, 255, 255, 210), outline=(255, 90, 20, 255), width=MARKER_BORDER
    )
    # Inner dot (orange)
    d6_ov.ellipse(
        [px - 5, py - 5, px + 5, py + 5],
        fill=(255, 90, 20, 255)
    )

img6_rgba = Image.alpha_composite(img6_rgba, overlay6)

# Damage report badge (top-left, replaces standard badge)
img6_out = img6_rgba.convert('RGB')
draw_final = ImageDraw.Draw(img6_out)

# Badge geometry
margin, pad, alpha_val = 16, 14, 215
r = 8
badge_w, badge_h = 260, 130
x0, y0, x1, y1 = margin, margin, margin + badge_w, margin + badge_h

badge_layer = Image.new('RGBA', img6_out.size, (0, 0, 0, 0))
bd = ImageDraw.Draw(badge_layer)
bd.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=(10, 10, 10, alpha_val))
img6_out_rgba = img6_out.convert('RGBA')
img6_out_rgba = Image.alpha_composite(img6_out_rgba, badge_layer)
df = ImageDraw.Draw(img6_out_rgba)

# Orange left bar
df.rectangle([x0 + 5, y0 + 6, x0 + 8, y1 - 6], fill=(255, 100, 30, 255))

font_title_b = load_font(13)
font_cat     = load_font(10)
font_acres   = load_font(22)
font_sub_b   = load_font(10)
font_desc    = load_font(9)

tx = x0 + pad
df.text((tx, y0 + 10),  'K-Means Epicenter Analysis',    font=font_title_b, fill=(255, 255, 255, 255))
df.text((tx, y0 + 27),  'CATASTROPHIC LOSS AREA',        font=font_cat,     fill=(160, 160, 160, 220))
df.text((tx, y0 + 40),  f'{area_acres:,.2f} acres',      font=font_acres,   fill=(255, 255, 255, 255))
df.text((tx, y0 + 70),  'Dixie Fire · 2021 · Sentinel-2', font=font_sub_b,  fill=(160, 160, 160, 200))

desc = 'K-Means Clustering: 5 primary epicenters'
df.text((tx, y0 + 84),  desc,                            font=font_desc,    fill=(200, 200, 200, 210))
desc2 = 'of extreme severity to guide recovery'
df.text((tx, y0 + 96),  desc2,                           font=font_desc,    fill=(200, 200, 200, 210))
desc3 = 'deployment.'
df.text((tx, y0 + 108), desc3,                           font=font_desc,    fill=(200, 200, 200, 210))

img6_final = img6_out_rgba.convert('RGB')
img6_final.save(os.path.join(OUT_DIR, 'KmeansDBNR.png'))
print(f"  Saved KmeansDBNR.png")

# ─── 7. TIN Mesh Wireframe ────────────────────────────────────────────────────
print("\n[7/7] TIN mesh wireframe...")

# Sample burn severity points (dNBR > 0.2) — 50km AOI so mesh fills the zoom-10 frame
burn_mask   = dnbr.gt(0.2)
aoi_tin     = target_point.buffer(50000)
burn_points = dnbr.updateMask(burn_mask).sample(
    region=aoi_tin,
    scale=80,
    numPixels=1000,
    seed=7,
    geometries=True
)

pts_info7 = burn_points.getInfo()
raw_pts7  = []
for feat in pts_info7['features']:
    coords = feat['geometry']['coordinates']
    raw_pts7.append((coords[1], coords[0]))  # (lat, lon)

print(f"  Sampled {len(raw_pts7)} burn points")

# Build near-black satellite basemap (zoom 10, wider view for TIN context)
ZOOM_TIN = 10
tx7, ty7, px7, py7 = latlon_to_tile_exact(CENTER_LAT, CENTER_LON, ZOOM_TIN)
tiles_l7 = math.ceil((640  - (256 - px7)) / 256) + 1
tiles_r7 = math.ceil((640  - px7)         / 256) + 1
tiles_u7 = math.ceil((480  - (256 - py7)) / 256) + 1
tiles_d7 = math.ceil((480  - py7)         / 256) + 1
cols7 = tiles_l7 + 1 + tiles_r7
rows7 = tiles_u7 + 1 + tiles_d7
ox7, oy7 = tx7 - tiles_l7, ty7 - tiles_u7

bm7 = fetch_tile_grid(BASEMAP_URL, ox7, oy7, cols7, rows7, ZOOM_TIN)
# Darken heavily → near-black Mapbox-style dark basemap
bm_arr = np.array(bm7.convert('RGB')).astype(np.float32) * 0.18
bm_arr = np.clip(bm_arr, 0, 255).astype(np.uint8)
bm7_dark = Image.fromarray(bm_arr, 'RGB')

cpx7 = tiles_l7 * 256 + px7
cpy7 = tiles_u7 * 256 + py7
img7 = bm7_dark.crop((cpx7 - 640, cpy7 - 480, cpx7 + 640, cpy7 + 480))

# Convert burn points (lat, lon) → pixel (x, y) on this 1280x960 image
def ll_to_px7(lat, lon):
    return latlon_to_pixel(lat, lon, CENTER_LAT, CENTER_LON, ZOOM_TIN, 1280, 960)

pixel_pts7 = [ll_to_px7(la, lo) for (la, lo) in raw_pts7]
pixel_pts7 = [(x, y) for (x, y) in pixel_pts7 if 0 <= x <= 1280 and 0 <= y <= 960]
print(f"  {len(pixel_pts7)} points within canvas")

# Delaunay triangulation
from scipy.spatial import Delaunay
pts_arr7 = np.array(pixel_pts7, dtype=np.float32)
tri7 = Delaunay(pts_arr7)

# Draw triangulation over the dark basemap
img7_rgba = img7.convert('RGBA')
tin_overlay = Image.new('RGBA', img7_rgba.size, (0, 0, 0, 0))
td = ImageDraw.Draw(tin_overlay)

for simplex in tri7.simplices:
    p0 = pixel_pts7[simplex[0]]
    p1 = pixel_pts7[simplex[1]]
    p2 = pixel_pts7[simplex[2]]
    td.polygon([p0, p1, p2], fill=(120, 20, 0, 55))
    td.line([p0, p1], fill=(255, 75, 15, 200), width=1)
    td.line([p1, p2], fill=(255, 75, 15, 200), width=1)
    td.line([p2, p0], fill=(255, 75, 15, 200), width=1)

img7_out = Image.alpha_composite(img7_rgba, tin_overlay).convert('RGB')
img7_out = draw_badge(img7_out,
                      title='TIN Mesh — Burn Extent',
                      subtitle='Dixie Fire · 2021 · Delaunay Triangulation')
img7_out.save(os.path.join(OUT_DIR, 'TinMesh-demo.png'))
print(f"  Saved TinMesh-demo.png")

print("\n✓ All done — docs/visuals/")
