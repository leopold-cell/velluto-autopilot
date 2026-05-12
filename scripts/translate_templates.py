"""
Translate Shopify theme JSON templates into all 10 languages.

Templates translated:
  product (Standard Produkt), product.trinkflasche, product.spare-lens,
  product.visione-glas-technology, product.glasses-case,
  product.cloth-cleaning-spray, product.cleaning_spray

Usage:
  python scripts/translate_templates.py          # live run
  python scripts/translate_templates.py --dry-run # preview only
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

SHOP    = settings.shopify_shop_name
TOKEN   = settings.shopify_access_token
API_VER = settings.shopify_api_version
GQL_URL = f"https://{SHOP}/admin/api/{API_VER}/graphql.json"
GQL_HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}

TARGET_TEMPLATES = [
    "product",
    "product.trinkflasche",
    "product.spare-lens",
    "product.visione-glas-technology",
    "product.glasses-case",
    "product.cloth-cleaning-spray",
    "product.cleaning_spray",
]

LANGUAGES = {
    "nl": "Dutch",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt-PT": "Portuguese (Portugal)",
    "pl": "Polish",
    "sv": "Swedish",
    "da": "Danish",
    "nb": "Norwegian (Bokmål)",
}

LANG_BATCH_SIZE  = 3   # languages per Claude call
FIELD_BATCH_SIZE = 40  # max fields per Claude call — large templates get split

SYSTEM_PROMPT = """You are a professional e-commerce translator for Velluto, a premium Dutch road cycling eyewear brand.

CRITICAL BRAND RULES:
- NEVER translate these terms: Velluto, StradaPro, VellutoPuro, VellutoVisione, Nero, Viola, Espresso, Arancia, Dolce Vita, TACX, UV400
- Maintain a premium, technical, performance-focused tone
- Preserve all HTML tags exactly — only translate visible text content inside them
- Preserve Liquid template tags like {{ ... }} exactly as-is
- Preserve URLs, shopify:// references, and numeric values exactly
- Short UI labels (like "Color", "Size") should use natural local equivalents

