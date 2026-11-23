#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
import urllib.request
from pathlib import Path

from converter import convert


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Eksik ayar: {name}")
    return value


def main() -> None:
    source_url = required("TICIMAX_XML_URL")
    output = Path(os.environ.get("OUTPUT_PATH", "docs/openai-products.csv"))
    request = urllib.request.Request(source_url, headers={"User-Agent": "BezeXL-OpenAI-Feed/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if len(data) < 100 or b"<" not in data[:500]:
        raise SystemExit("XML kaynağı geçerli görünmüyor")
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as handle:
        handle.write(data)
        temp_path = Path(handle.name)
    try:
        count = convert(
            temp_path,
            output,
            site_url=os.environ.get("SITE_URL", "https://www.bezexl.com"),
            seller_name=os.environ.get("SELLER_NAME", "BezeXL"),
            target_countries=[x.strip().upper() for x in os.environ.get("TARGET_COUNTRIES", "TR").split(",") if x.strip()],
            store_country=os.environ.get("STORE_COUNTRY", "TR").upper(),
        )
        print(f"Üretilen ürün satırı: {count}")
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

