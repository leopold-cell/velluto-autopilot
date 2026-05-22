"""
Revert all translations that were registered via the Shopify Translations API
(translate_products.py + translate_templates.py).

Translations should be managed exclusively through the Translate & Adapt app —
this script removes everything that was registered outside of that workflow.

Usage:
  python scripts/revert_translations.py --dry-run   # preview only
  python scripts/revert_translations.py --live      # actually delete
"""

from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

SHOP    = settings.shopify_shop_name
TOKEN   = settings.shopify_access_token
API_VER = settings.shopify_api_version
GQL_URL = f"https://{SHOP}/admin/api/{API_VER}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

LOCALES = ["nl", "de", "fr", "es", "it", "pt-PT", "pl", "sv", "da", "nb"]

PRODUCT_KEYS = ["title", "body_html", "meta_title", "meta_description", "product_type"]


def ok(s=""): return f"\033[32m{s or '✓'}\033[0m"
def warn(s=""): return f"\033[33m{s or '⚠'}\033[0m"
def err(s=""): return f"\033[31m{s or '✗'}\033[0m"


async def gql(client: httpx.AsyncClient, query: str, variables: dict = {}) -> dict:
    r = await client.post(GQL_URL, headers=HEADERS, json={"query": query, "variables": variables})
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]


# ── Queries ──────────────────────────────────────────────────────────────────

QUERY_PRODUCTS = """
query($cursor: String) {
  products(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes { id title }
  }
}
"""

QUERY_TRANSLATIONS = """
query($resourceId: ID!) {
  translatableResource(resourceId: $resourceId) {
    resourceId
    translations(locale: "nl") { locale key value }
  }
}
"""

QUERY_TRANSLATIONS_LOCALE = """
query($resourceId: ID!, $locale: String!) {
  translatableResource(resourceId: $resourceId) {
    resourceId
    translations(locale: $locale) { locale key value }
  }
}
"""

QUERY_THEME_TEMPLATES = """
query {
  translatableResources(resourceType: ONLINE_STORE_THEME_JSON_TEMPLATE, first: 50) {
    nodes {
      resourceId
      translations(locale: "nl") { locale key value }
    }
  }
}
"""

