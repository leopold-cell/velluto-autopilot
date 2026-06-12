#!/usr/bin/env python3
"""
Deploy the EU withdrawal button/page (required live from 19 June 2026,
Directive (EU) 2023/2673).

Unlike deploy_kits.py, this script MAY target the LIVE theme — but only with
the explicit --live-ok flag (user-approved: the withdrawal function is a
legal requirement on the live store). Recommended order:
  1. deploy to the theme copy, QA the form there
  2. re-run with the live theme id + --live-ok before 19 June

Usage:
  SHOPIFY_TOKEN=shpat_... python3 deploy_withdrawal.py --list-themes
  SHOPIFY_TOKEN=shpat_... python3 deploy_withdrawal.py --theme-id <COPY_ID>
  SHOPIFY_TOKEN=shpat_... python3 deploy_withdrawal.py --theme-id <LIVE_ID> --live-ok
  ... --dry-run / --skip-page / --skip-menu

What it does:
  - uploads sections/velluto-withdrawal-form.liquid and
    templates/page.withdrawal.json to the target theme
  - creates the published page /pages/withdrawal with that template
    (store-level: only needed once, shared by all themes)
  - adds a "Right of withdrawal" link to the footer menu via the GraphQL
    Admin API (menus are store-level); prints manual instructions if the
    token lacks the navigation scope
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

ROOT = Path(__file__).parent.parent

THEME_FILES = [
    "sections/velluto-withdrawal-form.liquid",
    "templates/page.withdrawal.json",
]

PAGE = {
    "title": "Right of withdrawal",
    "handle": "withdrawal",
    "template_suffix": "withdrawal",
}
MENU_ITEM_TITLE = "Right of withdrawal"
MENU_ITEM_URL = f"/pages/{PAGE['handle']}"


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
            if e.code == 429:
                time.sleep(2 ** attempt)
                continue
            print(f"  ✗ {method} {path} → {e.code}: {e.read().decode()[:300]}")
            raise
    raise RuntimeError(f"rate-limited too long: {path}")


def graphql(query: str, variables: dict | None = None) -> dict:
    out = api("POST", "/graphql.json", {"query": query, "variables": variables or {}})
    if out.get("errors"):
        raise RuntimeError(json.dumps(out["errors"])[:300])
    return out["data"]


def pick_theme(theme_id: str, live_ok: bool) -> dict:
    themes = api("GET", "/themes.json")["themes"]
    theme = next((t for t in themes if str(t["id"]) == str(theme_id)), None)
    if theme is None:
        sys.exit(f"Theme {theme_id} not found. Use --list-themes.")
    if theme["role"] == "main" and not live_ok:
        sys.exit(f"Theme {theme_id} ({theme['name']!r}) is the LIVE theme — "
                 "re-run with --live-ok to confirm (legal requirement, user-approved).")
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


def create_page(dry: bool):
    print("\n— Withdrawal page")
    if api("GET", f"/pages.json?handle={PAGE['handle']}")["pages"]:
        print(f"  • page /{PAGE['handle']} exists — skipped")
        return
    if dry:
        print(f"  (dry) would create published page /pages/{PAGE['handle']} "
              f"(template {PAGE['template_suffix']})")
        return
    api("POST", "/pages.json", {"page": {**PAGE, "published": True}})
    print(f"  ✓ page /pages/{PAGE['handle']}")


MANUAL_MENU_HELP = f"""  → Manual fallback (1 minute):
    Shopify Admin → Online Store → Navigation → footer/legal menu →
    Add menu item: "{MENU_ITEM_TITLE}" → link to Pages → Right of withdrawal."""


def add_footer_menu_link(dry: bool):
    """Menus are store-level and GraphQL-only. menuUpdate replaces the full
    item list, so we re-send existing items plus the new link."""
    print("\n— Footer menu link")
    try:
        data = graphql("""
          { menus(first: 25) { nodes {
              id handle title
              items { id title type url resourceId tags
                      items { id title type url resourceId tags } }
          } } }""")
    except Exception as e:
        print(f"  ✗ cannot read menus ({e})")
        print(MANUAL_MENU_HELP)
        return

    menus = data["menus"]["nodes"]
    footer = next((m for m in menus if "footer" in m["handle"].lower()), None) \
        or next((m for m in menus if "legal" in m["handle"].lower()), None)
    if footer is None:
        print(f"  ✗ no footer/legal menu found (menus: {[m['handle'] for m in menus]})")
        print(MANUAL_MENU_HELP)
        return

    if any(MENU_ITEM_URL in (i.get("url") or "") for i in footer["items"]):
        print(f"  • link already in menu {footer['handle']!r} — skipped")
        return
    if dry:
        print(f"  (dry) would append {MENU_ITEM_TITLE!r} to menu {footer['handle']!r}")
        return

    def to_input(item):
        out = {"title": item["title"], "type": item["type"]}
        if item.get("url"):
            out["url"] = item["url"]
        if item.get("resourceId"):
            out["resourceId"] = item["resourceId"]
        if item.get("tags"):
            out["tags"] = item["tags"]
        if item.get("items"):
            out["items"] = [to_input(c) for c in item["items"]]
        return out

    items = [to_input(i) for i in footer["items"]]
    items.append({"title": MENU_ITEM_TITLE, "type": "HTTP", "url": MENU_ITEM_URL})
    try:
        result = graphql("""
          mutation($id: ID!, $title: String!, $handle: String!, $items: [MenuItemUpdateInput!]!) {
            menuUpdate(id: $id, title: $title, handle: $handle, items: $items) {
              menu { id }
              userErrors { field message }
            }
          }""", {"id": footer["id"], "title": footer["title"],
                 "handle": footer["handle"], "items": items})
        errs = result["menuUpdate"]["userErrors"]
        if errs:
            raise RuntimeError(errs)
        print(f"  ✓ appended {MENU_ITEM_TITLE!r} to menu {footer['handle']!r}")
    except Exception as e:
        print(f"  ✗ menuUpdate failed ({e})")
        print(MANUAL_MENU_HELP)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme-id")
    ap.add_argument("--list-themes", action="store_true")
    ap.add_argument("--live-ok", action="store_true",
                    help="allow deploying to the LIVE theme (legal requirement)")
    ap.add_argument("--skip-page", action="store_true")
    ap.add_argument("--skip-menu", action="store_true")
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

    theme = pick_theme(args.theme_id, args.live_ok)
    print(f"Target: {theme['name']!r} (id {theme['id']}, role {theme['role']}) on {SHOP}")

    upload_theme_files(args.theme_id, args.dry_run)
    if not args.skip_page:
        create_page(args.dry_run)
    if not args.skip_menu:
        add_footer_menu_link(args.dry_run)

    print(f"""
Done. Verify:
  /pages/{PAGE['handle']} → two-step flow, then check the store contact inbox
  Footer → "{MENU_ITEM_TITLE}" link visible on every page (desktop + mobile)
Remaining manual steps:
  - Set the Klaviyo public site key in the section settings (theme editor)
  - Activate the Klaviyo flow on the "Withdrawal Requested" metric
""")


if __name__ == "__main__":
    main()
