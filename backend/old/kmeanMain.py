import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ee
import numpy as np
from sklearn.cluster import KMeans

load_dotenv()

try:
    ee.Initialize(project=os.getenv("PROJECT_ID"))
except Exception as e:
    ee.Authenticate()
    ee.Initialize(project=os.getenv("PROJECT_ID"))

app = FastAPI(title="Wildfire Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class FireAnalysisRequest(BaseModel):
    lng: float = -121.3283
    lat: float = 40.0632
    radius_meters: int = 30000
    pre_fire_start: str = '2021-06-01'
    pre_fire_end: str = '2021-07-01'
    post_fire_start: str = '2021-09-15'
    post_fire_end: str = '2021-10-15'

def mask_s2_clouds(image):
    qa = image.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    return image.updateMask(mask).divide(10000)

@app.post("/api/analyze-fire")
async def analyze_fire(req: FireAnalysisRequest):
    try:
        target_point = ee.Geometry.Point([req.lng, req.lat])
        aoi = target_point.buffer(req.radius_meters)
        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')

        pre_fire_img = s2.filterBounds(aoi).filterDate(req.pre_fire_start, req.pre_fire_end).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).map(mask_s2_clouds).median()
        post_fire_img = s2.filterBounds(aoi).filterDate(req.post_fire_start, req.post_fire_end).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).map(mask_s2_clouds).median()

        pre_nbr = pre_fire_img.normalizedDifference(['B8', 'B12']).rename('NBR_pre')
        post_nbr = post_fire_img.normalizedDifference(['B8', 'B12']).rename('NBR_post')
        dnbr = pre_nbr.subtract(post_nbr).rename('dNBR')

        vis_params_dnbr = {'min': -0.1, 'max': 0.8, 'palette': ['#008000', '#ffff00', '#ffA500', '#ff0000', '#800080']}
        tile_url = ee.Image(dnbr).getMapId(vis_params_dnbr)['tile_fetcher'].url_format

        high_severity_mask = dnbr.gt(0.66) # Standard threshold for High Severity
        pixel_area = ee.Image.pixelArea()
        high_sev_area_img = high_severity_mask.multiply(pixel_area)
        
        area_stats = high_sev_area_img.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=aoi,
            scale=30,
            maxPixels=1e10
        ).getInfo()
        
        # Convert square meters to acres
        sq_meters = area_stats.get('dNBR', 0)
        acres = sq_meters / 4046.86

        masked_extreme = dnbr.updateMask(high_severity_mask)
        points = masked_extreme.sample(region=aoi, scale=400, geometries=True, numPixels=2000).getInfo()
        
        epicenters = []
        if points and 'features' in points and len(points['features']) > 5:
            coords = np.array([f['geometry']['coordinates'] for f in points['features']])
            
            # K-means on 5 major damage points
            kmeans = KMeans(n_clusters=5, random_state=42, n_init="auto").fit(coords)
            
            for center in kmeans.cluster_centers_:
                epicenters.append({"lng": center[0], "lat": center[1]})

        return {
            "status": "success",
            "center": [req.lng, req.lat],
            "tile_url": tile_url,
            "metrics": {
                "high_severity_acres": round(acres, 2),
                "epicenters": epicenters
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))