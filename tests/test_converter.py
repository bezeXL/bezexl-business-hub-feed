import csv
import tempfile
import unittest
from pathlib import Path

from converter import convert


class ConverterTest(unittest.TestCase):
    def test_variants_stock_and_prices(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "feed.csv"
            count = convert(Path("tests/fixture.xml"), output, site_url="https://www.bezexl.com", seller_name="BezeXL", target_countries=["TR"], store_country="TR")
            self.assertEqual(count, 2)
            with output.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["item_id"], "BZXL9802-FUME-44")
            self.assertEqual(rows[0]["group_id"], "5597")
            self.assertEqual(rows[0]["availability"], "in_stock")
            self.assertEqual(rows[1]["availability"], "out_of_stock")
            self.assertEqual(rows[0]["price"], "2700.00 TRY")
            self.assertEqual(rows[0]["sale_price"], "2090.00 TRY")
            self.assertIn('"beden":"44"', rows[0]["variant_dict"])


if __name__ == "__main__":
    unittest.main()
