#!/usr/bin/env python3
"""Convert a Ticimax XML export to an OpenAI Business Hub CSV feed.

The XML URL is read from the environment by fetch_and_convert.py.  This module
never contains or logs the source URL.
"""

from __future__ import annotations

import csv
import html
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


OUTPUT_FIELDS = [
    "item_id", "group_id", "listing_has_variations", "variant_dict",
    "title", "description", "url", "brand", "seller_name", "image_url",
    "additional_image_urls", "availability", "price", "sale_price",
    "condition", "product_category", "color", "size", "gender", "age_group",
    "gtin", "mpn", "is_eligible_search", "target_countries", "store_country",
]


ALIASES = {
    "item_id": ["urunid", "urundetayid", "varyasyonid", "stokid", "id"],
    "group_id": ["urunkartiid", "urungrupid", "modelkodu", "itemgroupid"],
    "sku": ["varyasyonkodu", "stokkodu", "sku", "urunkodu"],
    "gtin": ["barkod", "barcode", "gtin", "ean"],
    "title": ["urunadi", "urunable", "baslik", "title", "name"],
    "description": ["aciklama", "detay", "urundetayi", "description", "onyazi"],
    "url": ["urunurl", "urunlink", "link", "url", "seo_url", "seourl"],
    "brand": ["marka", "brand", "uretici"],
    "stock": ["stokadedi", "stok", "stock", "quantity", "miktar"],
    "price": ["satisfiyati", "fiyat", "price", "piyasafiyati"],
    "sale_price": ["indirimlifiyat", "indirimlifiyati", "saleprice", "ozelfiyat"],
    "currency": ["parabirimi", "currency", "doviz"],
    "image": ["resim", "resimurl", "image", "imageurl", "gorsel", "anagorsel"],
    "category": ["breadcrumbkat", "kategori", "category", "adwordskategori"],
    "variant": ["varyasyon", "varyant", "variant", "secenekler", "options"],
    "color": ["renk", "color"],
    "size": ["beden", "size"],
    "active": ["urunaktif", "kartaktif", "aktif", "active"],
}


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def first(record: dict[str, str], field: str) -> str:
    for alias in ALIASES[field]:
        value = record.get(norm(alias), "").strip()
        if value:
            return value
    return ""


def decimal_value(value: str) -> Decimal | None:
    raw = re.sub(r"[^0-9,.-]", "", value or "").strip()
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def money(value: str, currency: str) -> str:
    amount = decimal_value(value)
    if amount is None or amount <= 0:
        return ""
    code = clean_text(currency).upper() or "TRY"
    code = {"TL": "TRY", "₺": "TRY", "TURK LIRASI": "TRY"}.get(code, code)
    if not re.fullmatch(r"[A-Z]{3}", code):
        code = "TRY"
    return f"{amount.quantize(Decimal('0.01'))} {code}"


def absolute_url(value: str, site_url: str) -> str:
    value = value.strip()
    if value.startswith(("https://", "http://")):
        return value
    if not value:
        return ""
    return f"{site_url.rstrip('/')}/{value.lstrip('/')}"


