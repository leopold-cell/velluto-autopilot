#!/usr/bin/env python3
"""
Deploy the Strada Pro bundle test (theme files + draft products + test page)
to an UNPUBLISHED copy of the Velluto theme.

Modeled on velluto-seo-bot/scripts/deploy_theme.py (same Admin API mechanism,
same SHOPIFY_TOKEN / SHOPIFY_STORE env vars).

Usage:
  SHOPIFY_TOKEN=shpat_... python3 deploy_bundles.py --list-themes
  SHOPIFY_TOKEN=shpat_... python3 deploy_bundles.py --theme-id 123456789
  ... --theme-id 123 --skip-products      # theme files + page only
  ... --theme-id 123 --dry-run            # print what would happen

Safety:
  - Refuses to deploy to the published (live) theme.
  - Products are created as DRAFTS.
  - Existing products/pages with the same handle are left untouched.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SHOP = os.getenv("SHOPIFY_STORE", "velluto-brand.myshopify.com")
TOKEN = os.getenv("SHOPIFY_TOKEN", "")
API_VER = "2024-10"
STOREFRONT = "https://velluto-shop.com"

ROOT = Path(__file__).parent.parent

THEME_FILES = [
    "sections/velluto-bundle-landing.liquid",
    "sections/velluto-bundle-included-items.liquid",
    "snippets/velluto-bundle-color-swatches.liquid",
    "templates/page.velluto-bundles-test.json",
]

COLORS = ["nero", "arancia", "espresso", "viola"]
COLOR_LABELS = {"nero": "Nero", "arancia": "Arancia", "espresso": "Espresso", "viola": "Viola"}
# Imagery is reused from the existing StradaPro color products.
STRADA_HANDLES = {c: f"velluto-stradapro-cycling-glasses-{c}" for c in COLORS}

# Individual item values at current storefront prices (2026-06-10):
# glasses 149, Visione lens 39, clear lens 19, hard case 19, spray 8, cloth 8, bidon 14
SETS = {
    "starter": {
        "title": "Strada Pro Starter Set",
        "price": "69.00",
        "compare_at": "188.00",
        "items": ["Strada Pro", "Velluto Visione™ Lens"],
    },
    "performance": {
        "title": "Strada Pro Performance Set",
        "price": "99.00",
        "compare_at": "226.00",
        "items": ["Strada Pro", "Velluto Visione™ Lens", "Clear Lens", "Hard Case"],
    },
    "ultimate": {
        "title": "Strada Pro Ultimate Set",
        "price": "119.00",
        "compare_at": "256.00",
        "items": [
            "Strada Pro", "Velluto Visione™ Lens", "Clear Lens", "Hard Case",
            "Cleaning Spray", "Microfiber Cloth", "Bottle",
        ],
    },
}

PAGE = {
    "title": "Choose your Strada Pro setup (TEST)",
    "handle": "strada-pro-sets-test",
    "template_suffix": "velluto-bundles-test",
}


def api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"https://{SHOP}/admin/api/{API_VER}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-Shopify-Access-Token": TOKEN,
        "Content-Type": "application/json",
    })
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read() or "{}")
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited — Shopify REST is 2 req/s
                time.sleep(2 ** attempt)
                continue
            print(f"  ✗ {method} {path} → {e.code}: {e.read().decode()[:300]}")
            raise
    raise RuntimeError(f"rate-limited too long: {path}")


def storefront_json(path: str) -> dict:
    with urllib.request.urlopen(f"{STOREFRONT}{path}", timeout=30) as r:
        return json.loads(r.read())


def handle_for(set_key: str, color: str) -> str:
    return f"strada-pro-{set_key}-set-{color}"


def pick_theme(theme_id: str) -> dict:
    themes = api("GET", "/themes.json")["themes"]
    theme = next((t for t in themes if str(t["id"]) == str(theme_id)), None)
    if theme is None:
        sys.exit(f"Theme {theme_id} not found. Use --list-themes.")
    if theme["role"] == "main":
        sys.exit(f"Refusing to deploy: theme {theme_id} ({theme['name']!r}) is the LIVE theme.")
    return theme


def upload_theme_files(theme_id: str, dry: bool):
    print(f"\n— Theme files → theme {theme_id}")
    for key in THEME_FILES:
        if dry:
            print(f"  (dry) would upload {key}")
            continue
        api("PUT", f"/themes/{theme_id}/assets.json", {
            "asset": {"key": key, "value": (ROOT / key).read_text(encoding="utf-8")}
        })
        print(f"  ✓ {key}")


def build_product_template(theme_id: str, dry: bool):
    """Clone the theme's real product.json so the bundle template keeps the
    existing gallery/blocks/trust badges 1:1, swap the hardcoded StradaPro
    color-swatch block for the metafield-driven snippet, and append the
    included-items section."""
    print(f"\n— Product template (from theme {theme_id} product.json)")
    asset = api("GET", f"/themes/{theme_id}/assets.json?asset[key]=templates/product.json")
    tpl = json.loads(asset["asset"]["value"])

    main_key = tpl["order"][0]
    main = tpl["sections"][main_key]
    swapped = False
    for block in main.get("blocks", {}).values():
        custom = block.get("settings", {}).get("custom_liquid", "")
        if "vcol-swatches" in custom or "velluto_color_swatches" in json.dumps(block):
            block["settings"]["custom_liquid"] = (
                "{% render 'velluto-bundle-color-swatches', product: product %}"
            )
            swapped = True
    if not swapped and "blocks" in main:
        # No existing swatch block found — add one at the end.
        main["blocks"]["velluto_bundle_swatches"] = {
            "type": "liquid",
            "settings": {"custom_liquid": "{% render 'velluto-bundle-color-swatches', product: product %}"},
        }
        main.setdefault("block_order", list(main["blocks"].keys()))
        if "velluto_bundle_swatches" not in main["block_order"]:
            main["block_order"].append("velluto_bundle_swatches")

    tpl["sections"]["bundle_includes"] = {
        "type": "velluto-bundle-included-items",
        "settings": {"free_shipping_threshold": 99},
    }
    tpl["order"].append("bundle_includes")

    if dry:
        print("  (dry) would upload templates/product.velluto-bundle.json "
              f"(swatch block {'swapped' if swapped else 'added'})")
        return
    api("PUT", f"/themes/{theme_id}/assets.json", {
        "asset": {"key": "templates/product.velluto-bundle.json",
                  "value": json.dumps(tpl, indent=2, ensure_ascii=False)}
    })
    print(f"  ✓ templates/product.velluto-bundle.json (swatch block {'swapped' if swapped else 'added'})")


def existing_handles() -> set:
    products = api("GET", "/products.json?limit=250&fields=handle")["products"]
    return {p["handle"] for p in products}


def create_products(dry: bool, active: bool):
    status = "active" if active else "draft"
    print(f"\n— Bundle products (12, status={status})")
    if not active:
        print("  NOTE: draft products do not render on the storefront, so the")
        print("  landing cards stay empty until the products are set to active")
        print("  (re-run with --active, or flip them in the admin when testing).")
    have = existing_handles()
    images = {}
    for color, h in STRADA_HANDLES.items():
        try:
            images[color] = storefront_json(f"/products/{h}.js").get("featured_image")
        except Exception:
            images[color] = None

    for set_key, cfg in SETS.items():
        siblings = ",".join(handle_for(set_key, c) for c in COLORS)
        for color in COLORS:
            handle = handle_for(set_key, color)
            if handle in have:
                print(f"  • {handle} exists — skipped")
                continue
            if dry:
                print(f"  (dry) would create {status} {handle} @ {cfg['price']}")
                continue
            body_html = (
                "<p>Test bundle — includes: " + ", ".join(cfg["items"]) + ".</p>"
            )
            product = {
                "title": f"{cfg['title']} | {COLOR_LABELS[color]}",
                "handle": handle,
                "status": status,
                "template_suffix": "velluto-bundle",
                "tags": "bundle, strada-pro-set, test",
                "body_html": body_html,
                "variants": [{
                    "price": cfg["price"],
                    "compare_at_price": cfg["compare_at"],
                    "requires_shipping": True,
                    "inventory_management": None,
                }],
                "metafields": [
                    {"namespace": "velluto", "key": "included_items",
                     "type": "multi_line_text_field", "value": "\n".join(cfg["items"])},
                    {"namespace": "velluto", "key": "color_label",
                     "type": "single_line_text_field", "value": COLOR_LABELS[color]},
                    {"namespace": "velluto", "key": "color_siblings",
                     "type": "single_line_text_field", "value": siblings},
                ],
            }
            img = images.get(color)
            if img:
                product["images"] = [{"src": img if img.startswith("http") else "https:" + img}]
            api("POST", "/products.json", {"product": product})
            print(f"  ✓ {status} {handle} @ {cfg['price']}")
            time.sleep(0.6)  # stay under REST rate limit


def create_page(dry: bool):
    print("\n— Test page")
    pages = api("GET", f"/pages.json?handle={PAGE['handle']}")["pages"]
    if pages:
        print(f"  • page /{PAGE['handle']} exists — skipped")
        return
    if dry:
        print(f"  (dry) would create page /{PAGE['handle']} (template {PAGE['template_suffix']})")
        return
    api("POST", "/pages.json", {"page": {**PAGE, "published": True}})
    print(f"  ✓ page /pages/{PAGE['handle']} (keep out of navigation; template only "
          "exists on the test theme, so the live theme renders it as a plain page)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme-id")
    ap.add_argument("--list-themes", action="store_true")
    ap.add_argument("--skip-products", action="store_true")
    ap.add_argument("--active", action="store_true",
                    help="create bundle products as active (visible by URL) instead of draft")
    ap.add_argument("--skip-page", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not TOKEN:
        sys.exit("SHOPIFY_TOKEN not set")

    if args.list_themes:
        for t in api("GET", "/themes.json")["themes"]:
            print(f"{t['id']}  role={t['role']:<12} {t['name']}  (updated {t['updated_at']})")
        return

    if not args.theme_id:
        sys.exit("--theme-id required (use --list-themes first)")

    theme = pick_theme(args.theme_id)
    print(f"Target: {theme['name']!r} (id {theme['id']}, role {theme['role']}) on {SHOP}")

    upload_theme_files(args.theme_id, args.dry_run)
    build_product_template(args.theme_id, args.dry_run)
    if not args.skip_products:
        create_products(args.dry_run, args.active)
    if not args.skip_page:
        create_page(args.dry_run)

    print(f"""
Done. Preview:
  Shopify Admin → Online Store → Themes → {theme['name']!r} → Customize / Preview
  Landing page:  /pages/{PAGE['handle']}  (while previewing the test theme)
Nothing was published; bundle products are drafts.
""")


if __name__ == "__main__":
    main()
