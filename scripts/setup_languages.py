"""
Shopify language setup — enables, publishes, and assigns European languages
to the Europe market via the GraphQL Admin API.

Run: python scripts/setup_languages.py
"""

import asyncio
import json
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

SHOP    = settings.shopify_shop_name
TOKEN   = settings.shopify_access_token
API_VER = settings.shopify_api_version
GQL_URL = f"https://{SHOP}/admin/api/{API_VER}/graphql.json"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

# Target languages — English is already primary, skip it
LANGUAGES = [
    ("nl", "Dutch"),
    ("de", "German"),
    ("fr", "French"),
    ("es", "Spanish"),
    ("it", "Italian"),
    ("pt-PT", "Portuguese (Portugal)"),
    ("pl", "Polish"),
    ("sv", "Swedish"),
    ("da", "Danish"),
    ("nb", "Norwegian"),
]


async def gql(client: httpx.AsyncClient, query: str, variables: dict = {}) -> dict:
    r = await client.post(GQL_URL, headers=HEADERS,
                          json={"query": query, "variables": variables})
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]


# ── Step 1: fetch currently enabled locales ───────────────────────────────────

QUERY_LOCALES = """
query {
  shopLocales {
    locale
    name
    primary
    published
  }
}
"""

# ── Step 2: enable a locale ───────────────────────────────────────────────────

MUTATION_ENABLE = """
mutation shopLocaleEnable($locale: String!) {
  shopLocaleEnable(locale: $locale) {
    shopLocale { locale name published }
    userErrors { field message }
  }
}
"""

# ── Step 3: publish a locale ──────────────────────────────────────────────────

MUTATION_PUBLISH = """
mutation shopLocaleUpdate($locale: String!, $shopLocale: ShopLocaleInput!) {
  shopLocaleUpdate(locale: $locale, shopLocale: $shopLocale) {
    shopLocale { locale name published }
    userErrors { field message }
  }
}
"""

# ── Step 4: fetch markets ─────────────────────────────────────────────────────

QUERY_MARKETS = """
query {
  markets(first: 20) {
    nodes {
      id
      name
      primary
      enabled
      webPresence {
        id
        subfolderSuffix
        domain { id host }
        alternateLocales { locale name }
        defaultLocale { locale name }
      }
    }
  }
}
"""

# ── Step 5: update webPresence locales directly ───────────────────────────────

MUTATION_WEB_PRESENCE_UPDATE = """
mutation webPresenceUpdate($id: ID!, $input: WebPresenceUpdateInput!) {
  webPresenceUpdate(id: $id, input: $input) {
    webPresence {
      id
      alternateLocales { locale name }
      defaultLocale { locale name }
    }
    userErrors { field message }
  }
}
"""


def ok(symbol="✓"): return f"\033[32m{symbol}\033[0m"
def warn(symbol="⚠"): return f"\033[33m{symbol}\033[0m"
def err(symbol="✗"): return f"\033[31m{symbol}\033[0m"


