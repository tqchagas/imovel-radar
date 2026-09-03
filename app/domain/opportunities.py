"""Pure calculation of listing opportunities against recent ITBI transactions.

ITBI declared values are not asking prices: across Belo Horizonte a listing
asks a median 1.74x the declared R$/m2 of a sale in the same neighborhood, and
the gap itself moves with unit size (2.55x under 60 m2, 1.27x over 250 m2).
Comparing a listing straight against an ITBI median therefore reports every
listing as overpriced and flags large apartments as bargains. So the ITBI
median only sets the *shape* of the reference - it resolves price differences
street by street, which the sparse listing sample cannot - and a calibration
factor measured per neighborhood and size band converts it into the asking
price a comparable unit is expected to carry.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from statistics import median, quantiles
from typing import Iterable, Mapping, Sequence

from app.domain.market_stats import Sale, shift_months
from app.domain.slugs import address_key, street_key
from app.market_collectors.normalize import normalize_type

WINDOW_MONTHS = 24
AREA_TOLERANCE = 0.30

# The ITBI area and the advertised area do not measure the same thing. "Área
# Construída Adquirida" is the unit's built area times the acquired share; a
# portal advertises usable area. Matched at the exact same address across 551
# Belo Horizonte pairs, the cartório records a median 1.62x the advertised
# number (p25 1.24, p75 1.97), so a window centred on the raw advertised area
# misses the very rows that describe the same apartment - it was finding 120
# exact-address references where the converted window finds 405.
#
# It converts only for *matching*: the estimate keeps multiplying the area the
# listing publishes, and the calibration factor is measured on that same area,
# so the price level is untouched. Remeasure per city with
# `scripts/medir_area_itbi.py`.
AREA_MATCH_FACTOR = 1.6

# Sample floors per reference tier, calibrated by holding out 20% of Belo
# Horizonte's residential apartment ITBI (8.148 rows) and predicting it from the
# rest. Median absolute error of the R$/m2 by tier: exact address 8.3%, street
# 18.4%, neighborhood+area 20.2%, broad neighborhood 22.8% - the ladder's order
# is right, and the address tier is worth reaching for.
#
# The floors are set where global error is lowest, not where each tier looks
# best on its own: raising the address floor to 10 makes that tier read 6.7%
# while global error climbs to 15.0%, because everything it rejects lands on a
# worse tier. Two sales at one address beat the street that would replace them.
#   address floor  2 -> global 12.6%  |  3 -> 13.0%  |  5 -> 13.9%  |  10 -> 15.0%
#   street floor   5 -> global 13.0% with 2.106 references, against 672 at 15
# Remeasure with `scripts/validar_referencia.py` when a new city arrives.
EXACT_MIN_SAMPLE = 2
STREET_MIN_SAMPLE = 5
BAIRRO_AREA_MIN_SAMPLE = 15
BAIRRO_AMPLO_MIN_SAMPLE = 1

# O piso de desconto e relativo ao erro medido da referencia que respondeu, e
# nao um numero fixo. Validacao cruzada: prever o preco pedido de um anuncio
# escondido erra 22,2% na mediana pela escada de ITBI, contra os ~5% da faixa
# que o proprio QuintoAndar publica no qpreco. Um desconto de 12% nao significa
# a mesma coisa nas duas — contra o ITBI e ruido, contra o qpreco e sinal.
#
# 1,5x reproduz o antigo piso fixo de 30% no tier de rua (erro 0,20) e libera
# 7,5% contra um qpreco de faixa estreita.
MIN_DISCOUNT_MULTIPLE = 1.5
# Chao absoluto, so para nada abaixo disso passar por acidente.
MIN_DISCOUNT_PCT = 0.05
# The score subsumes what the tier was proxying, so the tier no longer gates.
MIN_CONFIDENCE = "baixa"
# "Only show me above 80": strong discount against a sample that agrees with
# itself and is deep enough to trust.
MIN_SCORE = 80

# Score. A discount only means something next to how wrong its reference tends
# to be, so it is divided by the reference's *measured* error rather than by a
# proxy. `scripts/validar_referencia.py` predicts 8.143 held-out ITBI rows and
# reports the median error of each (tier, dispersion) cell:
#
#                    dispersão <15%   15-30%    >30%
#   endereço exato            4,8%     9,5%    12,8%
#   rua                      14,3%    15,2%    20,2%
#   bairro + área            19,3%*   19,3%    21,6%
#   bairro amplo             24,8%*   24,8%*   24,8%     (* célula rasa: usa o tier)
#
# Two things this replaces. The tier used to be absent from the score, on the
# theory that dispersion subsumed it - it does not: at equal dispersion the
# exact address still errs 9,5% against the neighborhood's 19,3%. And the old
# sample-depth bonus rewarded the wrong thing: holding dispersion fixed, error
# *rises* with sample size (13,4% -> 21,2% in the loosest band), because a deep
# sample is a wide scope, not better evidence.
EXPECTED_ERROR = {
    # O qpreco avalia a unidade e publica a propria incerteza; a escada de ITBI
    # ve rua e metragem. Por isso ele responde primeiro onde existe.
    "qpreco": (0.05, 0.10, 0.13),
    # Mediana do qpreco de unidades semelhantes na mesma rua, para o anuncio que
    # nao tem um proprio — Loft e VivaReal nunca terao, porque o endpoint
    # resolve por id do QuintoAndar. Medido escondendo o qpreco do proprio
    # anuncio e prevendo pelos vizinhos, em 974 anuncios: 3,5% de erro quando os
    # vizinhos concordam, 9,2% na faixa do meio, 13,2% quando discordam.
    "qpreco_vizinho": (0.04, 0.09, 0.13),
    "endereco_exato": (0.05, 0.10, 0.13),
    # Endereço que veio da coordenada, e não do anúncio. O cadastro imobiliário
    # da prefeitura resolve o prédio certo em 93,5% dos casos (medido contra os
    # 1.530 anúncios do VivaReal que publicam número e ponto exato); nos outros
    # 6,5% cai num vizinho da mesma rua. O erro é a mistura dos dois pesada por
    # essa taxa, tratando o vizinho errado como se valesse o tier de rua —
    # conservador, porque um prédio vizinho concreto tende a errar menos do que
    # a mediana de uma rua inteira.
    "endereco_geo": (0.06, 0.10, 0.14),
    "rua": (0.14, 0.15, 0.20),
    "bairro_area": (0.19, 0.19, 0.22),
    "bairro_amplo": (0.25, 0.25, 0.25),
}
DISPERSION_BANDS = (0.15, 0.30)
# Full strength at a discount four times the reference's typical error - 20% off
# a tight exact-address sample, 60% off a street one. Calibrated on the Belo
# Horizonte base to hold the alert volume where it was (71 listings against 73),
# so the change re-allocates which listings are flagged, toward the references
# that earn it, rather than opening or closing the gate. Sweeping it: 3.0 lets
# 398 through, 3.5 lets 143, 5.0 lets 4.
SCORE_FULL_SIGNAL = 4.0
# Below this share of the expected price a listing stops reading as a bargain
# and starts reading as bad data - a wrong area, a garage, a mislabelled unit.
SCORE_IMPLAUSIBLE = 0.20
SCORE_PLAUSIBLE = 0.45
# Guards the division when a sample is unanimous.
MIN_DISPERSION = 0.10
# Under four rows there are no quartiles to measure. Assuming the sample is
# tight would hand the thinnest references the best possible score, so they get
# a typical neighborhood spread instead and have to earn the score elsewhere.
SMALL_SAMPLE_DISPERSION = 0.35

# QuintoAndar's own estimate ("qpreço") is a second, independent reference. It
# is scored by the same rule as the ITBI one: the suggested price replaces the
# calibrated ITBI estimate, and the width of the suggested range plays the part
# of the sample's dispersion. QuintoAndar publishes no sample size behind it,
# so the depth term is left full rather than penalising the listing for a
# number the portal simply does not expose.
# O qpreço é uma estimativa por unidade, com a incerteza que o próprio portal
# publica na faixa — o análogo do tier mais estreito que temos.
QPRECO_REFERENCE_TIER = "qpreco"

# Size bands used by the calibration factor, in m2.
AREA_BANDS = (60, 90, 130, 180, 250)
# Origem de área que não sustenta alerta nem entra na calibração.
AREA_ORIGEM_INCERTA = "descricao"
# Número resolvido pela coordenada contra o cadastro imobiliário, não publicado
# pelo anúncio.
NUMERO_ORIGEM_CADASTRO = "cadastro"

# A janela de área existe para não comparar um quarto-e-sala com uma cobertura.
# Dentro de um prédio ela quase não tem o que separar: medida no cadastro
# imobiliário, a dispersão das áreas das unidades de um mesmo endereço tem
# mediana 0,09, e 76% dos prédios ficam abaixo de 0,30 — mais estreitos do que
# a tolerância que a janela aplicaria. Pior, a janela é centrada na área
# anunciada vezes um fator único da cidade, e esse fator vai de 0,80 a 2,21
# entre prédios, então ela recusa vendas do próprio prédio por estar centrada
# no lugar errado: dos 5.379 anúncios da Loft cujo prédio o ITBI enxerga, só
# 1.966 sobreviviam a ela.
#
# Onde o prédio é mais homogêneo do que a própria tolerância, a janela sai.
HOMOGENEOUS_BUILDING_DISPERSION = 0.30
MIN_CALIBRATION_LISTINGS = 15
# Minimum ITBI rows behind a listing's own reference for that listing to inform
# the factor. Matches the street/neighborhood tier floor; the exact-address
# tier is exempt because it is the tightest scope there is.
MIN_CALIBRATION_SALES = 15

RESIDENTIAL_OCCUPATION = "RESIDENCIAL"
TYPE_TO_CONSTRUCTION = {"APARTAMENTO": "AP", "CASA": "CA"}
REFERENCE_CONFIDENCE = {
    "endereco_exato": "alta",
    # "média" e não "alta": o erro esperado põe este tier junto do endereço
    # exato, que é onde ele pertence para efeito de nota, mas o rótulo responde
    # outra pergunta — "é mesmo este prédio?" — e ali a resposta é 93,5%, não
    # uma certeza.
    "endereco_geo": "media",
    "rua": "media",
    "bairro_area": "baixa",
    "bairro_amplo": "baixa",
}
CONFIDENCE_ORDER = {"baixa": 0, "media": 1, "alta": 2}
REFERENCE_LABEL = {
    "endereco_exato": "endereço exato",
    "endereco_geo": "endereço, pela coordenada",
    "rua": "rua",
    "bairro_area": "bairro e faixa de área",
    "bairro_amplo": "bairro amplo",
}


def itbi_construction_type(tipo_imovel: str | None) -> str | None:
    """Map a listing type to the ITBI residential construction code."""
    return TYPE_TO_CONSTRUCTION.get(normalize_type(tipo_imovel) or "")


def area_band(area: float | None) -> int | None:
    """Index of the size band an area falls into, or None when unknown."""
    return None if area is None or area <= 0 else bisect_right(AREA_BANDS, area)


@dataclass(frozen=True)
class PriceSuggestion:
    """QuintoAndar's estimate for a listing, with the range it publishes."""

    preco_sugerido: float
    limite_inferior: float | None = None
    limite_superior: float | None = None


