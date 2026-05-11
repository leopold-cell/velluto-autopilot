"""
Velluto Autopilot Orchestrator.

The main AI agent — powered by Claude with tool use.
Each cycle:
  1. Fetches KPI dashboard
  2. Runs Claude with all available tools to decide what to do
  3. For each tool call: checks risk, executes or routes to approval
  4. Logs everything to audit log
  5. Records rollback information for every mutation

Claude sees a 2000-token cached system prompt and the current KPI state.
Tool calls are dispatched to module executors.
High-risk actions are held in the approval engine (WhatsApp confirmation).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import anthropic
import structlog

from app.config import settings
from app.database import AsyncSessionLocal
from app.engines.approval import ApprovalEngine, classify_risk
from app.engines.rollback import RollbackEngine
from app.models.audit import AuditLog
from app.models.task import Task, TaskStatus
from app.modules.token_optimizer.optimizer import TokenOptimizer

log = structlog.get_logger()

# ── Assemble all tool specs ───────────────────────────────────────────────────

from app.modules.shopify.tools import TOOL_SPECS as SHOPIFY_SPECS, EXECUTORS as SHOPIFY_EXEC
from app.modules.meta_ads.tools import TOOL_SPECS as META_SPECS, EXECUTORS as META_EXEC
from app.modules.kpi.tools import TOOL_SPECS as KPI_SPECS
from app.modules.seo.tools import TOOL_SPECS as SEO_SPECS, EXECUTORS as SEO_EXEC
from app.modules.email_marketing.tools import TOOL_SPECS as EMAIL_SPECS, EXECUTORS as EMAIL_EXEC
from app.modules.competitor.tools import TOOL_SPECS as COMPETITOR_SPECS, EXECUTORS as COMPETITOR_EXEC
from app.modules.creative.tools import TOOL_SPECS as CREATIVE_SPECS, EXECUTORS as CREATIVE_EXEC

ALL_TOOL_SPECS = (
    KPI_SPECS
    + SHOPIFY_SPECS
    + META_SPECS
    + SEO_SPECS
    + EMAIL_SPECS
    + COMPETITOR_SPECS
    + CREATIVE_SPECS
)

# Actions that return mutations (need rollback registration)
MUTATION_ACTIONS = {
    "shopify_update_product_price",
    "shopify_update_product_seo",
    "shopify_create_discount",
    "meta_adjust_campaign_budget",
    "meta_pause_campaign",
    "email_send_campaign",
    "email_trigger_flow",
}

_pixel_training_block = f"""
PIXEL TRAINING MODE: ACTIVE
Meta pixel is currently being trained using Add-to-Cart (ATC) campaigns.
This is intentional. Do NOT treat 0 purchase ROAS as an error or suggest pausing campaigns.

Current phase goal: collect {settings.pixel_training_events_target} purchase events on the pixel.
Primary metrics to track in this phase:
  - ATC count (add_to_cart actions) — more is better
  - Cost per ATC — should trend down as pixel learns
  - ATC rate (ATCs / impressions) — signals audience relevance
  - CTR — creative performance proxy

Do NOT recommend:
  - Pausing ATC campaigns due to 0 ROAS
  - Switching to Purchase campaigns until {settings.pixel_training_events_target} purchases are logged
  - Treating low ROAS as a critical issue

DO recommend:
  - Adjusting ATC campaign budgets if cost-per-ATC is too high (>€15)
  - Refreshing creatives if CTR drops below 1%
  - SEO, email, and competitor actions as the primary growth levers right now
  - Monitoring organic and direct purchases separately
""" if settings.pixel_training_mode else ""

SYSTEM_PROMPT = f"""
You are Velluto Autopilot — the autonomous growth agent for Velluto, a premium road cycling eyewear brand.

YOUR MISSION:
- Drive {settings.daily_sales_target} eyewear sales per day ({settings.monthly_sales_target}/month)
- Optimize Meta Ads ROAS (target: ≥3.0x) — see pixel training note below if active
- Improve organic search rankings for high-intent cycling eyewear keywords
- Maximize email revenue through smart automation
- Monitor competitors and identify positioning opportunities
{_pixel_training_block}
YOUR APPROACH:
1. Always start by calling kpi_get_dashboard to understand current state
2. Identify the biggest gap vs target (sales pace, ROAS, SEO, email)
3. Take the highest-leverage action available
4. Be conservative: prefer 1-2 focused actions per cycle over spraying changes
5. Always provide a `reason` field explaining WHY you're taking each action

