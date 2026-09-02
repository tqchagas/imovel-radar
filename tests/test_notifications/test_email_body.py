"""O corpo do alerta diz quem avaliou o imóvel, não só quanto."""

from app.models.market_comparable import MarketComparable
from app.notifications.email import render_opportunity_email


def _row(**overrides) -> MarketComparable:
    defaults = dict(
        source="loft", listing_id="lo-1", cidade="Belo Horizonte", bairro="Buritis",
        rua="Rua Sao Joao", numero="10", tipo_imovel="APARTAMENTO", area_util_m2=90.0,
        preco_total=500000.0, preco_estimado=700000.0, desconto_pct=0.2857,
        desconto_reais=200000.0, confianca="alta", tipo_referencia="rua", amostra_count=42,
    )
    defaults.update(overrides)
    return MarketComparable(**defaults)


def test_a_qpreco_alert_says_quintoandar_valued_the_unit():
    message = render_opportunity_email(_row(referencia_primaria="qpreco"), ["a@b.com"])

    assert "QuintoAndar avaliou esta unidade" in message.body
    assert "R$ 700.000,00" in message.body


def test_a_borrowed_alert_says_the_valuation_came_from_neighbours():
    message = render_opportunity_email(_row(referencia_primaria="qpreco_vizinho"), ["a@b.com"])

    assert "vizinhos da mesma rua" in message.body


def test_an_itbi_alert_still_names_the_itbi():
    message = render_opportunity_email(_row(referencia_primaria="itbi"), ["a@b.com"])

    assert "ITBI" in message.body


def test_the_itbi_check_is_shown_next_to_a_qpreco_valuation():
    message = render_opportunity_email(
        _row(referencia_primaria="qpreco", preco_estimado_itbi=900000.0,
             desconto_itbi_pct=0.444),
        ["a@b.com"],
    )

    # Quem lê precisa poder ver se as duas réguas concordam.
    assert "Conferência por ITBI" in message.body
    assert "R$ 900.000,00" in message.body


def test_the_confidence_block_is_labelled_as_the_check_when_qpreco_answered():
    message = render_opportunity_email(
        _row(referencia_primaria="qpreco", preco_estimado_itbi=900000.0,
             desconto_itbi_pct=0.444, confianca="baixa", tipo_referencia="bairro_amplo",
             amostra_count=1228),
        ["a@b.com"],
    )

    # "Confiança: baixa" em destaque, quando quem avaliou foi o QuintoAndar,
    # descreve a conferência e não a resposta — e lê como se o alerta fosse
    # fraco quando ele é o mais forte que temos.
    linha = next(l for l in message.body.split("\n") if "bairro amplo" in l)
    assert "Conferência" in linha or "conferência" in linha
    assert "Confiança: Baixa" not in message.body
