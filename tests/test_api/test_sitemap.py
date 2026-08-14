from datetime import date

from app.seo.sitemap import sitemap_index_xml, sitemap_xml


def test_sitemap_xml_contains_lastmod_and_escaped_urls() -> None:
    xml = sitemap_xml(
        [("https://example.test/bairro/savassi/", date(2025, 1, 2))]
    )

    assert "<urlset" in xml
    assert "https://example.test/bairro/savassi/" in xml
    assert "2025-01-02" in xml


def test_sitemap_index_uses_sitemap_elements() -> None:
    xml = sitemap_index_xml(["https://example.test/sitemap-bairros.xml"])

    assert "<sitemapindex" in xml
    assert "<sitemap>" in xml
    assert "</sitemapindex>" in xml
