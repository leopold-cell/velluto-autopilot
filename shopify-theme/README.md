# Velluto — Strada Pro Bundle Page (TEST)

Test implementation of the Strada Pro bundle landing page and bundle product
page concept for **velluto-shop.com** (theme: **Stretch v1.4.1**).
**This is not live and must not be published without review.** All files are
designed to be deployed to an **unpublished copy** of the live theme and
previewed there first.

## Store facts these files are built against

Verified against the live storefront (2026-06-10):

- Each StradaPro frame color is **its own product** (no color variants):
  `velluto-stradapro-cycling-glasses-nero` / `-arancia` / `-espresso` /
  `-viola`, €149 each. The existing color switcher is the
  `velluto_color_swatches` custom liquid block in the product-info section —
  plain links between sibling products, styled by `assets/velluto-product.css`
  (`vcol-*` classes).
- Accessories: VellutoVisione™ High Contrast Lens €39, VellutoPuro
  Transparent Lens €19, Hard Case €19, Microfiber Cloth €8, Cleaning Spray
  €8, TACX Bidon €14.
- Live theme: `197496209749` ("Velluto Update 2026 with collection images").

The bundle products follow the same one-product-per-color structure:
3 sets × 4 colors = 12 products (created as **drafts** for testing), e.g.
`strada-pro-starter-set-nero` … `strada-pro-ultimate-set-viola`, connected
via metafields (see below) instead of hardcoded handles.

## What's in here

| File | Purpose |
| --- | --- |
| `sections/velluto-bundle-landing.liquid` | The bundle selector landing page: hero, three bundle cards ("Most Popular" badge, per-card color switcher across the four color products, free-shipping indicator, CTA), trust row, and auto-generated comparison table. |
| `sections/velluto-bundle-included-items.liquid` | Companion section for the bundle product pages: included-items list + free-shipping message (only shown at/above the threshold). |
| `snippets/velluto-bundle-color-swatches.liquid` | Color switcher for the bundle product pages. Mirrors the existing `velluto_color_swatches` block (same `vcol-*` classes and `velluto-product.css`), but driven by metafields instead of hardcoded HTML. |
| `templates/page.velluto-bundles-test.json` | Page template pre-wired with the Starter / Performance / Ultimate cards and the per-color product handles. |
| `templates/product.velluto-bundle.json` | Placeholder — regenerate from the theme copy's real `templates/product.json` at deploy time (see below) so the existing gallery, accordion blocks and trust badges carry over 1:1. |
| `preview/bundle-page-preview.html` | Static design preview with placeholder imagery — open directly in any browser, no Shopify required. |

## Bundle metafields (namespace `velluto`)

| Key | Type | Used for |
| --- | --- | --- |
| `included_items` | multi-line text, one item per line | Card lists, product page list, comparison table (theme-editor textarea as fallback). |
| `color_label` | single line text, e.g. `Nero` | Swatch labels (falls back to the `… \| Color` title suffix). |
| `color_siblings` | single line text, comma-separated handles of all color versions of the set, in display order | The product-page color switcher. |

## Design decisions (mapped to the brief)

- **Three cards side by side on desktop, stacked on mobile** with the
  Performance Set first on mobile (CSS `order`) and centered/elevated on
  desktop, carrying the "Most Popular" badge and the filled primary CTA.
- **Premium, not discount-heavy:** compare-at prices render as
  "€X individual value", never as slashed sale prices. No urgency or sale
  language. Ivory/charcoal palette with one Italian-red accent.
- **Free shipping from €99** is a single section setting
  (`free_shipping_threshold`); eligibility per bundle is computed from the
  live product price — Starter (€69) shows "Free shipping from €99",
  Performance and Ultimate show "Free shipping included". The comparison
  table's Free Shipping row uses the same logic. (The section only
  *communicates* the threshold — the actual free-shipping rate lives in
  Settings → Shipping.)
- **No hardcoded product IDs:** cards use theme-editor product pickers
  (stored as handles); product-page swatches use the `color_siblings`
  metafield.
- **CTA links to the bundle's product page** (the selected color's product),
  matching the existing sibling-product switcher logic — no add-to-cart
  variant complexity.
- **Comparison table** (Strada Pro → Bottle + Free Shipping) is generated
  from the union of the bundles' item lists, so it can never drift out of
  sync with the cards.

## Deploy to the theme copy

Deployment uses the Admin API Asset endpoint, same mechanism as
`scripts/deploy_theme.py` in the `velluto-seo-bot` repo (PUT
`/admin/api/2024-10/themes/{theme_id}/assets.json`, token with
`write_themes`).

1. Upload `sections/*.liquid` and `snippets/*.liquid` as-is.
2. **Product template:** GET the theme copy's `templates/product.json`,
   then create `templates/product.velluto-bundle.json` from it by
   - adding a Custom Liquid block to the product-info section containing
     `{% render 'velluto-bundle-color-swatches', product: product %}`
     (replaces the hardcoded StradaPro swatch block for bundle products),
   - appending the `velluto-bundle-included-items` section below the main
     section.
   This keeps the existing gallery, accordions, reviews and trust badges 1:1.
3. Upload `templates/page.velluto-bundles-test.json`.
4. Create the 12 draft bundle products (4 colors × 3 sets) with prices
   €69 / €99 / €119, compare-at prices from the individual item values
   (Starter €188, Performance €226, Ultimate €256 at current accessory
   prices), the metafields above, the matching StradaPro color imagery, and
   `template_suffix: velluto-bundle`.
5. Create a page (e.g. "Choose your Strada Pro") with template suffix
   `velluto-bundles-test`, kept out of navigation.
6. Preview via the unpublished theme copy's Preview link. **Do not publish.**

## Going live (later, after review)

- Publish the tested copy, or copy the files + template assignments to the
  live theme.
- Switch the 12 bundle products from draft to active.
- Confirm an actual free-shipping rate ≥ €99 exists in Settings → Shipping.
