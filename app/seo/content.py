def display_city(city: str) -> str:
    return city.replace("_", " ").replace("-", " ").title()


def neighborhood_intro(
    neighborhood: str,
    city: str,
    transaction_count: int,
    median_price_per_m2: float | None,
    delta_pct: float | None,
) -> str:
    city_name = display_city(city)
    if median_price_per_m2 is None:
        price_text = "não há R$/m² suficiente para uma medição confiável"
    else:
        price_text = f"o R$/m² mediano foi de R$ {median_price_per_m2:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if delta_pct is None:
        trend_text = "Ainda não há comparação temporal suficiente"
    else:
        trend_text = f"A variação contra a janela anterior foi de {delta_pct:+.1f}%"
    return (
        f"Em {neighborhood.title()}, {city_name}, foram registradas "
        f"{transaction_count} quitações de ITBI no período analisado; {price_text}. "
        f"{trend_text}. Os valores são declarações de transações reais, não preços de anúncio."
    )


def street_intro(
    street: str,
    city: str,
    transaction_count: int,
    property_count: int,
    median_price_per_m2: float | None,
) -> str:
    price_text = (
        "não há R$/m² suficiente para calcular a mediana"
        if median_price_per_m2 is None
        else f"o R$/m² mediano foi de R$ {median_price_per_m2:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    return (
        f"A {street.title()} em {display_city(city)} reúne {property_count} endereços "
        f"com {transaction_count} quitações de ITBI no recorte analisado; {price_text}. "
        "Consulte os endereços individuais para ver a sequência de transações."
    )


def property_intro(
    street: str,
    street_number: str | None,
    complement: str | None,
    transaction_count: int,
    year_from: int | None,
    year_to: int | None,
) -> str:
    address = f"{street.title()}, {street_number or 's/n'}"
    if complement:
        address += f" — {complement}"
    period = (
        f"entre {year_from} e {year_to}"
        if year_from and year_to
        else "no período disponível"
    )
    return (
        f"O histórico de {address} reúne {transaction_count} quitações de ITBI "
        f"{period}. A página mostra valores declarados, áreas, R$/m² e alertas "
        "para cotas parciais ou áreas divergentes."
    )
