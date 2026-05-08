"""SEO / GEO tool definitions for the orchestrator."""

from __future__ import annotations

from typing import Any

import anthropic
import structlog

from app.config import settings

log = structlog.get_logger()

TOOL_SPECS = [
    {
        "name": "seo_get_opportunities",
        "description": (
            "Analyze Google Search Console data to find keyword opportunities "
            "where Velluto ranks on page 2-3 and can improve with content updates."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "seo_generate_product_content",
        "description": "Generate SEO-optimized product title and description for a specific product.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "product_name": {"type": "string"},
                "target_keyword": {"type": "string"},
            },
            "required": ["product_id", "product_name", "target_keyword"],
        },
    },
    {
        "name": "seo_generate_geo_content",
        "description": (
            "Generate GEO (Generative Engine Optimization) content to improve Velluto's "
            "visibility in AI answers (ChatGPT, Perplexity, Claude). Writes structured "
            "FAQ, entity-rich paragraphs, and citation-worthy content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to create GEO content for"},
                "target_query": {"type": "string", "description": "The AI search query to target"},
            },
            "required": ["topic", "target_query"],
        },
    },
]


async def seo_get_opportunities() -> dict[str, Any]:
    try:
        from app.modules.gsc.client import GSCClient
        client = GSCClient()
        return await client.get_opportunities()
    except Exception as e:
        log.warning("seo.opportunities_failed", error=str(e))
        return {"opportunities": [], "error": str(e)}


async def seo_generate_product_content(
    product_id: str, product_name: str, target_keyword: str
) -> dict[str, Any]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": (
                    "You write SEO-optimized Shopify product copy for Velluto, a premium road "
                    "cycling eyewear brand. Be technical, performance-focused, and premium. "
                    "Output only valid JSON with keys: seo_title (50-60 chars), "
                    "seo_description (120-160 chars), product_description (150-200 words)."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write SEO content for: {product_name}\n"
                    f"Primary keyword: {target_keyword}\n"
                    f"Product ID: {product_id}\n\n"
                    "Output JSON only."
                ),
            }
        ],
    )
    import json
    text = response.content[0].text.strip()
    try:
        content = json.loads(text)
    except Exception:
        content = {"raw": text, "parse_error": True}

    return {"product_id": product_id, "content": content, "keyword": target_keyword}


async def seo_generate_geo_content(topic: str, target_query: str) -> dict[str, Any]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": (
                    "You write GEO (Generative Engine Optimization) content for Velluto cycling eyewear. "
                    "GEO content is structured to be cited by AI search engines. "
                    "Use: direct answers, statistics, entity definitions, FAQ format. "
                    "Output JSON: {answer_paragraph, faq_items: [{q, a}], key_entities: [], "
                    "citation_worthy_facts: []}."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Topic: {topic}\nTarget AI query: {target_query}\n\nOutput JSON only.",
            }
        ],
    )
    import json
    text = response.content[0].text.strip()
    try:
        content = json.loads(text)
    except Exception:
        content = {"raw": text}

    return {"topic": topic, "target_query": target_query, "geo_content": content}


EXECUTORS = {
    "seo_get_opportunities": seo_get_opportunities,
    "seo_generate_product_content": seo_generate_product_content,
    "seo_generate_geo_content": seo_generate_geo_content,
}
