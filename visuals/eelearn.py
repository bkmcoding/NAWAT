import os
from dotenv import load_dotenv
import ee
import geemap

load_dotenv()

ee.Authenticate()
ee.Initialize(project=os.getenv("PROJECT_ID"))

# NYC central park
point = ee.Geometry.Point([-73.9654, 40.7829])

dataset = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
           .filterBounds(point)
           .filterDate('2023-06-01', '2023-08-31')
           .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))

# Remember that median is needed to avoid clouds
image = dataset.median()

ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')

Map = geemap.Map(center=[40.7829, -73.9654], zoom=13)

rgb_vis = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}
Map.addLayer(image, rgb_vis, 'True Color Image')

ndvi_vis = {'min': 0, 'max': 0.8, 'palette': ['white', 'yellow', 'green', 'darkgreen']}
Map.addLayer(ndvi, ndvi_vis, 'NDVI (Plant Health)')

# jupyter notebook
Map