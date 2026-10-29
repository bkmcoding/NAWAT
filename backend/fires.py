"""Fire catalog backed by authoritative perimeters stored as GeoJSON.

Each file is a single GeoJSON Feature whose properties are the catalog entry.
Perimeters come from CAL FIRE FRAP's California Historic Fire Perimeters
service, repaired and simplified to 50 m; see each file's properties.
"""

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

_FILES = {
    "dixie-2021": DATA_DIR / "dixie_2021.geojson",
    "caldor-2021": DATA_DIR / "caldor_2021.geojson",
    "mosquito-2022": DATA_DIR / "mosquito_2022.geojson",
}

FIRE_IDS = tuple(_FILES)


def has_fire(fire_id: str) -> bool:
    return fire_id in _FILES


@lru_cache(maxsize=None)
def load_feature(fire_id: str) -> dict:
    """Return the full GeoJSON Feature for a known fire."""
    if fire_id not in _FILES:
        raise KeyError(fire_id)
    with _FILES[fire_id].open(encoding="utf-8") as handle:
        feature = json.load(handle)
    if feature.get("type") != "Feature" or "geometry" not in feature:
        raise ValueError(f"{_FILES[fire_id]} is not a GeoJSON Feature")
    return feature


def fire_metadata(fire_id: str) -> dict:
    """Return catalog metadata (no geometry) for a known fire."""
    props = load_feature(fire_id)["properties"]
    return {
        "id": props["fire_id"],
        "name": props["name"],
        "year": props["year"],
        "acres": props["official_acres"],
        "perimeter_acres": props["perimeter_acres"],
        "alarm_date": props["alarm_date"],
        "containment_date": props["containment_date"],
        "pre_window": props["pre_window"],
        "post_window": props["post_window"],
        "center": props["center"],
        "zoom": props["zoom"],
        "source": props["source"],
        "source_url": props["source_url"],
        "retrieved": props["retrieved"],
    }


def list_fires() -> list[dict]:
    return [fire_metadata(fire_id) for fire_id in FIRE_IDS]