OUTPUT: Return valid JSON only — no markdown, no explanation."""


def is_translatable(value: str) -> bool:
    if not value or not value.strip():
        return False
    v = value.strip()
    if v.startswith("shopify://"):
        return False
    if "{{" in v and "}}" in v and re.fullmatch(r'[\{\}\s\|a-zA-Z0-9_.\-\[\]"\']+', v):
        return False
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
        return False
    if re.fullmatch(r'[0-9a-f]{40,}', v):
        return False
    if re.fullmatch(r'\d+', v):
        return False
    return True


async def _gql(client: httpx.AsyncClient, query: str, variables: dict = {}) -> dict:
    r = await client.post(GQL_URL, headers=GQL_HEADERS,
                          json={"query": query, "variables": variables})
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL: {data['errors']}")
    return data["data"]


QUERY_TEMPLATES = """
query {
  translatableResources(resourceType: ONLINE_STORE_THEME_JSON_TEMPLATE, first: 50) {
    nodes {
      resourceId
      translatableContent { key value digest locale }
    }
  }
}
"""

MUTATION_REGISTER = """
mutation translationsRegister($resourceId: ID!, $translations: [TranslationInput!]!) {
  translationsRegister(resourceId: $resourceId, translations: $translations) {
    userErrors { field message }
    translations { locale key value }
  }
}
"""


async def translate_fields_batch(
    claude: anthropic.AsyncAnthropic,
    fields: dict[str, str],
    lang_batch: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Translate fields into a batch of languages. Returns {locale: {key: value}}."""
    lang_names = ", ".join(lang_batch.values())
    locale_keys = list(lang_batch.keys())

    # Use short numeric IDs to keep the prompt compact
    id_map = {str(i): k for i, k in enumerate(fields)}
    id_fields = {str(i): v for i, v in enumerate(fields.values())}

    prompt = (
        f"Translate the following UI fields into ONLY these languages: {lang_names}.\n"
        f"Return JSON with ONLY these locale keys: {locale_keys}.\n"
        f"Each locale maps to an object with the same numeric keys as the input.\n\n"
        f"INPUT:\n{json.dumps(id_fields, ensure_ascii=False, indent=2)}"
    )

    response = await claude.messages.create(
        model=settings.anthropic_model,
        max_tokens=8000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    id_result: dict[str, dict[str, str]] = json.loads(raw)

    # Map numeric IDs back to real keys
    result: dict[str, dict[str, str]] = {}
    for locale, id_translations in id_result.items():
        result[locale] = {id_map[k]: v for k, v in id_translations.items() if k in id_map}
    return result


async def translate_template(
    resource_id: str,
    template_name: str,
    content: list[dict],
    dry_run: bool = False,
) -> dict:
    claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    fields = {c["key"]: c["value"] for c in content if is_translatable(c.get("value", ""))}
    digest_map = {c["key"]: c["digest"] for c in content}

    if not fields:
        return {"template": template_name, "skipped": True, "reason": "no translatable fields"}

    log.info("translate_templates.start", template=template_name, fields=len(fields))

    # Translate in (field chunk) × (language batch) combinations
    all_translations: dict[str, dict[str, str]] = {}
    lang_items   = list(LANGUAGES.items())
    field_items  = list(fields.items())

    for fi in range(0, len(field_items), FIELD_BATCH_SIZE):
        field_chunk = dict(field_items[fi : fi + FIELD_BATCH_SIZE])
        for li in range(0, len(lang_items), LANG_BATCH_SIZE):
            lang_batch = dict(lang_items[li : li + LANG_BATCH_SIZE])
            try:
                batch_result = await translate_fields_batch(claude, field_chunk, lang_batch)
                for locale, translated in batch_result.items():
                    if locale not in all_translations:
                        all_translations[locale] = {}
                    all_translations[locale].update(translated)
                log.info("translate_templates.batch_done",
                         template=template_name, locales=list(lang_batch.keys()),
                         fields_offset=fi)
            except (json.JSONDecodeError, Exception) as e:
                log.error("translate_templates.batch_failed",
                          template=template_name, batch=list(lang_batch.keys()),
                          fields_offset=fi, error=str(e))

    if dry_run:
        sample_locale = "nl"
        sample = {k: v for k, v in (all_translations.get(sample_locale, {}) or {}).items()
                  if v and not k.endswith(":image") and not k.endswith(":url")}
        first5 = dict(list(sample.items())[:5])
        return {
            "template": template_name,
            "dry_run": True,
            "languages": list(all_translations.keys()),
            "fields_count": len(fields),
            "sample_nl": first5,
        }

    # Register translations
    async with httpx.AsyncClient(timeout=30) as client:
        registered = 0
        errors = []
        for locale, translated_fields in all_translations.items():
            inputs = []
            for key, value in translated_fields.items():
                if key not in digest_map or not value:
                    continue
                inputs.append({
                    "locale": locale,
                    "key": key,
                    "value": value,
                    "translatableContentDigest": digest_map[key],
                })
            if not inputs:
                continue

            result = await _gql(client, MUTATION_REGISTER, {
                "resourceId": resource_id,
                "translations": inputs,
            })
            errs = result["translationsRegister"]["userErrors"]
            if errs:
                errors.extend([f"{locale}: {e['message']}" for e in errs])
            else:
                registered += len(inputs)

    return {
        "template": template_name,
        "resource_id": resource_id,
        "languages_translated": list(all_translations.keys()),
        "fields_registered": registered,
        "errors": errors,
    }


async def translate_all_templates(dry_run: bool = False) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        data = await _gql(client, QUERY_TEMPLATES)

    nodes = data["translatableResources"]["nodes"]
    target_nodes = []
    for node in nodes:
        rid = node["resourceId"]
        template_name = rid.split("/OnlineStoreThemeJsonTemplate/")[1].split("?")[0]
        if template_name in TARGET_TEMPLATES:
            target_nodes.append((rid, template_name, node["translatableContent"]))

    log.info("translate_templates.found", count=len(target_nodes))

    results = []
    for rid, name, content in target_nodes:
        result = await translate_template(rid, name, content, dry_run=dry_run)
        results.append(result)
        status = "DRY RUN" if dry_run else f"{result.get('fields_registered', 0)} fields"
        log.info("translate_templates.done", template=name, status=status)

    total = sum(r.get("fields_registered", 0) for r in results)
    return {"templates_translated": len(results), "total_fields_registered": total,
            "dry_run": dry_run, "results": results}


# ── CLI output ──────────────────────────────────────────────────────────────

def ok(s=""): return f"\033[32m{s or '✓'}\033[0m"
def warn(s=""): return f"\033[33m{s or '⚠'}\033[0m"
def err(s=""): return f"\033[31m{s or '✗'}\033[0m"


async def main():
    dry_run = "--dry-run" in sys.argv
    mode = "DRY RUN — no writes" if dry_run else "LIVE — translating & publishing"
    print(f"\n── Velluto Template Translator [{mode}] ─────────────────────────\n")

    report = await translate_all_templates(dry_run=dry_run)

    print(f"\n── Results ───────────────────────────────────────────────────────")
    for r in report["results"]:
        if r.get("skipped"):
            print(f"  {warn('–')} {r['template']:45} SKIPPED ({r.get('reason')})")
            continue
        if r.get("errors"):
            for e in r["errors"][:2]:
                print(f"       {err()} {e}")

        if dry_run:
            print(f"  {ok()} {r['template']:45} {r.get('fields_count', 0)} fields × {len(r.get('languages', []))} langs")
            for k, v in (r.get("sample_nl") or {}).items():
                short_k = k.split(".")[-1].split(":")[0]
                print(f"       nl/{short_k}: {str(v)[:60]}")
        else:
            errs = r.get("errors", [])
            err_tag = f" {warn(f'⚠ {len(errs)} errors')}" if errs else ""
            print(f"  {ok()} {r['template']:45} {r.get('fields_registered', 0)} fields registered{err_tag}")

    print(f"\n── Summary ───────────────────────────────────────────────────────")
    print(f"  Templates  : {report['templates_translated']}")
    if not dry_run:
        print(f"  Fields     : {report['total_fields_registered']} registered across 10 languages")
    print(f"  Mode       : {'Dry run — nothing written' if dry_run else 'Live — translations published'}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
