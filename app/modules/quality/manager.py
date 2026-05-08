"""
Quality Manager Agent.
Reviews all content and structural changes before they go live.
Uses a separate Claude call to maintain independence from the orchestrator.
"""

from __future__ import annotations

from typing import Any

import anthropic
import structlog

from app.config import settings

log = structlog.get_logger()

BRAND_GUIDELINES = """
Velluto is a premium road cycling eyewear brand. Quality standards:

BRAND VOICE:
- Premium, technical, confident but not arrogant
- Cyclist-first: speak to performance, protection, aerodynamics
- European sensibility: understated elegance
- Never use: "cheap", "affordable", "budget", "cheap alternative"

PROHIBITED CLAIMS:
- No unverified safety claims (e.g., "ANSI rated" without cert)
- No competitor comparisons without evidence
- No superlatives without proof ("the fastest", "the best")
- No medical/health claims

SEO QUALITY:
- Titles: 50–60 characters
- Meta descriptions: 120–160 characters
- Must include primary keyword naturally
- No keyword stuffing

AD COPY QUALITY:
- Must pass Facebook advertising policies
- No before/after health claims
- Price claims must be accurate
- CTA must be clear and compliant

PRICING:
- Never discount more than 30% without approval
- Bundle prices must show genuine value
- No fake strikethrough pricing
"""


class QualityManager:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def check(
        self,
        content_type: str,
        content: dict | str,
        action: str,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """
        content_type: ad_copy | seo_content | email | product_description | pricing | discount
        content: the actual content to review
        Returns: {passed: bool, score: int (0-100), issues: list, suggestions: list}
        """
        prompt = self._build_prompt(content_type, content, action, context)

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": (
                        "You are Velluto's Quality Manager. Your job is to review content "
                        "before it goes live and ensure it meets brand standards, is factually accurate, "
                        "legally safe, and on-brand. Be strict. Output only valid JSON."
                    ),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        try:
            import json
            result = json.loads(raw)
        except Exception:
            result = {"passed": False, "score": 0, "issues": ["Failed to parse QA response"], "raw": raw}

        log.info(
            "quality.check",
            action=action,
            content_type=content_type,
            passed=result.get("passed"),
            score=result.get("score"),
            issues=len(result.get("issues", [])),
        )
        return result

    def _build_prompt(
        self,
        content_type: str,
        content: Any,
        action: str,
        context: dict | None,
    ) -> str:
        import json
        content_str = json.dumps(content, indent=2) if isinstance(content, dict) else str(content)
        ctx_str = json.dumps(context, indent=2) if context else "none"

        return f"""
Review this {content_type} for quality, brand compliance, and safety before it goes live.

## Brand Guidelines
{BRAND_GUIDELINES}

## Action Being Taken
{action}

## Content to Review
```
{content_str}
```

## Context
{ctx_str}

## Your Task
Evaluate this content and respond with ONLY this JSON structure:
{{
  "passed": true/false,
  "score": 0-100,
  "blocking_issues": ["list of issues that must be fixed before going live"],
  "warnings": ["non-blocking concerns"],
  "suggestions": ["optional improvements"],
  "summary": "one sentence verdict"
}}

A score ≥ 80 with no blocking issues = passed.
Be strict about safety claims, accuracy, and brand voice.
"""

    async def check_and_block_if_failed(
        self,
        content_type: str,
        content: Any,
        action: str,
        context: dict | None = None,
        min_score: int = 80,
    ) -> tuple[bool, dict]:
        result = await self.check(content_type, content, action, context)
        blocking = result.get("blocking_issues", [])
        score = result.get("score", 0)
        passed = score >= min_score and len(blocking) == 0
        result["passed"] = passed
        return passed, result
