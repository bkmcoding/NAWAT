"""USGS FireMon dNBR severity classes and area summaries.

The breaks follow the USGS FireMon table: high/low post-fire regrowth at
-0.25 and -0.1, unburned from -0.1 to 0.1, then the 0.1/0.27/0.44/0.66
burn-severity breaks, with high severity above 0.66. They are spectral
indices, not field-validated severity measurements.
"""

from dataclasses import dataclass
from typing import Mapping

SQ_METERS_PER_ACRE = 4046.8564224


@dataclass(frozen=True)
class SeverityClass:
    key: str
    label: str
    color: str
    min_dnbr: float | None  # inclusive
    max_dnbr: float | None  # exclusive

    def contains(self, value: float) -> bool:
        if self.min_dnbr is not None and value < self.min_dnbr:
            return False
        if self.max_dnbr is not None and value >= self.max_dnbr:
            return False
        return True


# Order matters for display and for the EE masks built in main.py.
SEVERITY_CLASSES: tuple[SeverityClass, ...] = (
    SeverityClass("regrowth_high", "Regrowth (high)", "#006837", None, -0.25),
    SeverityClass("regrowth_low", "Regrowth (low)", "#1a9641", -0.25, -0.1),
    SeverityClass("unburned", "Unburned", "#a6d96a", -0.1, 0.1),
    SeverityClass("low", "Low", "#ffffbf", 0.1, 0.27),
    SeverityClass("moderate_low", "Moderate-low", "#fdae61", 0.27, 0.44),
    SeverityClass("moderate_high", "Moderate-high", "#f46d43", 0.44, 0.66),
    SeverityClass("high", "High", "#d73027", 0.66, None),
)

HIGH_SEVERITY_KEYS = ("high",)


def build_severity_summary(
    areas_m2: Mapping[str, float | None], total_acres: float
) -> tuple[list[dict], float, float]:
    """Convert per-class square metres into API rows plus high-severity totals."""
    rows: list[dict] = []
    raw_acres: dict[str, float] = {}

    for cls in SEVERITY_CLASSES:
        value = areas_m2.get(cls.key) or 0.0
        acres = float(value) / SQ_METERS_PER_ACRE
        raw_acres[cls.key] = acres
        rows.append(
            {
                "key": cls.key,
                "label": cls.label,
                "color": cls.color,
                "min_dnbr": cls.min_dnbr,
                "max_dnbr": cls.max_dnbr,
                "acres": round(acres, 2),
                "pct_of_area": round(acres / total_acres * 100, 2) if total_acres else 0.0,
            }
        )

    valid_acres = sum(raw_acres.values())
    for row in rows:
        row["pct_of_valid"] = (
            round(raw_acres[row["key"]] / valid_acres * 100, 2) if valid_acres else 0.0
        )

    high_acres = sum(raw_acres[key] for key in HIGH_SEVERITY_KEYS)
    return rows, high_acres, valid_acres
