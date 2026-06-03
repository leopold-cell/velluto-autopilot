# Link Audit — internal links must be relative

**Goal:** every **internal** link in the storefront points to a **root-relative**
path (`/products/handle`), never an absolute URL with a domain
(`https://velluto-shop.com/products/handle`). External links (Instagram, payment
providers, etc.) stay absolute.

> **Why:** absolute internal links break across environments (preview themes,
> staging, domain changes), can leak a non-canonical host, and add needless
> redirects. Relative links always resolve against the current host.

The backend (`velluto-autopilot`) now enforces this automatically for generated
content — see [Backend guardrails](#backend-guardrails). The **theme** is not in
this repo, so the storefront part is done in Shopify. This guide covers that.

---

## 1. Fix the PDP color switcher

The colour/variant thumbnails on the product page currently link to absolute
URLs. In the variant-picker (usually `snippets/product-variant-picker.liquid`,
`sections/main-product.liquid`, or the theme's media/JS), build variant links
from Shopify's **relative** URL objects:

```liquid
{%- comment -%} ✅ relative — product.url is already root-relative {%- endcomment -%}
<a href="{{ product.url }}?variant={{ variant.id }}">{{ variant.title }}</a>
```

```liquid
{%- comment -%} ❌ avoid — hardcoded / absolute {%- endcomment -%}
<a href="https://velluto-shop.com/products/{{ product.handle }}?variant={{ variant.id }}">
<a href="{{ shop.url }}{{ product.url }}?variant={{ variant.id }}">
```

If the switch happens in JavaScript, construct **root-relative** paths
(`/products/${handle}?variant=${id}`) or use the History API with a relative
path — never prefix `window.location.origin` or a hardcoded domain.

## 2. Liquid best practice

These objects already return root-relative paths — use them instead of building
URLs by hand:

- `{{ product.url }}`, `{{ collection.url }}`, `{{ article.url }}`, `{{ page.url }}`
- `{{ routes.* }}` (e.g. `routes.cart_url`, `routes.search_url`, `routes.root_url`)

Avoid for internal links: `{{ shop.url }}`, `{{ shop.secure_url }}`,
`{{ canonical_url }}`, `{{ request.origin }}`, and any hardcoded
`https://velluto-shop.com`.

## 3. Storefront audit checklist

Pull the live theme and grep for absolute/internal patterns:

```bash
shopify theme pull --theme <THEME_ID>
grep -rniE 'https?://(www\.)?velluto-shop\.com|shop\.url|shop\.secure_url|canonical_url|request\.origin|//velluto-shop\.com' .
```

Review each hit:

- [ ] PDP variant/colour switcher → relative
- [ ] Header/footer navigation & logo link → relative (`routes.root_url`)
- [ ] Cart / checkout buttons → `routes.cart_url` (checkout stays Shopify-managed)
- [ ] Collection cards, "view all", breadcrumbs → `*.url`
- [ ] Blog/article and page links → `article.url` / `page.url`
- [ ] Promo banners / rich-text / metafield links pasted by hand → relative
- [ ] Hardcoded domains in custom Liquid blocks or theme settings → relative
- [ ] **Leave external links absolute** (social, reviews app, payment, tracking)

## 4. Apply safely

1. **Duplicate** the theme (Online Store → Themes → ⋯ → Duplicate).
2. Apply fixes in the duplicate.
3. **Preview** the PDP → click a colour thumbnail → the URL must be
   `/products/...?variant=...` (no domain prefix), variant still switches.
4. Spot-check nav, cart, a collection and a blog post.
5. **Publish**. Theme version history is your rollback.

---

## Backend guardrails

Generated content from this repo is normalized automatically via
[`app/utils/links.py`](../app/utils/links.py):

| Channel | Rule | Where |
| --- | --- | --- |
| SEO product copy, GEO content (on-site) | internal links → **root-relative** | `app/modules/seo/tools.py` |
| Email flows | internal links → **absolute** on the canonical domain (relative links don't work in email) | `app/modules/email_marketing/flows.py` |
| Meta ad copy | **no** raw links in copy (destination set on the ad object) | `app/modules/creative/tools.py` |

The canonical storefront domain is configured once via
`settings.storefront_domain` (`app/config.py`, default `velluto-shop.com`) and
is used to decide which hosts are "internal".

### Follow-up: `velluto-seo-bot`
The `velluto-seo-bot` repo generates on-site SEO/blog content and likely emits
internal links too. It must get the same treatment in a session scoped to that
repo: reuse the `to_relative_links` / `normalize_content_links` pattern and add
the "internal links root-relative" instruction to its generation prompts.
