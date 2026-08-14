from urllib.parse import urljoin


def breadcrumb_json_ld(
    items: list[tuple[str, str]], base_url: str
) -> dict[str, object]:
    origin = base_url.rstrip("/") + "/"
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": urljoin(origin, path.lstrip("/")),
            }
            for position, (name, path) in enumerate(items, start=1)
        ],
    }


def webpage_json_ld(name: str, description: str, url: str) -> dict[str, str]:
    return {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": name,
        "description": description,
        "url": url,
    }
