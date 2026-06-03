"""Tests for internal-link normalization (app/utils/links.py)."""

from __future__ import annotations

import pytest

from app.utils import links


class TestToRelativeLinks:
    def test_absolute_internal_href_becomes_relative(self):
        html = '<a href="https://velluto-shop.com/products/stradapro?variant=42#reviews">Shop</a>'
        out = links.to_relative_links(html)
        assert 'href="/products/stradapro?variant=42#reviews"' in out

    def test_www_variant_is_internal(self):
        assert links.to_relative_links("https://www.velluto-shop.com/collections/all") == "/collections/all"

    def test_bare_domain_becomes_root(self):
        assert links.to_relative_links("Visit https://velluto-shop.com now") == "Visit / now"

    def test_markdown_link_rewritten(self):
        md = "See [the glasses](https://velluto-shop.com/products/x)."
        assert links.to_relative_links(md) == "See [the glasses](/products/x)."

    def test_protocol_relative_internal(self):
        assert links.to_relative_links("//velluto-shop.com/pages/about") == "/pages/about"

    def test_external_links_untouched(self):
        ext = '<a href="https://instagram.com/velluto">IG</a>'
        assert links.to_relative_links(ext) == ext

    def test_myshopify_host_is_internal(self, monkeypatch):
        monkeypatch.setattr(links.settings, "shopify_shop_name", "velluto.myshopify.com")
        assert links.to_relative_links("https://velluto.myshopify.com/products/x") == "/products/x"

    def test_empty_input(self):
        assert links.to_relative_links("") == ""


class TestToAbsoluteLinks:
    def test_relative_href_becomes_absolute(self):
        html = '<a href="/products/stradapro">Shop</a>'
        out = links.to_absolute_links(html)
        assert 'href="https://velluto-shop.com/products/stradapro"' in out

    def test_markdown_relative_becomes_absolute(self):
        md = "Buy [now](/products/x)"
        assert links.to_absolute_links(md) == "Buy [now](https://velluto-shop.com/products/x)"

    def test_noncanonical_internal_host_canonicalized(self):
        html = '<a href="https://www.velluto-shop.com/cart">Cart</a>'
        out = links.to_absolute_links(html)
        assert 'href="https://velluto-shop.com/cart"' in out

    def test_external_links_untouched(self):
        ext = '<a href="https://instagram.com/velluto">IG</a>'
        assert links.to_absolute_links(ext) == ext


class TestNormalizeContentLinks:
    def test_recurses_nested_structure_relative(self):
        obj = {
            "answer_paragraph": "See https://velluto-shop.com/products/a",
            "faq_items": [
                {"q": "Where?", "a": 'Here: <a href="https://velluto-shop.com/pages/x">x</a>'},
            ],
            "count": 3,
            "facts": ["plain text", None],
        }
        out = links.normalize_content_links(obj, mode="relative")
        assert out["answer_paragraph"] == "See /products/a"
        assert 'href="/pages/x"' in out["faq_items"][0]["a"]
        assert out["count"] == 3
        assert out["facts"] == ["plain text", None]

    def test_absolute_mode(self):
        obj = {"html_body": '<a href="/products/x">x</a>'}
        out = links.normalize_content_links(obj, mode="absolute")
        assert out["html_body"] == '<a href="https://velluto-shop.com/products/x">x</a>'
