import os
import traceback
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import ee

import fires
from landcover import (
    LAND_COVER_CLASSES,
    LANDCOVER_SCALE_M,
    LANDCOVER_SOURCE,
    LANDCOVER_SOURCE_URL,
    LANDCOVER_YEAR,
    build_landcover_summary,
)
from qa import build_warnings
from severity import (
    SEVERITY_CLASSES,
    SQ_METERS_PER_ACRE,
    build_severity_summary,
)

load_dotenv()

try:
    ee.Initialize(project=os.getenv("PROJECT_ID"))
except Exception:
    ee.Authenticate()
    ee.Initialize(project=os.getenv("PROJECT_ID"))

app = FastAPI(title="Wildfire Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_PRE_WINDOW = ("2021-06-01", "2021-07-01")
DEFAULT_POST_WINDOW = ("2021-09-15", "2021-10-15")
CLOUD_FILTER_MAX = 20

VIS_DNBR = {
    "min": -0.1,
    "max": 0.8,
    "palette": ["#008000", "#ffff00", "#ffA500", "#ff0000", "#800080"],
}
VIS_SLOPE = {
    "min": 0,
    "max": 45,
    "palette": ["#2b83ba", "#abdda4", "#ffffbf", "#fdae61", "#d7191c"],
}


class FireAnalysisRequest(BaseModel):
    fire_id: str | None = None
    lng: float = -121.3283
    lat: float = 40.0632
    radius_meters: int = Field(default=30000, gt=0, le=100000)
    pre_fire_start: str | None = None
    pre_fire_end: str | None = None
    post_fire_start: str | None = None
    post_fire_end: str | None = None


def mask_s2_clouds(image):
    qa = image.select("QA60")
    cloud_mask = 1 << 10
    cirrus_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_mask).eq(0).And(qa.bitwiseAnd(cirrus_mask).eq(0))
    return image.updateMask(mask).divide(10000)


def parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be an ISO date (YYYY-MM-DD).",
        )


def resolve_window(
    start: str | None,
    end: str | None,
    default: tuple[str, str] | list[str],
    label: str,
) -> tuple[date, date]:
    start_date = parse_date(start or default[0], f"{label} start")
    end_date = parse_date(end or default[1], f"{label} end")
    if start_date >= end_date:
        raise HTTPException(
            status_code=400,
            detail=f"{label} start must be before its end.",
        )
    return start_date, end_date


def collection_qa(collection) -> tuple[int, float | None]:
    count = int(collection.size().getInfo())
    mean_cloud = None
    if count:
        value = collection.aggregate_mean("CLOUDY_PIXEL_PERCENTAGE").getInfo()
        if value is not None:
            mean_cloud = float(value)
    return count, mean_cloud


def severity_area_image(dnbr: ee.Image) -> ee.Image:
    """One band per USGS class, holding pixel area where the class applies."""
    pixel_area = ee.Image.pixelArea()
    bands = []
    for cls in SEVERITY_CLASSES:
        if cls.min_dnbr is None:
            mask = dnbr.lt(cls.max_dnbr)
        elif cls.max_dnbr is None:
            mask = dnbr.gte(cls.min_dnbr)
        else:
            mask = dnbr.gte(cls.min_dnbr).And(dnbr.lt(cls.max_dnbr))
        bands.append(mask.multiply(pixel_area).rename(cls.key))
    return ee.Image.cat(*bands)


def slope_area_image(dnbr: ee.Image, slope: ee.Image) -> ee.Image:
    """High severity split by slope band, as pixel-area bands."""
    pixel_area = ee.Image.pixelArea()
    high_severity = dnbr.gte(0.66)
    bands = [
        high_severity.And(slope.lte(10))
        .multiply(pixel_area)
        .rename("flat_0_to_10_deg"),
        high_severity.And(slope.gt(10)).And(slope.lte(25))
        .multiply(pixel_area)
        .rename("moderate_10_to_25_deg"),
        high_severity.And(slope.gt(25))
        .multiply(pixel_area)
        .rename("steep_25_plus_deg"),
    ]
    return ee.Image.cat(*bands)


