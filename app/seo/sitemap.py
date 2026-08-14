from datetime import date
from xml.etree.ElementTree import Element, SubElement, tostring


def sitemap_xml(urls: list[tuple[str, date | None]]) -> str:
    root = Element("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    for url, lastmod in urls:
        item = SubElement(root, "url")
        SubElement(item, "loc").text = url
        if lastmod:
            SubElement(item, "lastmod").text = lastmod.isoformat()
    return tostring(root, encoding="unicode")


def sitemap_index_xml(urls: list[str]) -> str:
    root = Element("sitemapindex", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    for url in urls:
        item = SubElement(root, "sitemap")
        SubElement(item, "loc").text = url
    return tostring(root, encoding="unicode")
