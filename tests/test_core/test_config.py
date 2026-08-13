from app.core.config import Settings


def test_settings_expose_public_base_url() -> None:
    settings = Settings(public_base_url="https://example.test")

    assert settings.public_base_url == "https://example.test"
