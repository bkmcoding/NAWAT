import unittest

from landcover import LAND_COVER_CLASSES, build_landcover_summary
from severity import SQ_METERS_PER_ACRE


class LandCoverClassTest(unittest.TestCase):
    def test_keys_and_values_are_unique(self):
        keys = [cls.key for cls in LAND_COVER_CLASSES]
        values = [cls.value for cls in LAND_COVER_CLASSES]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(values), len(set(values)))

    def test_rows_cover_every_class(self):
        rows, high_total = build_landcover_summary({}, {}, total_acres=0.0)
        self.assertEqual(len(rows), len(LAND_COVER_CLASSES))
        self.assertEqual(high_total, 0.0)
        self.assertTrue(all(row["pct_of_area"] == 0.0 for row in rows))
        self.assertTrue(all(row["pct_of_high"] == 0.0 for row in rows))


class LandCoverSummaryTest(unittest.TestCase):
    def test_all_class_and_high_severity_shares(self):
        class_count = len(LAND_COVER_CLASSES)
        areas = {cls.key: SQ_METERS_PER_ACRE for cls in LAND_COVER_CLASSES}
        high_areas = {cls.key: 0.0 for cls in LAND_COVER_CLASSES}
        high_areas["tree_cover"] = 2 * SQ_METERS_PER_ACRE
        high_areas["shrubland"] = SQ_METERS_PER_ACRE

        rows, high_total = build_landcover_summary(
            areas, high_areas, total_acres=float(class_count)
        )

        self.assertAlmostEqual(high_total, 3.0)
        tree = next(row for row in rows if row["key"] == "tree_cover")
        shrub = next(row for row in rows if row["key"] == "shrubland")
        self.assertAlmostEqual(tree["pct_of_area"], 100 / class_count, places=2)
        self.assertAlmostEqual(tree["high_severity_acres"], 2.0)
        self.assertAlmostEqual(tree["pct_of_high"], 66.67, places=2)
        self.assertAlmostEqual(shrub["pct_of_high"], 33.33, places=2)

    def test_none_values_are_treated_as_zero(self):
        areas = {cls.key: None for cls in LAND_COVER_CLASSES}
        high_areas = {cls.key: None for cls in LAND_COVER_CLASSES}
        rows, high_total = build_landcover_summary(
            areas, high_areas, total_acres=100.0
        )
        self.assertEqual(high_total, 0.0)
        self.assertTrue(all(row["acres"] == 0.0 for row in rows))


if __name__ == "__main__":
    unittest.main()