RISK AWARENESS:
- Low risk (auto-execute): SEO updates, reading data, generating creatives, minor ad adjustments
- High risk (requires human approval via WhatsApp): price changes, discounts, budget increases >10%,
  mass emails, checkout changes, homepage edits, guarantee changes, legal claims

BRAND STANDARDS:
- Premium road cycling: technical, performance-focused, European sensibility
- Never discount without strategic reason
- Never make unverified performance or safety claims
- All content goes through quality check before publishing

OUTPUT FORMAT:
Think step by step. Use tools to gather data, then act. After each action, evaluate if more is needed.
When you have executed your planned actions, stop and summarize what you did and what to watch.
"""


class Orchestrator:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.token_optimizer = TokenOptimizer()

    async def run_cycle(
        self,
        task_id: uuid.UUID | None = None,
        trigger: str = "scheduler",
        dry_run: bool = False,
        focus: str | None = None,
    ) -> dict[str, Any]:
        cycle_start = time.monotonic()
        task_id = task_id or uuid.uuid4()

        log.info("orchestrator.cycle_start", task_id=str(task_id), trigger=trigger, dry_run=dry_run)

        async with AsyncSessionLocal() as db:
            task = Task(
                id=task_id,
                name=f"orchestrator_cycle_{trigger}",
                trigger=trigger,
                status=TaskStatus.running,
                started_at=datetime.now(timezone.utc),
                input_data={"dry_run": dry_run, "focus": focus},
            )
            db.add(task)
            await db.commit()

            approval_engine = ApprovalEngine(db)
            rollback_engine = RollbackEngine(db)

            try:
                result = await self._run_agent_loop(
                    db=db,
                    task_id=task_id,
                    approval_engine=approval_engine,
                    rollback_engine=rollback_engine,
                    dry_run=dry_run,
                    focus=focus,
                )

                task.status = TaskStatus.completed
                task.completed_at = datetime.now(timezone.utc)
                task.result = result
                task.total_tokens = result.get("total_tokens", 0)
                task.actions_executed = result.get("actions_executed", 0)
                task.actions_pending = result.get("actions_pending_approval", 0)
                await db.commit()

                duration_ms = int((time.monotonic() - cycle_start) * 1000)
                log.info(
                    "orchestrator.cycle_complete",
                    task_id=str(task_id),
                    duration_ms=duration_ms,
                    actions=task.actions_executed,
                    pending=task.actions_pending,
                )
                return result

            except Exception as e:
                task.status = TaskStatus.failed
                task.error = str(e)
                task.completed_at = datetime.now(timezone.utc)
                await db.commit()
                log.error("orchestrator.cycle_failed", task_id=str(task_id), error=str(e))

                from app.engines.monitoring import MonitoringEngine
                monitor = MonitoringEngine(db)
                await monitor.alert_critical(
                    f"Orchestrator cycle failed: {e}",
                    context={"task_id": str(task_id), "trigger": trigger},
                )
                raise

    async def _run_agent_loop(
        self,
        db,
        task_id: uuid.UUID,
        approval_engine: ApprovalEngine,
        rollback_engine: RollbackEngine,
        dry_run: bool,
        focus: str | None,
    ) -> dict[str, Any]:
        messages: list[dict] = []
        total_tokens = 0
        actions_executed = 0
        actions_pending = 0
        action_log: list[dict] = []

        # Initial user message
        user_content = "Run your growth optimization cycle. Start with the KPI dashboard."
        if focus:
            user_content += f" Focus specifically on: {focus}."
        if dry_run:
            user_content += " This is a DRY RUN — simulate actions but do not execute them."

        messages.append({"role": "user", "content": user_content})

        # Agentic loop — max 10 iterations to prevent infinite loops
        for iteration in range(10):
            response = await self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.anthropic_max_tokens,
                system=self.token_optimizer.get_cached_system_block(SYSTEM_PROMPT),
                tools=ALL_TOOL_SPECS,
                messages=messages,
            )

            # Track token usage
            usage = response.usage
            await self.token_optimizer.track_usage(
                task_id=str(task_id),
                action=f"orchestrator_iter_{iteration}",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0),
            )
            total_tokens += usage.input_tokens + usage.output_tokens

            # Add assistant response to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Check stop condition
            if response.stop_reason == "end_turn":
                break

            if response.stop_reason != "tool_use":
                break

            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                action_id = uuid.uuid4()

                log.info(
                    "orchestrator.tool_call",
                    tool=tool_name,
                    task_id=str(task_id),
                    iteration=iteration,
                )

                t_start = time.monotonic()
                try:
                    tool_result = await self._dispatch_tool(
                        tool_name=tool_name,
                        tool_input=tool_input,
                        action_id=action_id,
                        task_id=task_id,
                        db=db,
                        approval_engine=approval_engine,
                        rollback_engine=rollback_engine,
                        dry_run=dry_run,
                    )
                    t_ms = int((time.monotonic() - t_start) * 1000)

                    status = tool_result.get("status", "success")
                    if status == "pending_approval":
                        actions_pending += 1
                    elif status not in ("error", "skipped"):
                        if tool_name in MUTATION_ACTIONS:
                            actions_executed += 1

                    action_log.append({
                        "action_id": str(action_id),
                        "tool": tool_name,
                        "status": status,
                        "duration_ms": t_ms,
                    })

                    # Audit log
                    audit = AuditLog(
                        action=tool_name,
                        module=tool_name.split("_")[0],
                        input_data=tool_input,
                        output_data=tool_result,
                        status="success" if status != "error" else "failure",
                        dry_run=dry_run,
                        duration_ms=t_ms,
                        task_id=task_id,
                    )
                    db.add(audit)
                    await db.commit()

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(tool_result),
                    })

                except Exception as e:
                    log.error("orchestrator.tool_error", tool=tool_name, error=str(e))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps({"error": str(e)}),
                        "is_error": True,
                    })

            messages.append({"role": "user", "content": tool_results})

        # Extract final text summary
        summary = ""
        for block in response.content:
            if hasattr(block, "text"):
                summary = block.text
                break

        return {
            "summary": summary,
            "total_tokens": total_tokens,
            "iterations": iteration + 1,
            "actions_executed": actions_executed,
            "actions_pending_approval": actions_pending,
            "action_log": action_log,
        }

    async def _dispatch_tool(
        self,
        tool_name: str,
        tool_input: dict,
        action_id: uuid.UUID,
        task_id: uuid.UUID,
        db,
        approval_engine: ApprovalEngine,
        rollback_engine: RollbackEngine,
        dry_run: bool,
    ) -> dict[str, Any]:
        # Build db-aware KPI executors
        from app.modules.kpi.tools import make_executors as make_kpi_exec
        kpi_executors = make_kpi_exec(db)

        all_executors = {
            **kpi_executors,
            **SHOPIFY_EXEC,
            **META_EXEC,
            **SEO_EXEC,
            **EMAIL_EXEC,
            **COMPETITOR_EXEC,
            **CREATIVE_EXEC,
        }

        executor = all_executors.get(tool_name)
        if not executor:
            return {"error": f"unknown_tool: {tool_name}"}

        # Inject dry_run for mutation tools
        if tool_name in MUTATION_ACTIONS:
            tool_input = {**tool_input, "dry_run": dry_run}

        risk = classify_risk(tool_name, tool_input)

        # High risk → approval engine
        if risk in ("high", "critical") and not dry_run:
            dry_run_result = None
            if tool_name in MUTATION_ACTIONS:
                try:
                    dry_run_result = await executor(**{**tool_input, "dry_run": True})
                except Exception:
                    pass

            return await approval_engine.request(
                action=tool_name,
                module=tool_name.split("_")[0],
                payload=tool_input,
                reason=tool_input.get("reason", "orchestrator decision"),
                dry_run_result=dry_run_result,
                executor=lambda p: executor(**p),
            )

        # Execute directly
        result = await executor(**tool_input)

        # Register rollback for mutations
        if tool_name in MUTATION_ACTIONS and not dry_run and result.get("updated"):
            inverse = self._build_inverse(tool_name, tool_input, result)
            if inverse:
                await rollback_engine.register(
                    action_id=action_id,
                    action=tool_name,
                    module=tool_name.split("_")[0],
                    forward_payload=tool_input,
                    inverse_action=inverse["action"],
                    inverse_payload=inverse["payload"],
                )

        return result

    def _build_inverse(self, action: str, payload: dict, result: dict) -> dict | None:
        """Build the inverse operation for a given action."""
        if action == "shopify_update_product_price":
            # Inverse: restore to the previous price (stored in result if available)
            return None  # Price rollback requires fetching original price first

        if action == "meta_adjust_campaign_budget":
            return {
                "action": "meta_adjust_campaign_budget",
                "payload": {
                    "campaign_id": payload["campaign_id"],
                    "new_daily_budget": payload.get("current_budget", 0),
                    "reason": f"rollback of: {payload.get('reason', 'budget change')}",
                },
            }

        if action == "meta_pause_campaign":
            return {
                "action": "meta_resume_campaign",
                "payload": {"campaign_id": payload["campaign_id"]},
            }

        return None
