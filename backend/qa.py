"""Build human-readable data-quality warnings for an analysis response."""

from datetime import date


def build_warnings(
    fire: dict | None,
    pre_window: tuple[date, date],
    post_window: tuple[date, date],
    pre_count: int,
    post_count: int,
    pre_cloud: float | None,
    post_cloud: float | None,
    valid_pct: float,
) -> list[str]:
    warnings = []
    if fire:
        containment = date.fromisoformat(fire["containment_date"])
        if post_window[1] < containment:
            warnings.append(
                f"Post-fire window ends {post_window[1].isoformat()}, before containment "
                f"on {fire['containment_date']}; severity may be underestimated."
            )
    if valid_pct < 90:
        warnings.append(
            f"Only {valid_pct:.1f}% of the area has valid dNBR data; interpret with caution."
        )
    if pre_cloud is not None and pre_cloud > 50:
        warnings.append(f"Pre-fire scenes average {pre_cloud:.1f}% cloud cover.")
    if post_cloud is not None and post_cloud > 50:
        warnings.append(f"Post-fire scenes average {post_cloud:.1f}% cloud cover.")
    if pre_count < 2 or post_count < 2:
        warnings.append(
            "Fewer than two scenes are available in one of the windows; the composite may be noisy."
        )
    return warnings
