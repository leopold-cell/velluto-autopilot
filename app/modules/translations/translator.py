"""
Product Translation Engine.

For each Shopify product:
1. Fetch translatable fields + content digests via GraphQL
2. Send all fields to Claude in one call → JSON with all 10 languages
3. Quality-check that brand terms are preserved
4. Register translations via translationsRegister mutation

One Claude call per product covers all 10 languages simultaneously.
Prompt caching keeps cost minimal on re-runs.
"""

from __future__ import annotations

import json
import re
from typing import Any

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

TRANSLATE_KEYS = {"title", "body_html", "meta_title", "meta_description", "product_type"}
LANG_BATCH_SIZE = 3  # languages per Claude call when chunking large body_html

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

# Terms that must NEVER be translated — preserve exactly as-is
PROTECTED_TERMS = [
    "Velluto", "StradaPro", "VellutoPuro", "VellutoVisione",
    "Nero", "Viola", "Espresso", "Arancia",
    "Dolce Vita", "TACX", "UV400",
]

SYSTEM_PROMPT = """You are a professional e-commerce translator for Velluto, a premium Dutch road cycling eyewear brand.

CRITICAL BRAND RULES — never break these:
- NEVER translate these terms — keep them exactly as written: Velluto, StradaPro, VellutoPuro, VellutoVisione, Nero, Viola, Espresso, Arancia, Dolce Vita, TACX, UV400
- Maintain a premium, technical, performance-focused tone in every language
- Preserve all HTML tags exactly — only translate the visible text content inside them
- Keep SEO titles under 60 characters and meta descriptions under 160 characters
- For Dutch (nl): use informal "je/jij" not formal "u"
- For German (de): capitalize nouns correctly

OUTPUT: Return valid JSON only — no markdown, no explanation. Structure:
{
  "nl": {"title": "...", "body_html": "...", "meta_title": "...", "meta_description": "...", "product_type": "..."},
  "de": {...},
  "fr": {...},
  "es": {...},
  "it": {...},
  "pt-PT": {...},
  "pl": {...},
  "sv": {...},
  "da": {...},
  "nb": {...}
}
Only include keys that were present in the input."""


async def _gql(client: httpx.AsyncClient, query: str, variables: dict = {}) -> dict:
    r = await client.post(GQL_URL, headers=GQL_HEADERS,
                          json={"query": query, "variables": variables})
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL: {data['errors']}")
    return data["data"]


QUERY_ALL_PRODUCTS = """
query($cursor: String) {
  products(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes { id title }
  }
}
"""

