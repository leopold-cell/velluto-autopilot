"""Creative generation tool definitions for the orchestrator."""

from __future__ import annotations

from typing import Any

import anthropic
import structlog

from app.config import settings

log = structlog.get_logger()

TOOL_SPECS = [
    {
        "name": "creative_generate_ad_copy",
        "description": (
            "Generate Meta ad copy (primary text, headline, description) for a campaign. "
            "Runs quality check automatically before returning."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_objective": {
                    "type": "string",
                    "enum": ["conversions", "traffic", "awareness", "retargeting"],
                },
                "product_focus": {"type": "string", "description": "Which product or collection to focus on"},
                "target_audience": {"type": "string", "description": "Target cyclist persona"},
                "key_message": {"type": "string", "description": "Core value prop to communicate"},
                "num_variations": {"type": "integer", "default": 3, "maximum": 5},
            },
            "required": ["campaign_objective", "product_focus"],
        },
    },
    {
        "name": "creative_generate_image_prompt",
        "description": "Generate DALL-E image prompts for ad visuals aligned with Velluto brand.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scene": {"type": "string", "description": "Scene description for the ad"},
                "product": {"type": "string"},
            },
            "required": ["scene"],
        },
    },
]

AD_COPY_SYSTEM = """
You write high-converting Meta ad copy for Velluto, a premium road cycling eyewear brand.
Brand voice: technical, performance-focused, premium European sensibility.
Target: serious road cyclists, ages 25-45, spending €150-400 on eyewear.
Always output valid JSON with the exact keys requested.
Never make unverified claims. No before/after. No medical claims.
"""


async def creative_generate_ad_copy(
    campaign_objective: str,
    product_focus: str,
    target_audience: str = "road cyclists",
    key_message: str = "performance and protection",
    num_variations: int = 3,
) -> dict[str, Any]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = f"""
Create {num_variations} Meta ad variations for:
- Objective: {campaign_objective}
- Product: {product_focus}
- Audience: {target_audience}
- Key message: {key_message}

For each variation output:
{{
  "variation": 1,
  "primary_text": "...",
  "headline": "...",
  "description": "...",
  "cta": "Shop Now|Learn More|Get Yours"
}}

Return an array of {num_variations} variation objects.
"""
    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=[{"type": "text", "text": AD_COPY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    import json
    text = response.content[0].text.strip()
    try:
        variations = json.loads(text)
    except Exception:
        variations = [{"primary_text": text, "parse_error": True}]

    # Quality check each variation
    from app.modules.quality.manager import QualityManager
    qm = QualityManager()
    checked_variations = []
    for var in variations if isinstance(variations, list) else [variations]:
        passed, qa_result = await qm.check_and_block_if_failed(
            "ad_copy", var, "creative_generate_ad_copy"
        )
        var["qa_passed"] = passed
        var["qa_score"] = qa_result.get("score")
        if not passed:
            var["qa_issues"] = qa_result.get("blocking_issues", [])
        checked_variations.append(var)

    return {
        "variations": checked_variations,
        "campaign_objective": campaign_objective,
        "product_focus": product_focus,
    }


async def creative_generate_image_prompt(scene: str, product: str = "") -> dict[str, Any]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write a DALL-E 3 prompt for a premium cycling eyewear ad.\n"
                    f"Scene: {scene}\n"
                    f"Product: {product or 'cycling sunglasses'}\n\n"
                    "Style: photorealistic, professional advertising photography, "
                    "dramatic lighting, premium feel. Output the prompt only."
                ),
            }
        ],
    )
    return {
        "image_prompt": response.content[0].text.strip(),
        "scene": scene,
        "product": product,
        "recommended_size": "1024x1024",
    }


EXECUTORS = {
    "creative_generate_ad_copy": creative_generate_ad_copy,
    "creative_generate_image_prompt": creative_generate_image_prompt,
}