def landcover_area_image(
    landcover: ee.Image, mask: ee.Image | None = None
) -> ee.Image:
    """One band per WorldCover class, holding pixel area where it applies."""
    if mask is not None:
        landcover = landcover.updateMask(mask)
    pixel_area = ee.Image.pixelArea()
    bands = [
        landcover.eq(cls.value).multiply(pixel_area).rename(cls.key)
        for cls in LAND_COVER_CLASSES
    ]
    return ee.Image.cat(*bands)


def reduce_areas(
    image: ee.Image, aoi: ee.Geometry, scale: int = 30
) -> dict[str, float]:
    values = image.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        scale=scale,
        maxPixels=1e10,
    ).getInfo()
    return {key: float(value or 0.0) for key, value in (values or {}).items()}


@app.get("/api/fires")
def list_fires():
    return {"fires": fires.list_fires()}


@app.post("/api/analyze-fire")
async def analyze_fire(req: FireAnalysisRequest):
    try:
        fire = None
        if req.fire_id:
            if not fires.has_fire(req.fire_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Unknown fire_id '{req.fire_id}'.",
                )
            fire = fires.fire_metadata(req.fire_id)
            feature = fires.load_feature(req.fire_id)
            aoi = ee.Geometry(feature["geometry"])
            area_acres = float(fire["acres"])
            center = fire["center"]
            default_pre = fire["pre_window"]
            default_post = fire["post_window"]
        else:
            target_point = ee.Geometry.Point([req.lng, req.lat])
            aoi = target_point.buffer(req.radius_meters)
            area_acres = float(aoi.area().divide(SQ_METERS_PER_ACRE).getInfo())
            center = [req.lng, req.lat]
            default_pre = DEFAULT_PRE_WINDOW
            default_post = DEFAULT_POST_WINDOW

        pre_start, pre_end = resolve_window(
            req.pre_fire_start, req.pre_fire_end, default_pre, "Pre-fire window"
        )
        post_start, post_end = resolve_window(
            req.post_fire_start, req.post_fire_end, default_post, "Post-fire window"
        )
        if pre_end > post_start:
            raise HTTPException(
                status_code=400,
                detail="Pre-fire window must end on or before the post-fire window starts.",
            )

        s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        pre_collection = (
            s2.filterBounds(aoi)
            .filterDate(pre_start.isoformat(), pre_end.isoformat())
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_FILTER_MAX))
        )
        post_collection = (
            s2.filterBounds(aoi)
            .filterDate(post_start.isoformat(), post_end.isoformat())
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_FILTER_MAX))
        )

        pre_count, pre_cloud = collection_qa(pre_collection)
        post_count, post_cloud = collection_qa(post_collection)
        if pre_count == 0 or post_count == 0:
            empty_window = "pre-fire" if pre_count == 0 else "post-fire"
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No Sentinel-2 scenes matched the {empty_window} window under "
                    f"the {CLOUD_FILTER_MAX}% cloud filter."
                ),
            )

        pre_image = pre_collection.map(mask_s2_clouds).median()
        post_image = post_collection.map(mask_s2_clouds).median()
        pre_nbr = pre_image.normalizedDifference(["B8", "B12"])
        post_nbr = post_image.normalizedDifference(["B8", "B12"])
        dnbr = pre_nbr.subtract(post_nbr).rename("dNBR")

        pre_ndvi = pre_image.normalizedDifference(["B8", "B4"]).rename("NDVI")
        ndvi_stats = (
            pre_ndvi.reduceRegion(
                reducer=ee.Reducer.mean().combine(
                    ee.Reducer.median(), sharedInputs=True
                ),
                geometry=aoi,
                scale=30,
                maxPixels=1e10,
                bestEffort=True,
            ).getInfo()
            or {}
        )

        dem = ee.Image("USGS/SRTMGL1_003")
        slope = ee.Terrain.slope(dem)

        dnbr_layer = dnbr.clip(aoi)
        slope_layer = slope.clip(aoi)
        dnbr_tile = dnbr_layer.getMapId(VIS_DNBR)["tile_fetcher"].url_format
        slope_tile = slope_layer.getMapId(VIS_SLOPE)["tile_fetcher"].url_format

        severity_areas = reduce_areas(severity_area_image(dnbr), aoi)
        slope_areas = reduce_areas(slope_area_image(dnbr, slope), aoi)

        landcover_image = (
            ee.ImageCollection("ESA/WorldCover/v100").first().select("Map")
        )
        landcover_areas = reduce_areas(
            landcover_area_image(landcover_image), aoi, LANDCOVER_SCALE_M
        )
        landcover_high_areas = reduce_areas(
            landcover_area_image(landcover_image, dnbr.gte(0.66)),
            aoi,
            LANDCOVER_SCALE_M,
        )
        landcover_rows, _high_landcover_acres = build_landcover_summary(
            landcover_areas, landcover_high_areas, area_acres
        )

        severity_rows, high_acres, valid_acres = build_severity_summary(
            severity_areas, area_acres
        )
        high_pct = (high_acres / area_acres * 100) if area_acres else 0.0
        valid_pct = (valid_acres / area_acres * 100) if area_acres else 0.0

        terrain = {
            "flat_0_to_10_deg": round(
                slope_areas.get("flat_0_to_10_deg", 0.0) / SQ_METERS_PER_ACRE, 2
            ),
            "moderate_10_to_25_deg": round(
                slope_areas.get("moderate_10_to_25_deg", 0.0)
                / SQ_METERS_PER_ACRE,
                2,
            ),
            "steep_25_plus_deg": round(
                slope_areas.get("steep_25_plus_deg", 0.0) / SQ_METERS_PER_ACRE, 2
            ),
        }

        warnings = build_warnings(
            fire,
            (pre_start, pre_end),
            (post_start, post_end),
            pre_count,
            post_count,
            pre_cloud,
            post_cloud,
            valid_pct,
        )

        return {
            "status": "success",
            "fire": fire,
            "center": center,
            "tiles": {
                "burn_severity": dnbr_tile,
                "topography_slope": slope_tile,
            },
            "landcover": {
                "source": LANDCOVER_SOURCE,
                "source_url": LANDCOVER_SOURCE_URL,
                "year": LANDCOVER_YEAR,
                "scale_m": LANDCOVER_SCALE_M,
                "classes": landcover_rows,
            },
            "metrics": {
                "high_severity_acres": round(high_acres, 2),
                "high_severity_pct_of_area": round(high_pct, 2),
                "valid_acres": round(valid_acres, 2),
                "valid_pct_of_area": round(valid_pct, 2),
                "terrain_correlation": terrain,
            },
            "severity": severity_rows,
            "qa": {
                "pre_scenes": pre_count,
                "post_scenes": post_count,
                "pre_mean_cloud_pct": (
                    round(pre_cloud, 1) if pre_cloud is not None else None
                ),
                "post_mean_cloud_pct": (
                    round(post_cloud, 1) if post_cloud is not None else None
                ),
                "pre_fire_ndvi_mean": (
                    round(float(ndvi_stats["NDVI_mean"]), 3)
                    if ndvi_stats.get("NDVI_mean") is not None
                    else None
                ),
                "pre_fire_ndvi_median": (
                    round(float(ndvi_stats["NDVI_median"]), 3)
                    if ndvi_stats.get("NDVI_median") is not None
                    else None
                ),
                "valid_pct_of_area": round(valid_pct, 2),
                "pre_window": [pre_start.isoformat(), pre_end.isoformat()],
                "post_window": [post_start.isoformat(), post_end.isoformat()],
                "cloud_filter_max_pct": CLOUD_FILTER_MAX,
            },
            "warnings": warnings,
        }

    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
