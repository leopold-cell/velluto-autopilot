#!/usr/bin/env python3
"""
Deploy the StradaPro PDP Kit Switcher test (theme files + kit products + page).

Catalog model (approved plan):
  - Starter Kit  = the 4 EXISTING StradaPro color products (rename only)
  - Performance Kit / Ultimate Kit = 8 NEW products (one per color)
  - PDP kit switcher + color switcher are metafield-driven sibling links

Modeled on velluto-seo-bot/scripts/deploy_theme.py (same Admin API mechanism,
same SHOPIFY_TOKEN / SHOPIFY_STORE env vars).

Usage:
  SHOPIFY_TOKEN=shpat_... python3 deploy_kits.py --list-themes
  SHOPIFY_TOKEN=shpat_... python3 deploy_kits.py --theme-id 123456789
  ... --rename-live       # ALSO rename the 4 live StradaPro products (title only)
  ... --reprice-live      # ALSO reprice them to 69.00 (compare-at 108.00)
  ... --skip-products     # theme files only
  ... --dry-run           # print what would happen

Safety:
  - Refuses theme writes to the published (live) theme.
  - Renaming the live products only happens with the explicit --rename-live
    flag; old titles are saved to kit_rename_rollback.json.
  - Existing products/pages with the same handle are never overwritten.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
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
    "snippets/velluto-kit-switcher.liquid",
    "assets/velluto-kit-switcher.css",
    "templates/page.velluto-bundles-test.json",
]

COLORS = ["nero", "arancia", "espresso", "viola"]
COLOR_LABELS = {"nero": "Nero", "arancia": "Arancia", "espresso": "Espresso", "viola": "Viola"}
STARTER_HANDLES = {c: f"velluto-stradapro-cycling-glasses-{c}" for c in COLORS}

# Kit definitions. Starter = the existing products (renamed + repriced).
# Regular values (compare-at) per user spec 2026-06-11:
# Starter 108 (save 39), Performance 146 (save 47), Ultimate 162 (save 43).
KITS = {
    "starter": {
        "label": "Starter Kit",
        "tagline": "The essentials, ready to ride",
        "badge": "",
        # Applied to the 4 LIVE products only with --reprice-live.
        # compare_at = regular value of the kit contents (user-provided).
        "price": "69.00",
        "compare_at": "108.00",
        "items": ["Strada Pro", "Velluto Visione™ Lens"],
    },
    "performance": {
        "label": "Performance Kit",
        "tagline": "Every condition covered",
        "badge": "Most Popular",
        "price": "99.00",
        "compare_at": "146.00",
        "items": ["Strada Pro", "Velluto Visione™ Lens", "Clear Lens", "Hard Case"],
    },
    "ultimate": {
        "label": "Ultimate Kit",
        "tagline": "The complete Velluto ritual",
        "badge": "",
        "price": "119.00",
        "compare_at": "162.00",
        "items": [
            "Strada Pro", "Velluto Visione™ Lens", "Clear Lens", "Hard Case",
            "Cleaning Spray", "Microfiber Cloth", "Bottle",
        ],
    },
}
KIT_ORDER = ["starter", "performance", "ultimate"]

PAGE = {
    "title": "Choose your Strada Pro setup (TEST)",
    "handle": "strada-pro-sets-test",
    "template_suffix": "velluto-bundles-test",
}

ROLLBACK_FILE = Path(__file__).parent / "kit_rename_rollback.json"


def kit_handle(kit: str, color: str) -> str:
    if kit == "starter":
        return STARTER_HANDLES[color]
    return f"velluto-stradapro-{kit}-kit-{color}"


def kit_title(kit: str, color: str) -> str:
    return f"Velluto StradaPro | {KITS[kit]['label']} | {COLOR_LABELS[color]}"


def kit_siblings_csv(color: str) -> str:
    return ",".join(kit_handle(k, color) for k in KIT_ORDER)


def color_siblings_csv(kit: str) -> str:
    return ",".join(kit_handle(kit, c) for c in COLORS)


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
            if e.code == 429:  # Shopify REST is ~2 req/s
                time.sleep(2 ** attempt)
                continue
            print(f"  ✗ {method} {path} → {e.code}: {e.read().decode()[:300]}")
            raise
    raise RuntimeError(f"rate-limited too long: {path}")


def storefront_json(path: str) -> dict:
    with urllib.request.urlopen(f"{STOREFRONT}{path}", timeout=30) as r:
        return json.loads(r.read())


def product_by_handle(handle: str) -> dict | None:
    products = api("GET", f"/products.json?handle={urllib.parse.quote(handle)}")["products"]
    return products[0] if products else None


def pick_theme(theme_id: str) -> dict:
    themes = api("GET", "/themes.json")["themes"]
    theme = next((t for t in themes if str(t["id"]) == str(theme_id)), None)
    if theme is None:
        sys.exit(f"Theme {theme_id} not found. Use --list-themes.")
    if theme["role"] == "main":
        sys.exit(f"Refusing theme writes: {theme_id} ({theme['name']!r}) is the LIVE theme.")
    return theme


# ── Theme files ───────────────────────────────────────────────────────────────

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


KIT_SWITCHER_LIQUID = "{% render 'velluto-kit-switcher', product: product %}"
COLOR_SWATCHES_LIQUID = "{% render 'velluto-bundle-color-swatches', product: product %}"


def patch_product_template(theme_id: str, dry: bool) -> dict:
    """Add the kit-switcher Custom Liquid block to the theme COPY's default
    product template, positioned right above the buy buttons. The snippet
    renders nothing without the kit metafields, so non-kit products are
    unaffected. Returns the patched template dict for reuse."""
    print(f"\n— Patch templates/product.json on theme {theme_id} (kit switcher block)")
    asset = api("GET", f"/themes/{theme_id}/assets.json?asset[key]=templates/product.json")
    tpl = json.loads(asset["asset"]["value"])

    main_key = tpl["order"][0]
    main = tpl["sections"][main_key]
    blocks = main.setdefault("blocks", {})
    order = main.setdefault("block_order", list(blocks.keys()))

    already = any(
        KIT_SWITCHER_LIQUID in json.dumps(b) for b in blocks.values()
    )
    if already:
        print("  • kit switcher block already present — skipped")
    else:
        blocks["velluto_kit_switcher"] = {
            "type": "liquid",
            "settings": {"custom_liquid": KIT_SWITCHER_LIQUID},
        }
        # Insert above the buy buttons; fall back to the end.
        buy_idx = next(
            (i for i, bid in enumerate(order) if "buy" in blocks.get(bid, {}).get("type", "")),
            None,
        )
        if buy_idx is None:
            order.append("velluto_kit_switcher")
        else:
            order.insert(buy_idx, "velluto_kit_switcher")
        if not dry:
            api("PUT", f"/themes/{theme_id}/assets.json", {
                "asset": {"key": "templates/product.json",
                          "value": json.dumps(tpl, indent=2, ensure_ascii=False)}
            })
        print(f"  {'(dry) would add' if dry else '✓ added'} kit switcher block "
              f"({'above buy buttons' if buy_idx is not None else 'at end'})")
    return tpl


def build_bundle_template(theme_id: str, base_tpl: dict, dry: bool):
    """Template for the 8 NEW kit products: clone of the (patched) product
    template, with the hardcoded StradaPro color-swatch block swapped for the
    metafield-driven snippet, plus the included-items section."""
    print(f"\n— Build templates/product.velluto-bundle.json")
    tpl = json.loads(json.dumps(base_tpl))  # deep copy

    main_key = tpl["order"][0]
    main = tpl["sections"][main_key]
    swapped = False
    for block in main.get("blocks", {}).values():
        custom = block.get("settings", {}).get("custom_liquid", "")
        if "vcol-swatches" in custom or "vcol-swatch" in custom:
            block["settings"]["custom_liquid"] = COLOR_SWATCHES_LIQUID
            swapped = True
    if not swapped:
        main.setdefault("blocks", {})["velluto_bundle_swatches"] = {
            "type": "liquid",
            "settings": {"custom_liquid": COLOR_SWATCHES_LIQUID},
        }
        main.setdefault("block_order", list(main["blocks"].keys()))
        if "velluto_bundle_swatches" not in main["block_order"]:
            main["block_order"].append("velluto_bundle_swatches")

    if "bundle_includes" not in tpl["sections"]:
        tpl["sections"]["bundle_includes"] = {
            "type": "velluto-bundle-included-items",
            "settings": {"free_shipping_threshold": 99},
        }
        tpl["order"].append("bundle_includes")

    if dry:
        print(f"  (dry) would upload (color swatch block {'swapped' if swapped else 'added'})")
        return
    api("PUT", f"/themes/{theme_id}/assets.json", {
        "asset": {"key": "templates/product.velluto-bundle.json",
                  "value": json.dumps(tpl, indent=2, ensure_ascii=False)}
    })
    print(f"  ✓ uploaded (color swatch block {'swapped' if swapped else 'added'})")


# ── Products ─────────────────────────────────────────────────────────────────

def kit_metafields(kit: str, color: str) -> list[dict]:
    cfg = KITS[kit]
    mf = [
        {"namespace": "velluto", "key": "kit_label",
         "type": "single_line_text_field", "value": cfg["label"]},
        {"namespace": "velluto", "key": "kit_tagline",
         "type": "single_line_text_field", "value": cfg["tagline"]},
        {"namespace": "velluto", "key": "kit_siblings",
         "type": "single_line_text_field", "value": kit_siblings_csv(color)},
        {"namespace": "velluto", "key": "color_label",
         "type": "single_line_text_field", "value": COLOR_LABELS[color]},
        {"namespace": "velluto", "key": "color_siblings",
         "type": "single_line_text_field", "value": color_siblings_csv(kit)},
        {"namespace": "velluto", "key": "included_items",
         "type": "multi_line_text_field", "value": "\n".join(cfg["items"])},
    ]
    if cfg["badge"]:
        mf.append({"namespace": "velluto", "key": "kit_badge",
                   "type": "single_line_text_field", "value": cfg["badge"]})
    return mf


def create_kit_products(dry: bool):
    print("\n— New kit products (8, active but in no collection/menu)")
    images = {}
    for color, h in STARTER_HANDLES.items():
        try:
            images[color] = storefront_json(f"/products/{h}.js").get("featured_image")
        except Exception:
            images[color] = None

    for kit in ("performance", "ultimate"):
        cfg = KITS[kit]
        for color in COLORS:
            handle = kit_handle(kit, color)
            if product_by_handle(handle):
                print(f"  • {handle} exists — skipped")
                continue
            if dry:
                print(f"  (dry) would create active {handle} @ {cfg['price']}")
                continue
            product = {
                "title": kit_title(kit, color),
                "handle": handle,
                "status": "active",
                "template_suffix": "velluto-bundle",
                "tags": "kit, test",
                "body_html": "<p>Test kit — includes: " + ", ".join(cfg["items"]) + ".</p>",
                "variants": [{
                    "price": cfg["price"],
                    "compare_at_price": cfg["compare_at"],
                    "requires_shipping": True,
                    "inventory_management": None,
                }],
                "metafields": kit_metafields(kit, color),
            }
            img = images.get(color)
            if img:
                product["images"] = [{"src": img if img.startswith("http") else "https:" + img}]
            api("POST", "/products.json", {"product": product})
            print(f"  ✓ active {handle} @ {cfg['price']}")
            time.sleep(0.6)


def update_starter_products(dry: bool, rename: bool, reprice: bool):
    """Kit metafields on the 4 existing StradaPro products. Title rename only
    with --rename-live; price 149 → 69 (compare-at 149) only with
    --reprice-live. Both are LIVE changes — old title/price/compare-at are
    saved for rollback. Note: the REST price is the store's base (EUR)
    price; markets with automatic conversion follow it, but fixed per-market
    price lists (Shopify Markets) must be adjusted separately."""
    print(f"\n— Existing StradaPro products (metafields"
          f"{' + LIVE rename' if rename else ''}{' + LIVE reprice' if reprice else ''})")
    rollback = {}
    cfg = KITS["starter"]
    for color in COLORS:
        handle = STARTER_HANDLES[color]
        prod = product_by_handle(handle)
        if not prod:
            print(f"  ✗ {handle} not found — skipped")
            continue
        pid = prod["id"]
        variant = prod["variants"][0]

        if dry:
            msg = f"  (dry) would set kit metafields on {handle}"
            if rename:
                msg += f"; rename {prod['title']!r} → {kit_title('starter', color)!r}"
            if reprice:
                msg += f"; reprice {variant['price']} → {cfg['price']} (compare-at {cfg['compare_at']})"
            print(msg)
            continue

        existing_mf = api("GET", f"/products/{pid}/metafields.json?namespace=velluto")["metafields"]
        existing_keys = {m["key"] for m in existing_mf}
        for mf in kit_metafields("starter", color):
            if mf["key"] in existing_keys:
                mid = next(m["id"] for m in existing_mf if m["key"] == mf["key"])
                api("PUT", f"/metafields/{mid}.json", {"metafield": {"id": mid, "value": mf["value"], "type": mf["type"]}})
            else:
                api("POST", f"/products/{pid}/metafields.json", {"metafield": mf})
        print(f"  ✓ metafields on {handle}")

        rollback[handle] = {
            "title": prod["title"],
            "price": variant["price"],
            "compare_at_price": variant.get("compare_at_price"),
        }
        if rename:
            api("PUT", f"/products/{pid}.json", {
                "product": {"id": pid, "title": kit_title("starter", color)}
            })
            print(f"  ✓ LIVE rename: {prod['title']!r} → {kit_title('starter', color)!r}")
        if reprice:
            api("PUT", f"/variants/{variant['id']}.json", {
                "variant": {"id": variant["id"], "price": cfg["price"],
                            "compare_at_price": cfg["compare_at"]}
            })
            print(f"  ✓ LIVE reprice: {variant['price']} → {cfg['price']} (compare-at {cfg['compare_at']})")
        time.sleep(0.6)

    if rollback and not dry and (rename or reprice):
        ROLLBACK_FILE.write_text(json.dumps(rollback, indent=2, ensure_ascii=False))
        print(f"  Old titles/prices saved to {ROLLBACK_FILE}")


def create_page(dry: bool):
    print("\n— Test landing page")
    if api("GET", f"/pages.json?handle={PAGE['handle']}")["pages"]:
        print(f"  • page /{PAGE['handle']} exists — skipped")
        return
    if dry:
        print(f"  (dry) would create page /{PAGE['handle']}")
        return
    api("POST", "/pages.json", {"page": {**PAGE, "published": True}})
    print(f"  ✓ page /pages/{PAGE['handle']} (keep out of navigation)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme-id")
    ap.add_argument("--list-themes", action="store_true")
    ap.add_argument("--skip-products", action="store_true")
    ap.add_argument("--skip-page", action="store_true")
    ap.add_argument("--rename-live", action="store_true",
                    help="rename the 4 LIVE StradaPro products to '… | Starter Kit | Color'")
    ap.add_argument("--reprice-live", action="store_true",
                    help="reprice the 4 LIVE StradaPro products to 69.00 (compare-at 108.00)")
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
    patched = patch_product_template(args.theme_id, args.dry_run)
    build_bundle_template(args.theme_id, patched, args.dry_run)
    if not args.skip_products:
        create_kit_products(args.dry_run)
        update_starter_products(args.dry_run, args.rename_live, args.reprice_live)
    if not args.skip_page:
        create_page(args.dry_run)

    print(f"""
Done. Preview (theme copy {theme['id']}):
  Shopify Admin → Online Store → Themes → {theme['name']!r} → Preview, then open
  /products/{STARTER_HANDLES['nero']}  → kit switcher (Starter selected)
  /pages/{PAGE['handle']}              → bundle landing page
Notes:
  - The new kit products are ACTIVE (reachable by URL) but in no collection
    or menu. Set them to draft to fully hide them again.
  - The kit switcher only appears on the theme copy; the live theme is untouched.
""")


if __name__ == "__main__":
    main()