@dataclass(frozen=True)
class NeighbourEstimate:
    """Mediana do qpreco por m2 de unidades semelhantes na mesma rua."""

    preco_m2: float
    dispersao: float
    amostra: int


@dataclass(frozen=True)
class ListingInput:
    source: str
    listing_id: str
    tipo_imovel: str | None
    area_util_m2: float | None
    preco_total: float | None
    bairro: str | None = None
    rua: str | None = None
    numero: str | None = None
    qpreco: PriceSuggestion | None = None
    qpreco_vizinhos: NeighbourEstimate | None = None
    # "cadastro" quando o número não veio do anúncio e sim do lote mais próximo
    # da coordenada. Só muda o tier que a referência declara, nunca a busca.
    numero_origem: str | None = None
    # Dispersão das áreas das unidades do prédio, do cadastro imobiliário.
    # None quando o prédio é desconhecido ou pequeno demais para ter quartil.
    predio_dispersao_area: float | None = None
    # "descricao" quando a área foi lida do texto livre do anúncio em vez de
    # publicada pelo portal. Ela erra ~13% das vezes, e para baixo, o que faz o
    # anúncio parecer barato — então serve para exibir, nunca para alertar nem
    # para calibrar.
    area_origem: str | None = None


@dataclass(frozen=True)
class Reference:
    tipo_referencia: str
    confianca: str
    amostra_count: int
    preco_m2_mediano: float
    dispersao_relativa: float
    referencia_data_inicio: date
    referencia_data_fim: date
    area_minima: float | None
    area_maxima: float | None