QUERY_TRANSLATABLE = """
query($id: ID!) {
  translatableResource(resourceId: $id) {
    resourceId
    translatableContent { key value digest locale }
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


async def fetch_all_products(client: httpx.AsyncClient) -> list[dict]:
    products = []
    cursor = None
    while True:
        data = await _gql(client, QUERY_ALL_PRODUCTS, {"cursor": cursor})
        page = data["products"]
        products.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return products


async def fetch_translatable_content(client: httpx.AsyncClient, product_id: str) -> list[dict]:
    data = await _gql(client, QUERY_TRANSLATABLE, {"id": product_id})
    return data["translatableResource"]["translatableContent"]


def _build_translation_prompt(fields: dict[str, str]) -> str:
    lines = ["Translate the following Shopify product fields into all 10 languages.\n"]
    for key, value in fields.items():
        lines.append(f"[{key}]\n{value}\n")
    return "\n".join(lines)


def _validate_brand_terms(original: str, translated: str) -> list[str]:
    issues = []
    for term in PROTECTED_TERMS:
        if term in original and term not in translated:
            issues.append(f"'{term}' missing in translation")
    return issues


async def translate_product(
    product_id: str,
    product_title: str,
    content: list[dict],
    dry_run: bool = False,
) -> dict[str, Any]:
    claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Build input dict — only translatable keys with actual values
    fields = {
        c["key"]: c["value"]
        for c in content
        if c["key"] in TRANSLATE_KEYS and c["value"]
    }
    digest_map = {c["key"]: c["digest"] for c in content}

    if not fields:
        return {"product": product_title, "skipped": True, "reason": "no translatable content"}

    prompt = _build_translation_prompt(fields)

    log.info("translator.claude_call", product=product_title, fields=list(fields.keys()))

    # Estimate output size: 10 languages × fields × ~200 chars avg
    estimated_output = len(fields) * len(LANGUAGES) * 200
    max_tok = min(settings.anthropic_max_tokens, max(4096, estimated_output // 3))

    response = await claude.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tok,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # If response was cut off, try a repair call; failure is caught downstream
    if response.stop_reason == "max_tokens":
        log.warning("translator.response_truncated", product=product_title)
        try:
            repair = await claude.messages.create(
                model=settings.anthropic_model,
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "The JSON was cut off. Complete it from where it stopped. Output only the remaining valid JSON to close the structure."},
                ],
            )
            raw = raw + repair.content[0].text.strip()
        except Exception as e:
            log.warning("translator.repair_failed", product=product_title, error=str(e))

    try:
        translations: dict[str, dict] = json.loads(raw)
    except json.JSONDecodeError:
        # body_html is too large — translate slim fields first, then chunk body_html separately
        log.warning("translator.retrying_chunked", product=product_title)
        slim_fields = {k: v for k, v in fields.items() if k != "body_html"}
        if not slim_fields:
            return {"product": product_title, "error": "JSON parse failed and no slim fields available"}

        slim_prompt = _build_translation_prompt(slim_fields)
        r2 = await claude.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": slim_prompt}],
        )
        raw2 = re.sub(r"^```json\s*", "", r2.content[0].text.strip())
        raw2 = re.sub(r"\s*```$", "", raw2)
        try:
            translations = json.loads(raw2)
        except json.JSONDecodeError as e:
            log.error("translator.json_parse_failed_final", product=product_title, error=str(e))
            return {"product": product_title, "error": f"JSON parse failed after retry: {e}"}

        # Now translate body_html in batches of LANG_BATCH_SIZE languages
        if "body_html" in fields:
            log.info("translator.chunking_body_html", product=product_title)
            lang_items = list(LANGUAGES.items())
            for i in range(0, len(lang_items), LANG_BATCH_SIZE):
                batch = dict(lang_items[i : i + LANG_BATCH_SIZE])
                batch_names = ", ".join(batch.values())
                batch_prompt = (
                    f"Translate the following product description into ONLY these languages: {batch_names}.\n"
                    f"Return JSON with ONLY these locale keys: {list(batch.keys())}.\n\n"
                    f"[body_html]\n{fields['body_html']}\n"
                )
                rb = await claude.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=6000,
                    system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": batch_prompt}],
                )
                raw_b = re.sub(r"^```json\s*", "", rb.content[0].text.strip())
                raw_b = re.sub(r"\s*```$", "", raw_b)
                try:
                    batch_result: dict = json.loads(raw_b)
                    for locale, locale_fields in batch_result.items():
                        if locale not in translations:
                            translations[locale] = {}
                        if isinstance(locale_fields, dict):
                            translations[locale]["body_html"] = locale_fields.get("body_html", "")
                        elif isinstance(locale_fields, str):
                            translations[locale]["body_html"] = locale_fields
                except json.JSONDecodeError as e:
                    log.warning("translator.body_html_chunk_failed", product=product_title,
                                batch=list(batch.keys()), error=str(e))

    # Quality check
    qa_issues: list[str] = []
    for locale, translated_fields in translations.items():
        for key, translated_value in translated_fields.items():
            original = fields.get(key, "")
            issues = _validate_brand_terms(original, translated_value)
            for issue in issues:
                qa_issues.append(f"{locale}/{key}: {issue}")

    if qa_issues:
        log.warning("translator.qa_issues", product=product_title, issues=qa_issues)

    if dry_run:
        return {
            "product": product_title,
            "product_id": product_id,
            "dry_run": True,
            "languages": list(translations.keys()),
            "fields": list(fields.keys()),
            "qa_issues": qa_issues,
            "sample": {k: v.get("title") for k, v in translations.items()},
        }

    # Register translations
    async with httpx.AsyncClient(timeout=30) as client:
        registered = 0
        errors = []
        for locale, translated_fields in translations.items():
            inputs = []
            for key, value in translated_fields.items():
                if key not in digest_map:
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
                "resourceId": product_id,
                "translations": inputs,
            })
            errs = result["translationsRegister"]["userErrors"]
            if errs:
                errors.extend([f"{locale}: {e['message']}" for e in errs])
            else:
                registered += len(inputs)

    return {
        "product": product_title,
        "product_id": product_id,
        "languages_translated": list(translations.keys()),
        "fields_registered": registered,
        "qa_issues": qa_issues,
        "errors": errors,
    }


async def translate_all_products(dry_run: bool = False) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        products = await fetch_all_products(client)
        log.info("translator.products_found", count=len(products))

        results = []
        for product in products:
            content = await fetch_translatable_content(client, product["id"])
            result = await translate_product(
                product_id=product["id"],
                product_title=product["title"],
                content=content,
                dry_run=dry_run,
            )
            results.append(result)
            status = "DRY RUN" if dry_run else f"{result.get('fields_registered', 0)} fields"
            log.info("translator.product_done", product=product["title"], status=status)

    total_fields = sum(r.get("fields_registered", 0) for r in results)
    total_qa = sum(len(r.get("qa_issues", [])) for r in results)

    return {
        "products_translated": len(results),
        "total_fields_registered": total_fields,
        "total_qa_issues": total_qa,
        "dry_run": dry_run,
        "results": results,
    }