MUTATION_REMOVE = """
mutation translationsRemove($resourceId: ID!, $locales: [String!]!, $translationKeys: [String!]!) {
  translationsRemove(resourceId: $resourceId, locales: $locales, translationKeys: $translationKeys) {
    userErrors { field message }
    translations { locale key value }
  }
}
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

async def fetch_all_products(client: httpx.AsyncClient) -> list[dict]:
    products = []
    cursor = None
    while True:
        data = await gql(client, QUERY_PRODUCTS, {"cursor": cursor})
        page = data["products"]
        products.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return products


async def has_any_translation(client: httpx.AsyncClient, resource_id: str) -> bool:
    """Quick check: does this resource have at least one nl translation registered?"""
    data = await gql(client, QUERY_TRANSLATIONS, {"resourceId": resource_id})
    translations = data["translatableResource"]["translations"]
    return bool(translations)


async def get_all_translated_keys(client: httpx.AsyncClient, resource_id: str) -> list[str]:
    """Collect all keys that have at least one translation across any locale."""
    keys: set[str] = set()
    for locale in LOCALES:
        data = await gql(client, QUERY_TRANSLATIONS_LOCALE,
                         {"resourceId": resource_id, "locale": locale})
        for t in data["translatableResource"]["translations"]:
            keys.add(t["key"])
    return list(keys)


async def remove_translations(
    client: httpx.AsyncClient,
    resource_id: str,
    keys: list[str],
    dry_run: bool,
) -> dict:
    if not keys:
        return {"deleted": 0, "errors": []}

    if dry_run:
        return {"deleted": len(keys) * len(LOCALES), "errors": [], "dry_run": True}

    deleted = 0
    errors = []
    # Shopify max: 250 translationKeys per call
    for i in range(0, len(keys), 250):
        chunk = keys[i : i + 250]
        data = await gql(client, MUTATION_REMOVE, {
            "resourceId": resource_id,
            "locales": LOCALES,
            "translationKeys": chunk,
        })
        result = data["translationsRemove"]
        errors.extend([e["message"] for e in result["userErrors"]])
        deleted += len(result["translations"] or [])
    return {"deleted": deleted, "errors": errors}


# ── Products ─────────────────────────────────────────────────────────────────

async def revert_product_translations(client: httpx.AsyncClient, dry_run: bool) -> dict:
    products = await fetch_all_products(client)
    log.info("revert.products_found", count=len(products))

    total_deleted = 0
    total_skipped = 0
    errors = []

    for product in products:
        pid = product["id"]
        title = product["title"]

        # Use product keys that were translated by translate_products.py
        result = await remove_translations(client, pid, PRODUCT_KEYS, dry_run)

        if result.get("errors"):
            errors.extend([f"{title}: {e}" for e in result["errors"]])
            print(f"  {err()} {title[:50]}")
        elif result["deleted"] > 0:
            total_deleted += result["deleted"]
            tag = "(dry)" if dry_run else ""
            print(f"  {ok()} {title[:50]:50} {result['deleted']} entries removed {tag}")
        else:
            total_skipped += 1

    return {"deleted": total_deleted, "skipped": total_skipped, "errors": errors}


# ── Theme Templates ───────────────────────────────────────────────────────────

async def revert_template_translations(client: httpx.AsyncClient, dry_run: bool) -> dict:
    data = await gql(client, QUERY_THEME_TEMPLATES)
    nodes = data["translatableResources"]["nodes"]
    log.info("revert.templates_found", count=len(nodes))

    total_deleted = 0
    total_skipped = 0
    errors = []

    for node in nodes:
        rid = node["resourceId"]
        template_name = rid.split("/OnlineStoreThemeJsonTemplate/")[1].split("?")[0] \
            if "/OnlineStoreThemeJsonTemplate/" in rid else rid

        # Get all keys that actually have translations (could vary per template)
        keys = await get_all_translated_keys(client, rid)

        if not keys:
            total_skipped += 1
            continue

        result = await remove_translations(client, rid, keys, dry_run)

        if result.get("errors"):
            errors.extend([f"{template_name}: {e}" for e in result["errors"]])
            print(f"  {err()} {template_name[:50]}")
        else:
            total_deleted += result["deleted"]
            tag = "(dry)" if dry_run else ""
            print(f"  {ok()} {template_name[:50]:50} {len(keys)} keys × {len(LOCALES)} locales removed {tag}")

    return {"deleted": total_deleted, "skipped": total_skipped, "errors": errors}


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    dry_run = "--dry-run" in sys.argv
    live    = "--live" in sys.argv

    if not dry_run and not live:
        print("Usage: python scripts/revert_translations.py [--dry-run | --live]")
        print("  --dry-run  Preview what would be deleted (no writes)")
        print("  --live     Actually remove all API-registered translations")
        sys.exit(1)

    mode = "DRY RUN — no changes" if dry_run else "LIVE — deleting translations"
    print(f"\n── Velluto Translation Revert [{mode}] ──────────────────────\n")

    if live:
        print(f"  {warn('!')} This will remove ALL translated content for products and")
        print(f"  {warn('!')} theme templates across 10 languages.")
        print(f"  {warn('!')} Translations must then be re-done via the Translate & Adapt app.")
        print()
        confirm = input("  Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("  Aborted.")
            sys.exit(0)
        print()

    async with httpx.AsyncClient(timeout=60) as client:
        print("── Products ──────────────────────────────────────────────────────")
        prod_result = await revert_product_translations(client, dry_run)

        print("\n── Theme Templates ───────────────────────────────────────────────")
        tmpl_result = await revert_template_translations(client, dry_run)

    total = prod_result["deleted"] + tmpl_result["deleted"]
    all_errors = prod_result["errors"] + tmpl_result["errors"]

    print(f"\n── Summary ───────────────────────────────────────────────────────")
    print(f"  Products   : {prod_result['deleted']} entries removed"
          f" ({prod_result['skipped']} had no translations)")
    print(f"  Templates  : {tmpl_result['deleted']} entries removed"
          f" ({tmpl_result['skipped']} had no translations)")
    print(f"  Total      : {total} translation entries removed")
    if all_errors:
        print(f"\n  {warn(f'⚠ {len(all_errors)} errors:')}")
        for e in all_errors[:5]:
            print(f"    {err()} {e}")
    print(f"  Mode       : {'Dry run — nothing written' if dry_run else 'Live — changes applied'}")
    if dry_run:
        print(f"\n  Run with --live to apply these changes.")
    else:
        print(f"\n  ✓ Done. Re-do translations via Translate & Adapt in Shopify Admin.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
