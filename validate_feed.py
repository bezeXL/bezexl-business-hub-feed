#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


REQUIRED = {"item_id", "title", "description", "url", "brand", "seller_name", "image_url", "availability", "price", "target_countries", "store_country"}


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/openai-products.csv")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("Feed boş")
    missing_columns = REQUIRED - set(rows[0])
    if missing_columns:
        raise SystemExit(f"Eksik sütunlar: {sorted(missing_columns)}")
    ids: set[str] = set()
    errors: list[str] = []
    for line, row in enumerate(rows, 2):
        missing = [name for name in REQUIRED if not row.get(name, "").strip()]
        if missing:
            errors.append(f"satır {line}: boş alan {','.join(missing)}")
        item_id = row.get("item_id", "")
        if item_id in ids:
            errors.append(f"satır {line}: yinelenen item_id")
        ids.add(item_id)
        if row.get("availability") not in {"in_stock", "out_of_stock", "pre_order", "backorder", "unknown"}:
            errors.append(f"satır {line}: geçersiz availability")
        if row.get("price") and not re.fullmatch(r"\d+(?:\.\d{1,2})? [A-Z]{3}", row["price"]):
            errors.append(f"satır {line}: geçersiz fiyat")
        try:
            json.loads(row.get("target_countries", ""))
        except json.JSONDecodeError:
            errors.append(f"satır {line}: geçersiz target_countries")
    if errors:
        raise SystemExit("\n".join(errors[:30]))
    print(f"Doğrulama başarılı: {len(rows)} benzersiz ürün/varyant")


if __name__ == "__main__":
    main()

