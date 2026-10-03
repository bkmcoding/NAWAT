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
    cloud_mask = 1 << 10
    cirrus_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_mask).eq(0).And(qa.bitwiseAnd(cirrus_mask).eq(0))
    return image.updateMask(mask).divide(10000)

@app.post("/api/analyze-fire")
async def analyze_fire(req: FireAnalysisRequest):
    try:
        target_point = ee.Geometry.Point([req.lng, req.lat])
        aoi = target_point.buffer(req.radius_meters)
        
        # Data for Burn Severity
        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        pre_img = s2.filterBounds(aoi).filterDate(req.pre_fire_start, req.pre_fire_end).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).map(mask_s2_clouds).median()
        post_img = s2.filterBounds(aoi).filterDate(req.post_fire_start, req.post_fire_end).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).map(mask_s2_clouds).median()

        pre_nbr = pre_img.normalizedDifference(['B8', 'B12'])
        post_nbr = post_img.normalizedDifference(['B8', 'B12'])
        dnbr = pre_nbr.subtract(post_nbr).rename('dNBR')

        # Elevation
        dem = ee.Image('USGS/SRTMGL1_003').clip(aoi)
        slope = ee.Terrain.slope(dem)

        # Burn Layer
        vis_dnbr = {'min': -0.1, 'max': 0.8, 'palette': ['#008000', '#ffff00', '#ffA500', '#ff0000', '#800080']}
        dnbr_tile = ee.Image(dnbr).getMapId(vis_dnbr)['tile_fetcher'].url_format
        
        # Slope Layer
        vis_slope = {'min': 0, 'max': 45, 'palette': ['#2b83ba', '#abdda4', '#ffffbf', '#fdae61', '#d7191c']}
        slope_tile = ee.Image(slope).getMapId(vis_slope)['tile_fetcher'].url_format

        high_severity_mask = dnbr.gt(0.66)
        
        def calculate_acres(condition_mask):
            """Helper function to calculate acreage of a given boolean mask"""
            area_img = condition_mask.multiply(ee.Image.pixelArea()).rename('area')
            stats = area_img.reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=aoi,
                scale=30, 
                maxPixels=1e10
            ).getInfo()
            return round(stats.get('area', 0) / 4046.86, 2) # Convert sq meters to acres

        # Bin the severe damage by slope steepness
        flat_acres = calculate_acres(high_severity_mask.And(slope.lte(10)))
        moderate_acres = calculate_acres(high_severity_mask.And(slope.gt(10)).And(slope.lte(25)))
        steep_acres = calculate_acres(high_severity_mask.And(slope.gt(25)))

        return {
            "status": "success",
            "center": [req.lng, req.lat],
            "tiles": {
                "burn_severity": dnbr_tile,
                "topography_slope": slope_tile
            },
            "metrics": {
                "total_catastrophic_acres": flat_acres + moderate_acres + steep_acres,
                "terrain_correlation": {
                    "flat_0_to_10_deg": flat_acres,
                    "moderate_10_to_25_deg": moderate_acres,
                    "steep_25_plus_deg": steep_acres
                }
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))