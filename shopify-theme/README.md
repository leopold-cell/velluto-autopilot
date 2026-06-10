# Velluto — Strada Pro Bundle Page (TEST)

Test implementation of the Strada Pro bundle landing page and bundle product
page concept. **This is not live and must not be published without review.**
All files are Online Store 2.0 theme files designed to be copied into an
**unpublished duplicate** of the live theme and previewed there first.

## What's in here

| File | Purpose |
| --- | --- |
| `sections/velluto-bundle-landing.liquid` | The bundle selector landing page: hero, three bundle cards (with "Most Popular" badge, per-card color switcher, free-shipping indicator, CTA), trust row, and auto-generated comparison table. |
| `sections/velluto-bundle-included-items.liquid` | Companion section for the bundle product pages: included-items list + free-shipping message (only shown at/above the threshold). |
| `templates/page.velluto-bundles-test.json` | Page template that pre-wires the landing section with the Starter / Performance / Ultimate copy. |
| `templates/product.velluto-bundle.json` | Alternate product template for the three bundle products: the theme's existing main product section (gallery, color switcher, price, CTA, trust badges stay untouched) + the included-items section below it. |
| `preview/bundle-page-preview.html` | Static design preview with placeholder imagery — open directly in any browser, no Shopify required. |

## Design decisions (mapped to the brief)

- **Three cards side by side on desktop, stacked on mobile** with the
  Performance Set first on mobile (CSS `order`) and centered/elevated on
  desktop. Performance Set carries the "Most Popular" badge, a stronger
  border/shadow and the filled primary CTA.
- **Premium, not discount-heavy:** compare-at prices are presented as
  "€X individual value", never as slashed sale prices. No countdown timers,
  no "SALE" language. Ivory/charcoal palette with a single Italian-red accent.
- **Free shipping from €99** is a single section setting
  (`free_shipping_threshold`, default 99) — eligibility per bundle is
  computed from the live product price, so Starter (€69) shows
  "Free shipping from €99" while Performance and Ultimate show
  "Free shipping included". The comparison table's Free Shipping row uses the
  same logic.
- **No hardcoded product IDs.** Bundle cards use theme-editor product pickers
  (stored as handles). The page template pre-fills the handles
  `strada-pro-starter-set`, `strada-pro-performance-set`,
  `strada-pro-ultimate-set` — adjust to the real handles or re-pick in the
  editor.
- **Included items** come from the product metafield
  `velluto.included_items` (multi-line text, one item per line) with a
  theme-editor textarea as fallback. The comparison table is generated from
  the union of all bundles' lists, so it can never drift out of sync with
  the cards.
- **CTA links to the bundle's product page** (with the selected color
  pre-applied via `?variant=`), per the brief's guidance that direct
  add-to-cart is riskier with 4 color variants.
- **Color switcher:** the bundle product pages reuse the theme's existing
  main product section, so the existing Strada Pro color switcher works
  unchanged — provided each bundle product is created with the same color
  option / 4 color variants as the Strada Pro. The landing cards add a small
  swatch picker (progressive enhancement; falls back to plain links without
  JS) that swaps the card image and deep-links the chosen variant.

## Setup on the store (test, not live)

1. **Duplicate the live theme** (Online Store → Themes → … → Duplicate) and
   rename it e.g. `[TEST] Bundles`. Do everything below on the duplicate.
2. **Copy the files** into the duplicate (code editor, Shopify CLI
   `shopify theme push --unpublished`, or the GitHub integration):
   - both `sections/*.liquid` files into `sections/`
   - both `templates/*.json` files into `templates/`
3. **Create the three bundle products** (Starter Set €69, Performance Set
   €99, Ultimate Set €119), each with the **same color option and 4 color
   values as the Strada Pro** (one variant per color, with a variant image
   per color). Optionally set a compare-at price equal to the sum of the
   individual items to power the "individual value" line, and fill the
   `velluto.included_items` metafield (multi-line text definition on
   products, namespace `velluto`, key `included_items`).
4. **Assign templates** (on the test theme): set the three bundle products
   to the `Velluto Bundle (TEST)` product template; create a new page
   (e.g. "Choose your Strada Pro") with the `Velluto Bundles (TEST)` page
   template. Keep the page out of navigation.
5. **Preview** via the duplicate theme's Preview button. Check mobile
   (Performance Set should stack first) and desktop (three cards side by
   side). Verify swatches swap images and that CTAs land on the right
   bundle product page with the color preselected.

> **Note on `templates/product.velluto-bundle.json`:** it references the main
> product section as `main-product` (Dawn-family convention). If the live
> theme's product template uses a different section name, copy the live
> theme's `templates/product.json`, rename it to
> `product.velluto-bundle.json`, and just append the
> `velluto-bundle-included-items` section to it — that guarantees the
> existing gallery, color switcher and trust badges carry over 1:1.

## Going live (later, after review)

- Publish path A: keep the tested duplicate and publish it.
- Publish path B: copy the two sections + two templates into the live theme
  and assign the templates there.
- Make sure the actual shipping settings (free shipping rate ≥ €99) match
  the `free_shipping_threshold` section setting — the section only
  *communicates* the threshold, it does not configure shipping.