async def main():
    async with httpx.AsyncClient(timeout=30) as client:

        # ── 1. Check existing locales ─────────────────────────────────────────
        print("\n── Current shop locales ─────────────────────────────────────")
        data = await gql(client, QUERY_LOCALES)
        existing = {loc["locale"]: loc for loc in data["shopLocales"]}
        for loc in data["shopLocales"]:
            flag = "PRIMARY" if loc["primary"] else ("published" if loc["published"] else "draft")
            print(f"  {ok()} {loc['locale']:8} {loc['name']:30} [{flag}]")

        # ── 2. Enable + publish each target language ──────────────────────────
        print("\n── Enabling & publishing languages ──────────────────────────")
        enabled_locales = []

        for locale, name in LANGUAGES:
            if locale in existing:
                if existing[locale]["published"]:
                    print(f"  {ok()} {locale:8} {name} — already published")
                    enabled_locales.append(locale)
                    continue
                else:
                    print(f"  {warn()} {locale:8} {name} — exists but not published, publishing...")
            else:
                # Enable
                result = await gql(client, MUTATION_ENABLE, {"locale": locale})
                errs = result["shopLocaleEnable"]["userErrors"]
                if errs:
                    print(f"  {err()} {locale:8} {name} — enable failed: {errs}")
                    continue
                print(f"  {ok()} {locale:8} {name} — enabled")

            # Publish
            result = await gql(client, MUTATION_PUBLISH,
                               {"locale": locale, "shopLocale": {"published": True}})
            errs = result["shopLocaleUpdate"]["userErrors"]
            if errs:
                print(f"  {err()} {locale:8} {name} — publish failed: {errs}")
            else:
                print(f"  {ok()} {locale:8} {name} — published")
                enabled_locales.append(locale)

        # ── 3. Find Europe market ─────────────────────────────────────────────
        print("\n── Markets ──────────────────────────────────────────────────")
        data = await gql(client, QUERY_MARKETS)
        markets = data["markets"]["nodes"]
        for m in markets:
            wp = m.get("webPresence") or {}
            default = wp.get("defaultLocale", {}).get("locale", "?") if wp else "?"
            alts = [l["locale"] for l in (wp.get("alternateLocales") or [])]
            print(f"  {'PRIMARY' if m['primary'] else '       '} {m['name']:30} default={default} alts={alts}")

        europe = next(
            (m for m in markets if "europe" in m["name"].lower() or "eu" in m["name"].lower()),
            None
        )

        if not europe:
            # Fall back to primary market
            europe = next((m for m in markets if m["primary"]), None)
            if europe:
                print(f"\n  {warn()} No 'Europe' market found — using primary market '{europe['name']}'")
            else:
                print(f"\n  {err()} No market found to assign locales to. Add an 'Europe' market in Shopify admin first.")
                sys.exit(1)
        else:
            print(f"\n  {ok()} Found Europe market: {europe['name']} ({europe['id']})")

        if not europe.get("webPresence"):
            print(f"  {warn()} Market has no webPresence — skipping locale assignment.")
            print("  Set up domain/subfolder in Shopify Admin → Markets → Europe, then re-run.")
            return

        wp = europe["webPresence"]
        domain_id = wp.get("domain", {}).get("id") if wp.get("domain") else None
        subfolder  = wp.get("subfolderSuffix")

        # ── 4. Swap webPresence: delete old, add new with all locales ─────────
        print(f"\n── Assigning locales to '{europe['name']}' market ───────────────")
        print(f"  webPresence id : {wp['id']}")
        print(f"  subfolder      : {subfolder or '(none)'}  domain: {wp.get('domain', {}).get('host') if wp.get('domain') else '(none)'}")

        result = await gql(client, MUTATION_WEB_PRESENCE_UPDATE, {
            "id": wp["id"],
            "input": {"defaultLocale": "en", "alternateLocales": enabled_locales}
        })
        errs = result["webPresenceUpdate"]["userErrors"]
        if errs:
            print(f"  {warn()} Errors: {errs}")
            print("  Languages are still published store-wide — assign manually in Shopify Admin → Markets → Europe → Languages.")
        else:
            new = result["webPresenceUpdate"]["webPresence"]
            default = new["defaultLocale"]["locale"]
            alts = [l["locale"] for l in new["alternateLocales"]]
            print(f"  {ok()} Default locale : {default}")
            print(f"  {ok()} Alternate locales: {alts}")

        print("\n── Summary ──────────────────────────────────────────────────")
        print(f"  Published languages : {len(enabled_locales) + 1} (EN + {len(enabled_locales)} others)")
        print(f"  Market              : {europe['name']}")
        print(f"  Next step           : Go to Shopify Admin → Translate & Adapt to fill in")
        print(f"                        translations, or use the Autopilot translation tools.")
        print()


if __name__ == "__main__":
    asyncio.run(main())
