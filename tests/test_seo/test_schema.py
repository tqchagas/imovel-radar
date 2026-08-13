from app.seo.schema import breadcrumb_json_ld


def test_breadcrumb_schema_uses_absolute_item_urls() -> None:
    data = breadcrumb_json_ld(
        [("Início", "/"), ("Bairros", "/bairro"), ("Savassi", "/bairro/bh/savassi/")],
        "https://radar.example",
    )

    assert data["@type"] == "BreadcrumbList"
    assert data["itemListElement"][-1]["item"] == "https://radar.example/bairro/bh/savassi/"
