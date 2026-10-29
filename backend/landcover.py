"""Pre-fire land-cover classes and summaries from ESA WorldCover 2020.

WorldCover 2020 is used instead of a 2021 map so the classes describe
pre-fire conditions for the catalog's 2021-2022 fires. The source is 10 m
imagery, summarized here at 30 m to match the rest of the analysis.
"""

from dataclasses import dataclass
from typing import Mapping

from severity import SQ_METERS_PER_ACRE

LANDCOVER_SOURCE = "ESA WorldCover 2020 (v100)"
LANDCOVER_YEAR = 2020
LANDCOVER_SCALE_M = 30
LANDCOVER_SOURCE_URL = "https://esa-worldcover.org/en/data-access"


@dataclass(frozen=True)
class LandCoverClass:
    value: int
    key: str
    label: str
    color: str


# Official ESA WorldCover class values and palette.
LAND_COVER_CLASSES: tuple[LandCoverClass, ...] = (
    LandCoverClass(10, "tree_cover", "Tree cover", "#006400"),
    LandCoverClass(20, "shrubland", "Shrubland", "#ffbb22"),
    LandCoverClass(30, "grassland", "Grassland", "#ffff4c"),
    LandCoverClass(40, "cropland", "Cropland", "#f096ff"),
    LandCoverClass(50, "built_up", "Built-up", "#fa0000"),
    LandCoverClass(60, "bare_sparse", "Bare / sparse", "#b4b4b4"),
    LandCoverClass(70, "snow_ice", "Snow / ice", "#f0f0f0"),
    LandCoverClass(80, "water", "Water", "#0064c8"),
    LandCoverClass(90, "wetland", "Herbaceous wetland", "#0096a0"),
    LandCoverClass(95, "mangroves", "Mangroves", "#00cf75"),
    LandCoverClass(100, "moss_lichen", "Moss / lichen", "#fae6a0"),
)


def build_landcover_summary(
    areas_m2: Mapping[str, float | None],
    high_areas_m2: Mapping[str, float | None],
    total_acres: float,
) -> tuple[list[dict], float]:
    """Convert per-class square metres into API rows and high-severity totals."""
    rows: list[dict] = []
    high_total_m2 = 0.0

    for cls in LAND_COVER_CLASSES:
        area = float(areas_m2.get(cls.key) or 0.0)
        high_area = float(high_areas_m2.get(cls.key) or 0.0)
        high_total_m2 += high_area
        acres = area / SQ_METERS_PER_ACRE
        high_acres = high_area / SQ_METERS_PER_ACRE
        rows.append(
            {
                "key": cls.key,
                "label": cls.label,
                "color": cls.color,
                "acres": round(acres, 2),
                "pct_of_area": (
                    round(acres / total_acres * 100, 2) if total_acres else 0.0
                ),
                "high_severity_acres": round(high_acres, 2),
                "pct_of_high": 0.0,
            }
        )

    high_total_acres = high_total_m2 / SQ_METERS_PER_ACRE
    for row in rows:
        row["pct_of_high"] = (
            round(row["high_severity_acres"] / high_total_acres * 100, 2)
            if high_total_acres
            else 0.0
        )

    return rows, high_total_acres
