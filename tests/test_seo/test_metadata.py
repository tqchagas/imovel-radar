from app.seo.metadata import build_metadata


def test_metadata_builds_canonical_and_noindex_directive() -> None:
    metadata = build_metadata(
        title="Preço na Savassi",
        description="Dados reais de transações.",
        canonical="/bairro/belo-horizonte/savassi/",
        base_url="https://radar.example",
        indexable=False,
    )

    assert metadata.canonical == "https://radar.example/bairro/belo-horizonte/savassi/"
    assert metadata.robots == "noindex,follow"
    assert metadata.title == "Preço na Savassi"
