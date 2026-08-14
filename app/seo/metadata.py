from dataclasses import dataclass
from urllib.parse import urljoin


@dataclass(frozen=True)
class PageMetadata:
    title: str
    description: str
    canonical: str
    robots: str


def build_metadata(
    *,
    title: str,
    description: str,
    canonical: str,
    base_url: str,
    indexable: bool = True,
) -> PageMetadata:
    return PageMetadata(
        title=title,
        description=description,
        canonical=urljoin(base_url.rstrip("/") + "/", canonical.lstrip("/")),
        robots="index,follow" if indexable else "noindex,follow",
    )
