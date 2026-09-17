import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import ee

load_dotenv()

try:
    ee.Initialize(project=os.getenv("PROJECT_ID"))
except Exception as e:
    ee.Authenticate()
    ee.Initialize(project=os.getenv("PROJECT_ID"))

app = FastAPI(title="NAWAT")

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

        # Pre-fire composite
        pre_fire_img = s2.filterBounds(aoi) \
                         .filterDate(req.pre_fire_start, req.pre_fire_end) \
                         .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
                         .map(mask_s2_clouds) \
                         .median()

        # Post-fire composite
        post_fire_img = s2.filterBounds(aoi) \
                          .filterDate(req.post_fire_start, req.post_fire_end) \
                          .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
                          .map(mask_s2_clouds) \
                          .median()

        # Calculate NBR and dNBR
        pre_nbr = pre_fire_img.normalizedDifference(['B8', 'B12']).rename('NBR_pre')
        post_nbr = post_fire_img.normalizedDifference(['B8', 'B12']).rename('NBR_post')
        dnbr = pre_nbr.subtract(post_nbr).rename('dNBR')

        vis_params_dnbr = {
            'min': -0.1,
            'max': 0.8,
            'palette': ['#008000', '#ffff00', '#ffA500', '#ff0000', '#800080']
        }
        
        map_id_dict = ee.Image(dnbr).getMapId(vis_params_dnbr)
        tile_url = map_id_dict['tile_fetcher'].url_format
        
        # severe_burn_mask = dnbr.gt(0.27)
        # vectors = severe_burn_mask.reduceToVectors(
        #     geometry=aoi, 
        #     crs=dnbr.projection(), 
        #     scale=20, 
        #     geometryType='polygon',
        #     eightConnected=False
        # ).getInfo() 

        return {
            "status": "success",
            "center": [req.lng, req.lat],
            "tile_url": tile_url,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))