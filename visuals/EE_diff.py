import os
from dotenv import load_dotenv
import ee
import geemap


load_dotenv()
try:
    ee.Initialize(project=os.getenv("PROJECT_ID"))
except Exception as e:
    ee.Authenticate()
    ee.Initialize(project=os.getenv("PROJECT_ID"))

# (Dixie Fire, CA)
target_point = ee.Geometry.Point([-121.3283, 40.0632])
aoi = target_point.buffer(30000) # 3 km

# define pre+post fire
pre_fire_dates = ('2021-06-01', '2021-07-01')
post_fire_dates = ('2021-09-15', '2021-10-15')


def mask_s2_clouds(image):
    qa = image.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0) \
        .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    
    return image.updateMask(mask).divide(10000)


s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')

pre_fire_img = s2.filterBounds(aoi) \
                 .filterDate(*pre_fire_dates) \
                 .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
                 .map(mask_s2_clouds) \
                 .median()

post_fire_img = s2.filterBounds(aoi) \
                  .filterDate(*post_fire_dates) \
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
                  .map(mask_s2_clouds) \
                  .median()

# Normalized Burn Ratio (NBR)
# Formula: (NIR - SWIR) / (NIR + SWIR)

pre_nbr = pre_fire_img.normalizedDifference(['B8', 'B12']).rename('NBR_pre')
post_nbr = post_fire_img.normalizedDifference(['B8', 'B12']).rename('NBR_post')

dnbr = pre_nbr.subtract(post_nbr).rename('dNBR')
Swipe_Map = geemap.Map(center=[40.0632, -121.3283], zoom=10)

left_layer = geemap.ee_tile_layer(pre_fire_img, vis_params_true_color, 'Pre-Fire')
right_layer = geemap.ee_tile_layer(post_fire_img, vis_params_true_color, 'Post-Fire')

Swipe_Map.split_map(left_layer, right_layer)

Swipe_Map