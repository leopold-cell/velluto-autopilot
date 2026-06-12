# Velluto — StradaPro Kit Switcher & Bundle Page (TEST)

Test implementation for **velluto-shop.com** (theme: **Stretch v1.4.1**) of:

1. a **Daily-Elements-style kit switcher directly on the PDP** — switch
   between Starter / Performance / Ultimate Kit without leaving the page,
   plus the existing color switch,
2. a bundle landing page comparing the three kits.

**Theme changes deploy to an unpublished theme copy only — never the live
theme.** The one approved live change is renaming the 4 StradaPro products
(`--rename-live`).

## Catalog model (approved)

| Kit | Products | Price | Contents |
| --- | --- | --- | --- |
| **Starter Kit** | the 4 **existing** StradaPro color products, renamed to `Velluto StradaPro \| Starter Kit \| {Color}` (handles unchanged for SEO/ads) | **€69** (was €149; compare-at €108 — applied with `--reprice-live`) | Strada Pro + Visione™ Lens |
| **Performance Kit** | 4 **new** products `velluto-stradapro-performance-kit-{color}` | €99 (compare-at €146 value) | + Clear Lens, Hard Case |
| **Ultimate Kit** | 4 **new** products `velluto-stradapro-ultimate-kit-{color}` | €119 (compare-at €162 value) | + Cleaning Spray, Microfiber Cloth, Bottle |

Colors: Nero / Arancia / Espresso / Viola — one product per kit×color,
matching the store's existing one-product-per-color architecture.