@dataclass(frozen=True)
class Opportunity:
    source: str
    listing_id: str
    preco_anunciado: float
    preco_estimado: float
    desconto_pct: float
    desconto_reais: float
    tipo_referencia: str
    confianca: str
    amostra_count: int
    referencia_data_inicio: date
    referencia_data_fim: date
    preco_m2_mediano: float
    motivos: tuple[str, ...]
    fingerprint: str
    fator_calibracao: float = 1.0
    unidade_fingerprint: str | None = None
    dispersao_relativa: float = 0.0
    area_origem: str | None = None
    # Qual referencia respondeu "quanto vale": o qpreco quando ele existe, a
    # escada de ITBI quando nao.
    referencia_primaria: str = "itbi"
    preco_estimado_itbi: float = 0.0
    desconto_itbi_pct: float = 0.0
    # Dispersao da referencia que respondeu, que e o que calibra o piso.
    dispersao_primaria: float = 0.0
    nota: int = 0
    nota_itbi: int = 0
    nota_qpreco: int | None = None
    qpreco_estimado: float | None = None
    qpreco_desconto_pct: float | None = None


def _positive(value: float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if number > 0 else None


def is_valid_sale(sale: Sale) -> bool:
    """Residential ITBI row with a usable declared value and built area."""
    return (
        (sale.occupation_type or "").strip().upper() == RESIDENTIAL_OCCUPATION
        and _positive(sale.declared_value) is not None
        and _positive(sale.built_area_acquired) is not None
    )


def sale_price_per_m2(sale: Sale) -> float:
    return float(sale.declared_value) / float(sale.built_area_acquired)


def reference_date_for(sales: Iterable[Sale]) -> date | None:
    """Latest settlement date among valid residential ITBI rows."""
    dates = [sale.settlement_date for sale in sales if is_valid_sale(sale)]
    return max(dates) if dates else None


def window_bounds(reference: date) -> tuple[date, date]:
    """Inclusive 24-month window ending on the reference date."""
    return shift_months(reference, WINDOW_MONTHS), reference


@dataclass(frozen=True)
class SaleIndex:
    """ITBI sales grouped by the scopes the reference ladder walks.

    Scanning every sale for every listing is O(listings x sales); on Belo
    Horizonte that is 6.5k x 48k comparisons per run. The ladder only ever
    asks for three scopes, so they are grouped once up front.
    """

    by_neighborhood: Mapping[tuple[str, str], list[Sale]] = field(default_factory=dict)
    by_street: Mapping[tuple[str, str, str], list[Sale]] = field(default_factory=dict)
    by_address: Mapping[tuple[str, str, str, str], list[Sale]] = field(default_factory=dict)
    reference_date: date | None = None

    @classmethod
    def build(cls, sales: Iterable[Sale], reference_date: date | None = None) -> "SaleIndex":
        sales = list(sales)
        reference_day = reference_date or reference_date_for(sales)
        if reference_day is None:
            return cls(reference_date=None)
        start, end = window_bounds(reference_day)

        by_neighborhood: dict[tuple[str, str], list[Sale]] = {}
        by_street: dict[tuple[str, str, str], list[Sale]] = {}
        by_address: dict[tuple[str, str, str, str], list[Sale]] = {}
        for sale in sales:
            if not is_valid_sale(sale) or not start <= sale.settlement_date <= end:
                continue
            construction = (sale.construction_type or "").strip().upper()
            bairro = address_key(sale.neighborhood)
            if not construction or bairro is None:
                continue
            by_neighborhood.setdefault((construction, bairro), []).append(sale)
            rua = street_key(sale.street)
            if rua is None:
                continue
            by_street.setdefault((construction, bairro, rua), []).append(sale)
            numero = address_key(sale.street_number)
            if numero is not None:
                by_address.setdefault((construction, bairro, rua, numero), []).append(sale)
        return cls(by_neighborhood, by_street, by_address, reference_day)


def _as_index(sales: Sequence[Sale] | SaleIndex, reference_date: date | None) -> SaleIndex:
    return sales if isinstance(sales, SaleIndex) else SaleIndex.build(sales, reference_date)


@dataclass(frozen=True)
class Calibration:
    """Asking-price-to-ITBI ratio, measured where there is enough of both."""

    by_band: Mapping[tuple[str, str, int], float] = field(default_factory=dict)
    by_city_band: Mapping[tuple[str, int], float] = field(default_factory=dict)
    by_neighborhood: Mapping[tuple[str, str], float] = field(default_factory=dict)
    by_construction: Mapping[str, float] = field(default_factory=dict)
    flat_factor: float | None = None

    @classmethod
    def flat(cls, value: float) -> "Calibration":
        """One factor everywhere. `flat(1.0)` compares straight against the raw
        ITBI median, which is only meaningful in tests."""
        return cls(flat_factor=value)

    def factor(self, construction: str, bairro: str | None, area: float | None) -> float | None:
        """Most specific factor available, or None when nothing was measured.

        Returning None keeps a listing out of the results entirely: an
        uncalibrated estimate is the bug this whole module exists to avoid, so
        it must never silently fall back to 1.0.
        """
        if self.flat_factor is not None:
            return self.flat_factor
        band = area_band(area)
        if bairro is not None and band is not None:
            found = self.by_band.get((construction, bairro, band))
            if found is not None:
                return found
        # Size distorts the ratio far more than location does (3.2x for a small
        # flat against 1.5x for a large one in the same neighborhood), so a
        # city-wide factor for the right size band beats a neighborhood factor
        # that averages every size together.
        if band is not None:
            found = self.by_city_band.get((construction, band))
            if found is not None:
                return found
        if bairro is not None:
            found = self.by_neighborhood.get((construction, bairro))
            if found is not None:
                return found
        return self.by_construction.get(construction)


def _median_of(values: list[float], minimum: int) -> float | None:
    return median(values) if len(values) >= minimum else None


def build_calibration(
    listings: Iterable[ListingInput],
    index: SaleIndex,
    *,
    min_listings: int = MIN_CALIBRATION_LISTINGS,
    min_sales: int = MIN_CALIBRATION_SALES,
) -> Calibration:
    """Measure how far asking prices sit above the ITBI each listing is judged by.

    The ratio is taken against the listing's *own* reference, not against the
    neighborhood median. Streets dense enough to earn a narrow reference tend
    to be main avenues carrying pricier stock, so a factor calibrated on the
    neighborhood over-inflates the estimate exactly where the reference is
    narrowest - which showed up as a systematic +13% discount at the exact
    address tier. Pairing each listing with the sample it is actually scored
    against removes that by construction.
    """
    by_band: dict[tuple[str, str, int], list[float]] = {}
    by_city_band: dict[tuple[str, int], list[float]] = {}
    by_neighborhood: dict[tuple[str, str], list[float]] = {}
    by_construction: dict[str, list[float]] = {}

    for listing in listings:
        construction = itbi_construction_type(listing.tipo_imovel)
        area = _positive(listing.area_util_m2)
        price = _positive(listing.preco_total)
        if construction is None or area is None or price is None:
            continue
        if listing.area_origem == AREA_ORIGEM_INCERTA:
            # Área lida do texto entra no numerador do fator; um erro para baixo
            # infla o R$/m² pedido de toda a faixa.
            continue
        reference = select_reference(listing, index, index.reference_date)
        if reference is None or reference.preco_m2_mediano <= 0:
            continue
        if reference.amostra_count < min_sales and reference.tipo_referencia not in (
            "endereco_exato",
            "endereco_geo",
        ):
            # A reference too thin to trust would drag the factor with it.
            continue
        ratio = (price / area) / reference.preco_m2_mediano
        bairro = address_key(listing.bairro)
        band = area_band(area)
        by_construction.setdefault(construction, []).append(ratio)
        if band is not None:
            by_city_band.setdefault((construction, band), []).append(ratio)
        if bairro is None:
            continue
        by_neighborhood.setdefault((construction, bairro), []).append(ratio)
        if band is not None:
            by_band.setdefault((construction, bairro, band), []).append(ratio)

    def measured(groups: dict) -> dict:
        found = {}
        for key, ratios in groups.items():
            value = _median_of(ratios, min_listings)
            if value is not None and value > 0:
                found[key] = value
        return found

    return Calibration(
        by_band=measured(by_band),
        by_city_band=measured(by_city_band),
        by_neighborhood=measured(by_neighborhood),
        by_construction=measured(by_construction),
    )


def itbi_area_for(area: float) -> float:
    """The built area an ITBI row is expected to carry for this listing."""
    return area * AREA_MATCH_FACTOR


def _within_area(sale: Sale, area: float) -> bool:
    return area * (1 - AREA_TOLERANCE) <= float(sale.built_area_acquired) <= area * (1 + AREA_TOLERANCE)


def relative_dispersion(values: Sequence[float]) -> float:
    """Interquartile spread of the sample as a share of its median.

    This is how much the reference disagrees with itself, and it is what makes
    a discount comparable across tiers.
    """
    ordered = sorted(values)
    middle = median(ordered)
    if middle <= 0:
        return SMALL_SAMPLE_DISPERSION
    if len(ordered) < 4:
        return SMALL_SAMPLE_DISPERSION
    lower, _, upper = quantiles(ordered, n=4)
    return max((upper - lower) / middle, MIN_DISPERSION)


def _reference_from(sales: Sequence[Sale], tipo: str, area_range: tuple[float, float] | None) -> Reference:
    per_m2 = [sale_price_per_m2(sale) for sale in sales]
    return Reference(
        tipo_referencia=tipo,
        confianca=REFERENCE_CONFIDENCE[tipo],
        amostra_count=len(sales),
        preco_m2_mediano=median(per_m2),
        dispersao_relativa=relative_dispersion(per_m2),
        referencia_data_inicio=min(sale.settlement_date for sale in sales),
        referencia_data_fim=max(sale.settlement_date for sale in sales),
        area_minima=round(area_range[0], 2) if area_range else None,
        area_maxima=round(area_range[1], 2) if area_range else None,
    )


def select_reference(
    listing: ListingInput,
    sales: Sequence[Sale] | SaleIndex,
    reference: date | None = None,
) -> Reference | None:
    """Pick the narrowest ITBI sample that still meets its own sample floor."""
    index = _as_index(sales, reference)
    construction = itbi_construction_type(listing.tipo_imovel)
    bairro = address_key(listing.bairro)
    if construction is None or bairro is None:
        return None

    candidates = index.by_neighborhood.get((construction, bairro), [])
    if not candidates:
        return None

    # Converted: the window has to sit where the cartório records this unit,
    # not where the portal advertises it.
    area = _positive(listing.area_util_m2)
    esperada = itbi_area_for(area) if area else None
    area_range = (
        (esperada * (1 - AREA_TOLERANCE), esperada * (1 + AREA_TOLERANCE)) if esperada else None
    )

    def in_area(rows: Sequence[Sale]) -> list[Sale]:
        return [sale for sale in rows if esperada and _within_area(sale, esperada)]

    rua = street_key(listing.rua)
    numero = address_key(listing.numero)

    if rua is not None and numero is not None:
        no_predio = index.by_address.get((construction, bairro, rua, numero), [])
        # Num prédio cujas unidades já concordam em área, toda venda dele é
        # comparável, e filtrar por uma janela centrada num fator de cidade só
        # descarta a melhor evidência que existe.
        homogeneo = (
            listing.predio_dispersao_area is not None
            and listing.predio_dispersao_area <= HOMOGENEOUS_BUILDING_DISPERSION
        )
        exact = no_predio if homogeneo else in_area(no_predio)
        if len(exact) >= EXACT_MIN_SAMPLE:
            tier = "endereco_geo" if listing.numero_origem == NUMERO_ORIGEM_CADASTRO else "endereco_exato"
            return _reference_from(exact, tier, None if homogeneo else area_range)

    if rua is not None:
        street = in_area(index.by_street.get((construction, bairro, rua), []))
        if len(street) >= STREET_MIN_SAMPLE:
            return _reference_from(street, "rua", area_range)

    neighborhood_in_area = in_area(candidates)
    if len(neighborhood_in_area) >= BAIRRO_AREA_MIN_SAMPLE:
        return _reference_from(neighborhood_in_area, "bairro_area", area_range)

    if len(candidates) >= BAIRRO_AMPLO_MIN_SAMPLE:
        return _reference_from(candidates, "bairro_amplo", None)
    return None


def expected_error(tipo_referencia: str, dispersao_relativa: float) -> float:
    """How far this kind of reference typically lands from the truth."""
    banda = 0 if dispersao_relativa < DISPERSION_BANDS[0] else (
        1 if dispersao_relativa < DISPERSION_BANDS[1] else 2
    )
    return EXPECTED_ERROR.get(tipo_referencia, EXPECTED_ERROR["bairro_amplo"])[banda]


def score(
    *,
    desconto_pct: float,
    dispersao_relativa: float,
    tipo_referencia: str,
    preco_anunciado: float,
    preco_estimado: float,
) -> int:
    """A 0-100 reading of how good the evidence for this discount is.

    Two things have to be right for a listing to score high: the discount has to
    be large next to how far this kind of reference usually misses, and the
    asking price has to stay inside the range where a bargain is still a
    plausible reading of the data rather than a sign of bad input.
    """
    if preco_estimado <= 0:
        return 0
    signal = desconto_pct / expected_error(tipo_referencia, dispersao_relativa)
    strength = min(max(signal / SCORE_FULL_SIGNAL, 0.0), 1.0)

    # Past a point a deeper discount stops being better news and starts being
    # evidence the inputs are wrong, so the curve turns back down.
    ratio = preco_anunciado / preco_estimado
    plausibility = min(
        max((ratio - SCORE_IMPLAUSIBLE) / (SCORE_PLAUSIBLE - SCORE_IMPLAUSIBLE), 0.0), 1.0
    )

    return round(100 * strength * plausibility)


def qpreco_dispersion(suggestion: PriceSuggestion) -> float:
    """Half-width of the suggested range, relative to the suggested price.

    Same units as the ITBI reference's `dispersao_relativa`, so both scores are
    read on one scale. A suggestion published without a range says nothing
    about its own confidence, so it is treated as an ordinary spread rather
    than as a certainty.
    """
    price = _positive(suggestion.preco_sugerido)
    lower = _positive(suggestion.limite_inferior)
    upper = _positive(suggestion.limite_superior)
    if price is None or lower is None or upper is None or upper <= lower:
        return SMALL_SAMPLE_DISPERSION
    return (upper - lower) / (2 * price)


def score_qpreco(
    suggestion: PriceSuggestion, preco_anunciado: float
) -> tuple[float, int] | None:
    """Discount against QuintoAndar's estimate and the score it earns."""
    preco_sugerido = _positive(suggestion.preco_sugerido)
    if preco_sugerido is None:
        return None
    desconto_pct = round((preco_sugerido - preco_anunciado) / preco_sugerido, 4)
    nota = score(
        desconto_pct=desconto_pct,
        dispersao_relativa=qpreco_dispersion(suggestion),
        tipo_referencia=QPRECO_REFERENCE_TIER,
        preco_anunciado=preco_anunciado,
        preco_estimado=preco_sugerido,
    )
    return desconto_pct, nota


def unit_fingerprint(listing: ListingInput) -> str | None:
    """Identity of the physical unit, so one flat advertised by three agencies
    (or carried by three portals) does not become three alerts.

    The street number is deliberately left out. QuintoAndar and Loft never
    publish one, so keying on it would stop cross-portal duplicates from ever
    matching - which is the case this exists for. Street plus rounded area plus
    price to the thousand can, in principle, merge two identical units in the
    same building; for a buyer those are interchangeable anyway.
    """
    bairro = address_key(listing.bairro)
    rua = street_key(listing.rua)
    area = _positive(listing.area_util_m2)
    price = _positive(listing.preco_total)
    if bairro is None or rua is None or area is None or price is None:
        return None
    payload = {
        "bairro": bairro,
        "rua": rua,
        "area": round(area),
        "preco": round(price / 1000),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def fingerprint(
    *,
    source: str,
    listing_id: str,
    preco_anunciado: float,
    preco_estimado: float,
    desconto_pct: float,
    tipo_referencia: str,
    confianca: str,
    amostra_count: int,
    referencia_data_inicio: date,
    referencia_data_fim: date,
) -> str:
    """Stable digest of everything that makes an alert worth resending.

    The estimate and the discount are rounded coarsely on purpose: the
    calibration factor moves a little on every collection, and a digest
    sensitive to that would resend the same alert forever.
    """
    payload = {
        "source": source,
        "listing_id": listing_id,
        "preco_anunciado": round(float(preco_anunciado), 2),
        "preco_estimado": round(float(preco_estimado) / 1000),
        "desconto_pct": round(float(desconto_pct), 2),
        "tipo_referencia": tipo_referencia,
        "confianca": confianca,
        "amostra_count": int(amostra_count),
        "referencia_data_inicio": referencia_data_inicio.isoformat(),
        "referencia_data_fim": referencia_data_fim.isoformat(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _money(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"R$ {formatted}"


def _area(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + " m²"


def _motivos(
    listing: ListingInput, reference: Reference, area: float, fator: float, preco_m2_esperado: float
) -> tuple[str, ...]:
    escopo = REFERENCE_LABEL[reference.tipo_referencia]
    if reference.tipo_referencia == "endereco_exato":
        onde = f"{escopo} ({listing.rua}, {listing.numero})"
    elif reference.tipo_referencia == "rua":
        onde = f"{escopo} {listing.rua}"
    elif reference.tipo_referencia == "bairro_area":
        onde = f"{escopo} no bairro {listing.bairro}"
    else:
        onde = f"{escopo} no bairro {listing.bairro}, sem filtro de área"
    motivos = [
        f"Mediana de {reference.amostra_count} ITBIs residenciais por {onde}.",
        f"Janela de {WINDOW_MONTHS} meses entre "
        f"{reference.referencia_data_inicio.isoformat()} e {reference.referencia_data_fim.isoformat()}.",
        # O fator não é só prêmio de anúncio: o R$/m² do ITBI está em área
        # construída e o do anúncio em área útil, e a diferença entre as duas
        # (mediana de 1,6x em BH) está embutida nele. Chamá-lo de "anúncio sobre
        # ITBI" sugere uma coisa só, e são duas.
        f"ITBI de {_money(reference.preco_m2_mediano)}/m² construído ajustado pelo fator "
        f"{fator:.2f}x — que junta o quanto o anúncio pede acima da venda e o quanto a "
        f"área do cartório excede a anunciada —, chegando a {_money(preco_m2_esperado)}/m² "
        f"de área anunciada.",
        f"Referência aplicada a {_area(area)} anunciados "
        f"(ITBIs comparados na faixa de área construída equivalente).",
    ]
    if reference.area_minima is not None and reference.area_maxima is not None:
        motivos.append(
            f"Área comparável entre {_area(reference.area_minima)} e {_area(reference.area_maxima)}."
        )
    if reference.confianca == "baixa":
        motivos.append("Amostra insuficiente para endereço ou rua: confiança baixa.")
    return tuple(motivos)


def _motivo_qpreco(
    suggestion: PriceSuggestion, preco_anunciado: float, desconto_pct: float
) -> str:
    faixa = ""
    lower = _positive(suggestion.limite_inferior)
    upper = _positive(suggestion.limite_superior)
    if lower is not None and upper is not None and upper > lower:
        faixa = f" (faixa de {_money(lower)} a {_money(upper)})"
    lado = "abaixo" if desconto_pct >= 0 else "acima"
    percentual = f"{abs(desconto_pct) * 100:.1f}".replace(".", ",")
    return (
        f"QuintoAndar estima {_money(suggestion.preco_sugerido)}{faixa}: "
        f"anúncio {percentual}% {lado} dessa estimativa."
    )


def compute_opportunity(
    listing: ListingInput,
    sales: Sequence[Sale] | SaleIndex,
    reference_date: date | None,
    calibration: Calibration,
) -> Opportunity | None:
    """Estimate the expected asking price of a listing and its discount."""
    area = _positive(listing.area_util_m2)
    preco_anunciado = _positive(listing.preco_total)
    if area is None or preco_anunciado is None:
        return None

    index = _as_index(sales, reference_date)
    reference_day = reference_date or index.reference_date
    if reference_day is None:
        return None

    construction = itbi_construction_type(listing.tipo_imovel)
    if construction is None:
        return None

    reference = select_reference(listing, index, reference_day)
    if reference is None:
        return None

    fator = calibration.factor(construction, address_key(listing.bairro), area)
    if fator is None or fator <= 0:
        return None

    preco_m2_esperado = reference.preco_m2_mediano * fator
    preco_estimado = round(preco_m2_esperado * area, 2)
    if preco_estimado <= 0:
        return None
    desconto_pct = round((preco_estimado - preco_anunciado) / preco_estimado, 4)
    desconto_reais = round(preco_estimado - preco_anunciado, 2)
    nota_itbi = score(
        desconto_pct=desconto_pct,
        dispersao_relativa=reference.dispersao_relativa,
        tipo_referencia=reference.tipo_referencia,
        preco_anunciado=preco_anunciado,
        preco_estimado=preco_estimado,
    )
    motivos = _motivos(listing, reference, area, fator, preco_m2_esperado)

    # The two references have to agree for a listing to score high, and the
    # second one can only ever lower the score: a listing whose portal does not
    # publish an estimate must not be punished for the missing number.
    qpreco_desconto_pct: float | None = None
    qpreco_estimado: float | None = None
    nota_qpreco: int | None = None
    nota = nota_itbi
    qpreco_scored = (
        score_qpreco(listing.qpreco, preco_anunciado) if listing.qpreco is not None else None
    )
    referencia_primaria = "itbi"
    preco_primario, desconto_primario = preco_estimado, desconto_pct
    dispersao_primaria = reference.dispersao_relativa

    # Sem qpreco proprio, a mediana dos vizinhos ainda erra menos que a escada
    # de ITBI (6,7% contra 22,2%), entao ela responde antes dela.
    vizinhos = listing.qpreco_vizinhos
    if qpreco_scored is None and vizinhos is not None and vizinhos.preco_m2 > 0:
        referencia_primaria = "qpreco_vizinho"
        preco_primario = round(vizinhos.preco_m2 * area, 2)
        desconto_primario = round((preco_primario - preco_anunciado) / preco_primario, 4)
        dispersao_primaria = vizinhos.dispersao
        nota = score(
            desconto_pct=desconto_primario,
            dispersao_relativa=vizinhos.dispersao,
            tipo_referencia="qpreco_vizinho",
            preco_anunciado=preco_anunciado,
            preco_estimado=preco_primario,
        )
        motivos = (
            f"Mediana do valor que o QuintoAndar atribui a {vizinhos.amostra} "
            f"unidade(s) semelhante(s) na mesma rua: {_money(vizinhos.preco_m2)}/m², "
            f"chegando a {_money(preco_primario)}.",
        ) + motivos

    if qpreco_scored is not None:
        qpreco_desconto_pct, nota_qpreco = qpreco_scored
        qpreco_estimado = round(float(listing.qpreco.preco_sugerido), 2)
        # A referência mais precisa decide; a outra só derruba quando
        # *contradiz*. Na base, quase todo anúncio 15% abaixo do qpreço também
        # tem desconto positivo no ITBI — as duas concordam, e mesmo assim a
        # nota do ITBI sai baixa por ser dividida pelos 22% de erro dele.
        # Deixar isso vetar seria devolver o ruído da régua grossa à decisão.
        # Contradição é o ITBI dizer que o anúncio pede *acima* do esperado, e
        # por margem maior que o próprio erro dele.
        contradiz = desconto_pct < -expected_error(
            reference.tipo_referencia, reference.dispersao_relativa
        )
        nota = min(nota_itbi, nota_qpreco) if contradiz else nota_qpreco
        # O qpreço respondeu "quanto vale", então ele abre a lista e a leitura
        # de ITBI vem em seguida como conferência.
        motivos = (
            _motivo_qpreco(listing.qpreco, preco_anunciado, qpreco_desconto_pct),
        ) + motivos
        # O qpreco erra ~5% contra os 22,2% da escada de ITBI na previsao do
        # preco pedido, entao onde ele existe e ele quem responde "quanto vale".
        # A leitura de ITBI continua guardada como checagem.
        referencia_primaria = "qpreco"
        preco_primario = qpreco_estimado
        desconto_primario = qpreco_desconto_pct
        dispersao_primaria = qpreco_dispersion(listing.qpreco)

    return Opportunity(
        source=listing.source,
        listing_id=listing.listing_id,
        preco_anunciado=round(preco_anunciado, 2),
        preco_estimado=preco_primario,
        desconto_pct=desconto_primario,
        desconto_reais=round(preco_primario - preco_anunciado, 2),
        referencia_primaria=referencia_primaria,
        preco_estimado_itbi=preco_estimado,
        desconto_itbi_pct=desconto_pct,
        dispersao_primaria=dispersao_primaria,
        tipo_referencia=reference.tipo_referencia,
        confianca=reference.confianca,
        amostra_count=reference.amostra_count,
        referencia_data_inicio=reference.referencia_data_inicio,
        referencia_data_fim=reference.referencia_data_fim,
        preco_m2_mediano=round(reference.preco_m2_mediano, 2),
        fator_calibracao=round(fator, 4),
        unidade_fingerprint=unit_fingerprint(listing),
        dispersao_relativa=round(reference.dispersao_relativa, 4),
        area_origem=listing.area_origem,
        nota=nota,
        nota_itbi=nota_itbi,
        nota_qpreco=nota_qpreco,
        qpreco_estimado=qpreco_estimado,
        qpreco_desconto_pct=qpreco_desconto_pct,
        motivos=motivos,
        fingerprint=fingerprint(
            source=listing.source,
            listing_id=listing.listing_id,
            preco_anunciado=preco_anunciado,
            preco_estimado=preco_estimado,
            desconto_pct=desconto_pct,
            tipo_referencia=reference.tipo_referencia,
            confianca=reference.confianca,
            amostra_count=reference.amostra_count,
            referencia_data_inicio=reference.referencia_data_inicio,
            referencia_data_fim=reference.referencia_data_fim,
        ),
    )


def is_alert_eligible(
    opportunity: Opportunity | None,
    *,
    min_discount_pct: float = MIN_DISCOUNT_PCT,
    min_confianca: str = MIN_CONFIDENCE,
    min_nota: int = MIN_SCORE,
) -> bool:
    """An opportunity becomes an alert once its score clears the floor.

    The discount and confidence bounds remain as extra guards, but the score is
    the one that carries the meaning: it already weighs the discount against
    the spread and the depth of the sample behind it.
    """
    if opportunity is None:
        return False
    if opportunity.area_origem == AREA_ORIGEM_INCERTA:
        return False
    minimum = CONFIDENCE_ORDER.get(min_confianca, CONFIDENCE_ORDER[MIN_CONFIDENCE])
    # O piso acompanha o erro da referencia que respondeu: 30% contra a escada
    # de ITBI no tier de rua, 7,5% contra um qpreco de faixa estreita.
    tier = "qpreco" if opportunity.referencia_primaria == "qpreco" else opportunity.tipo_referencia
    piso = MIN_DISCOUNT_MULTIPLE * expected_error(tier, opportunity.dispersao_primaria)
    return (
        opportunity.nota >= min_nota
        and opportunity.desconto_pct >= max(piso, min_discount_pct)
        and CONFIDENCE_ORDER[opportunity.confianca] >= minimum
    )
