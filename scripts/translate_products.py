"""
Run product translation for all Shopify products.

Usage:
  python scripts/translate_products.py          # live run
  python scripts/translate_products.py --dry-run # preview only, no writes
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.translations.translator import translate_all_products


def ok(s=""): return f"\033[32m{s or '✓'}\033[0m"
def warn(s=""): return f"\033[33m{s or '⚠'}\033[0m"
def err(s=""): return f"\033[31m{s or '✗'}\033[0m"


async def main():
    dry_run = "--dry-run" in sys.argv
    mode = "DRY RUN — no writes" if dry_run else "LIVE — translating & publishing"
    print(f"\n── Velluto Product Translator [{mode}] ────────────────────────\n")

    report = await translate_all_products(dry_run=dry_run)

    print(f"\n── Results ───────────────────────────────────────────────────────")
    for r in report["results"]:
        if r.get("skipped"):
            print(f"  {warn('–')} {r['product'][:50]:50} SKIPPED ({r.get('reason')})")
            continue
        if r.get("error"):
            print(f"  {err()} {r['product'][:50]:50} ERROR: {r['error']}")
            continue

        qa = r.get("qa_issues", [])
        if dry_run:
            sample = r.get("sample", {})
            nl_title = sample.get("nl", "?")
            de_title = sample.get("de", "?")
            print(f"  {ok()} {r['product'][:45]:45} → nl: {str(nl_title)[:30]}  de: {str(de_title)[:30]}")
        else:
            fields = r.get("fields_registered", 0)
            qa_tag = f" {warn(f'⚠ {len(qa)} QA issues')}" if qa else ""
            print(f"  {ok()} {r['product'][:50]:50} {fields} fields registered{qa_tag}")

        for issue in r.get("qa_issues", []):
            print(f"       {warn('⚠')} {issue}")

    print(f"\n── Summary ───────────────────────────────────────────────────────")
    print(f"  Products   : {report['products_translated']}")
    if not dry_run:
        print(f"  Fields     : {report['total_fields_registered']} registered across 10 languages")
    print(f"  QA issues  : {report['total_qa_issues']}")
    print(f"  Mode       : {'Dry run — nothing written' if dry_run else 'Live — translations published'}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