Pricing ladder €69 / €99 / €119 — Starter does **not** qualify for free
shipping (from €99); Performance and Ultimate do. Note on markets: the
script sets the base (EUR) price; markets with automatic conversion follow
it, but any **fixed per-market price lists** (Shopify Markets, e.g. the
DKK/NOK/PLN/SEK prices in seo-bot's `commercial_config.py`) must be
adjusted separately in the admin.

## How the switchers work

Both switchers are **links between sibling products** (the same mechanic as
the live `velluto_color_swatches` block), driven by product metafields
(namespace `velluto`) — no hardcoded handles, no JS required on the PDP:

| Metafield | Example | Drives |
| --- | --- | --- |
| `kit_siblings` | `velluto-stradapro-cycling-glasses-nero,velluto-stradapro-performance-kit-nero,velluto-stradapro-ultimate-kit-nero` | kit switcher (same color, kit order) |
| `kit_label` / `kit_tagline` / `kit_badge` | `Performance Kit` / `Every condition covered` / `Most Popular` | switcher card content |
| `color_siblings` / `color_label` | handles of the 4 colors of one kit / `Nero` | color switcher on the new kit products |
| `included_items` | one item per line | included-items section, landing cards, comparison table |

The kit-switcher snippet renders **nothing** when `kit_siblings` is absent,
so it is safe inside the shared product template (accessories unaffected).
`all_products[...]` only resolves active products, so draft kits silently
drop out.

## Files

| File | Purpose |
| --- | --- |
| `snippets/velluto-kit-switcher.liquid` + `assets/velluto-kit-switcher.css` | The PDP kit switcher: radio-style cards (name, tagline, price, "€X value", "Most Popular" badge), inserted as a Custom Liquid block above the buy buttons. |
| `snippets/velluto-bundle-color-swatches.liquid` | Metafield-driven color switcher for the new kit products (existing 4 keep their hardcoded block); same `vcol-*` classes/`velluto-product.css` as live. |
| `sections/velluto-bundle-included-items.liquid` | Included items + free-shipping message (renders at/above the €99 threshold) for the kit PDPs. |
| `sections/velluto-bundle-landing.liquid` + `templates/page.velluto-bundles-test.json` | Bundle landing page (hero, three cards with Most Popular badge + color swatches, trust row, auto-generated comparison table), pre-wired to the kit products. |
| `preview/pdp-kit-switcher-preview.html` | Static PDP mockup with working kit + color switching, real CDN imagery — open in any browser. |
| `preview/bundle-page-preview.html` | Static landing-page mockup. |
| `scripts/deploy_kits.py` | One-shot deploy (see below). |

## Deploy (`scripts/deploy_kits.py`)

Needs `SHOPIFY_TOKEN` (scopes: `write_themes`, `write_products`,
`write_content`) and optionally `SHOPIFY_STORE` (defaults to
`velluto-brand.myshopify.com`) — same env vars as seo-bot.

```
python3 deploy_kits.py --list-themes
python3 deploy_kits.py --theme-id <COPY_ID> --dry-run
python3 deploy_kits.py --theme-id <COPY_ID> --rename-live --reprice-live
```

What it does, in order:

1. Uploads the sections/snippets/asset/page template to the **theme copy**
   (refuses the live theme).
2. Patches the copy's `templates/product.json`: adds the kit-switcher
   Custom Liquid block above the buy buttons (idempotent).
3. Builds `templates/product.velluto-bundle.json` from the copy's real
   product template (gallery/accordions/reviews/trust badges carry over
   1:1), swapping the hardcoded color-swatch block for the metafield-driven
   snippet and appending the included-items section.
4. Creates the 8 kit products — **active** (drafts wouldn't render, so the
   switcher couldn't be tested) but in no collection or menu, tagged
   `kit, test`, with metafields and the matching StradaPro color imagery.
5. Sets kit metafields on the 4 existing products; with `--rename-live`
   also renames them and with `--reprice-live` sets them to €69
   (compare-at €108). Old titles/prices saved to
   `kit_rename_rollback.json`.
6. Creates the hidden landing page `/pages/strada-pro-sets-test`.

## Verify on the theme copy preview

- `/products/velluto-stradapro-cycling-glasses-nero`: kit switcher shows
  Starter selected; Performance carries the "Most Popular" badge; clicking
  Performance lands on the Performance Kit PDP in Nero with the kit and
  color switchers in the right state.
- All 4 colors × 3 kits navigate correctly in both switchers.
- Kit PDPs show included items + "free shipping" (€99/€119 ≥ €99).
- Accessory PDPs render unchanged.
- `/pages/strada-pro-sets-test`: landing page, mobile = Performance first.

## Rollback

- Theme: changes exist only on the copy.
- Products: the 8 kits are unlinked — set to draft or delete; restore the
  4 original titles from `kit_rename_rollback.json`.

## EU Withdrawal Button (live by June 19, 2026)

Required by Directive (EU) 2023/2673 for stores selling to EU buyers.
Implementation (deployed **live**, unlike the kit test):

| Requirement | Implementation |
| --- | --- |
| Clearly visible, continuously available button/link | "Right of withdrawal" link in the footer menu (added by `deploy_withdrawal.py` via GraphQL, or 1-minute manual step) → `/pages/withdrawal` |
| Two-step confirmation (name + order reference) | `sections/velluto-withdrawal-form.liquid`: step 1 details, step 2 summary + "Withdraw from contract now". No-JS fallback: single step with explicit confirmation checkbox. |
| Merchant-side record | Submission uses Shopify's native contact form → store contact inbox, subject-tagged `[Withdrawal]`, includes submission timestamp. |
| Automatic confirmation email (content + timestamp) | Client-side Klaviyo event `Withdrawal Requested` (public site key `W24JTE`, a section setting) triggers a flow that sends template **`SQQ2zG` "Withdrawal Confirmation (EU Widerruf)"** (already created in Klaviyo). |

Deploy: `python3 scripts/deploy_withdrawal.py --theme-id <ID> [--live-ok]` —
uploads section + `templates/page.withdrawal.json`, creates the published
page `/pages/withdrawal`, appends the footer menu link. `--live-ok` is
required to target the live theme. QA on the copy first, then live before
**June 19**.

Remaining manual steps:
1. **Klaviyo flow** (API cannot create flows): Flows → Create → trigger =
   metric "Withdrawal Requested" → Email → use template "Withdrawal
   Confirmation (EU Widerruf)" → set live. Recommended: mark the email as
   transactional-style (no marketing filters) so every requester receives it.
2. When Shopify ships its **native withdrawal feature** (announced for the
   week of June 15): compare; if adequate, enable it and keep or retire this
   page (decision point — the footer link can target Shopify's native flow).
3. Have legal review the wording (button labels follow the directive's
   "withdraw from contract here/now" pattern; all copy is editable via
   section settings, incl. German wording per market).