def flatten(node: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for child in node.iter():
        if child is node:
            continue
        key = norm(child.tag.split("}")[-1])
        value = clean_text(child.text)
        if value and key not in result:
            result[key] = value
        for attr, attr_value in child.attrib.items():
            attr_key = norm(f"{child.tag}_{attr}")
            if attr_value and attr_key not in result:
                result[attr_key] = clean_text(attr_value)
    for attr, value in node.attrib.items():
        result.setdefault(norm(attr), clean_text(value))
    return result


def product_nodes(root: ET.Element) -> list[ET.Element]:
    candidates: list[ET.Element] = []
    for node in root.iter():
        children = list(node)
        if not children:
            continue
        keys = {norm(c.tag.split("}")[-1]) for c in children}
        score = sum(any(alias in keys for alias in ALIASES[name]) for name in ("title", "price", "stock", "item_id", "sku"))
        if score >= 3:
            candidates.append(node)
    if not candidates:
        raise ValueError("XML içinde ürün kayıtları bulunamadı")
    # Prefer the repeated tag with the strongest population.
    counts: dict[str, int] = {}
    for node in candidates:
        tag = norm(node.tag.split("}")[-1])
        counts[tag] = counts.get(tag, 0) + 1
    best = max(counts, key=counts.get)
    return [node for node in candidates if norm(node.tag.split("}")[-1]) == best]


def variant_values(raw: str, explicit_color: str, explicit_size: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in re.split(r"[|;,]", raw or ""):
        if ":" in part:
            key, value = part.split(":", 1)
        elif "=" in part:
            key, value = part.split("=", 1)
        else:
            bits = part.strip().split(None, 1)
            if len(bits) != 2:
                continue
            key, value = bits
        if clean_text(key) and clean_text(value):
            values[clean_text(key).lower()] = clean_text(value)
    if explicit_color:
        values.setdefault("color", clean_text(explicit_color))
    if explicit_size:
        values.setdefault("size", clean_text(explicit_size))
    return values


def convert(xml_path: Path, output_path: Path, *, site_url: str, seller_name: str,
            target_countries: list[str], store_country: str) -> int:
    root = ET.parse(xml_path).getroot()
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for node in product_nodes(root):
        record = flatten(node)
        if first(record, "active").lower() in {"0", "false", "hayir", "pasif"}:
            continue
        sku = first(record, "sku")
        source_id = first(record, "item_id")
        item_id = sku or source_id or first(record, "gtin")
        if not item_id or item_id in seen:
            if source_id and item_id:
                item_id = f"{item_id}-{source_id}"
            else:
                continue
        seen.add(item_id)
        group_id = first(record, "group_id") or item_id
        title = clean_text(first(record, "title"))[:150]
        description = clean_text(first(record, "description"))[:5000] or title
        stock = decimal_value(first(record, "stock"))
        currency = first(record, "currency") or "TRY"
        regular = money(first(record, "price"), currency)
        sale = money(first(record, "sale_price"), currency)
        if sale and regular:
            if decimal_value(sale) is None or decimal_value(regular) is None or decimal_value(sale) >= decimal_value(regular):
                sale = ""
        color = first(record, "color")
        size = first(record, "size")
        variants = variant_values(first(record, "variant"), color, size)
        image_values = [v for k, v in record.items() if any(t in k for t in ("resim", "image", "gorsel")) and v]
        images = []
        for value in image_values:
            for part in re.split(r"[|;,]", value):
                url = absolute_url(part, site_url)
                if url.startswith(("https://", "http://")) and url not in images:
                    images.append(url)
        url = absolute_url(first(record, "url"), site_url)
        if not url and source_id:
            url = f"{site_url.rstrip('/')}/urun-{source_id}"
        row = {
            "item_id": item_id,
            "group_id": group_id if variants and group_id != item_id else "",
            "listing_has_variations": "true" if variants and group_id != item_id else "",
            "variant_dict": json.dumps(variants, ensure_ascii=False, separators=(",", ":")) if variants and group_id != item_id else "",
            "title": title,
            "description": description,
            "url": url,
            "brand": clean_text(first(record, "brand")) or seller_name,
            "seller_name": seller_name,
            "image_url": images[0] if images else "",
            "additional_image_urls": ",".join(images[1:]),
            "availability": "in_stock" if stock is not None and stock > 0 else "out_of_stock",
            "price": regular,
            "sale_price": sale,
            "condition": "new",
            "product_category": clean_text(first(record, "category")),
            "color": clean_text(color),
            "size": clean_text(size),
            "gender": "female",
            "age_group": "adult",
            "gtin": re.sub(r"\D", "", first(record, "gtin")),
            "mpn": sku,
            "is_eligible_search": "true",
            "target_countries": json.dumps(target_countries, separators=(",", ":")),
            "store_country": store_country,
        }
        required = ("item_id", "title", "description", "url", "brand", "seller_name", "image_url", "availability", "price")
        if all(row[name] for name in required):
            rows.append(row)
    if not rows:
        raise ValueError("Geçerli OpenAI ürün satırı üretilemedi")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)

