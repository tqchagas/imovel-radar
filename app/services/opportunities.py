"""Materialize listing opportunities from ITBI references."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Callable

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.http_client import PortalBlocked
from app.domain.market_stats import Sale
from app.domain.opportunities import (
    MIN_CALIBRATION_LISTINGS,
    NeighbourEstimate,
    MIN_CALIBRATION_SALES,
    MIN_CONFIDENCE,
    MIN_DISCOUNT_PCT,
    MIN_SCORE,
    RESIDENTIAL_OCCUPATION,
    ListingInput,
    Opportunity,
    PriceSuggestion,
    SaleIndex,
    address_key,
    build_calibration,
    compute_opportunity,
    relative_dispersion,
    is_alert_eligible,
    window_bounds,
)
from app.models.market_comparable import MarketComparable
from app.models.transaction import Transaction

# One QuintoAndar call per listing, so only listings that would already raise an
# alert on the ITBI reference are worth asking about, and only a bounded number
# of them per run.
QPRECO_SOURCE = "quintoandar"
QPRECO_FETCH_LIMIT = 50
# Consecutive failures that read as "the portal stopped answering us" rather
# than as one bad listing.
QPRECO_MAX_CONSECUTIVE_FAILURES = 3
# The portal re-estimates slowly; a month-old suggestion is still the same
# reading of the same unit.
QPRECO_TTL_DAYS = 30

# O contexto de vizinhanca vale para qualquer fonte, porque o endpoint pergunta
# por coordenada e nao por id de anuncio. Ele nao entra na nota, entao serve
# tambem aos anuncios que ja alertaram: e o que a tela mostra ao lado deles.
SIMILARES_FETCH_LIMIT = 50
SIMILARES_TTL_DAYS = 30

# Regua emprestada: a mediana do qpreco de unidades semelhantes na mesma rua.
# Loft e VivaReal nunca terao qpreco proprio, porque o endpoint resolve por id
# do QuintoAndar — mas 48% e 69% deles dividem rua e faixa de area com um
# anuncio que tem. Medido escondendo o qpreco do proprio anuncio: 6,7% de erro
# com cinco vizinhos, contra os 22,2% da escada de ITBI.
VIZINHO_AREA_TOLERANCE = 0.20
VIZINHO_MIN_AMOSTRA = 2

SALE_COLUMNS = (
    Transaction.neighborhood,
    Transaction.street,
    Transaction.street_number,
    Transaction.settlement_date,
    Transaction.declared_value,
    Transaction.built_area_acquired,
    Transaction.construction_type,
    Transaction.occupation_type,
)

OPPORTUNITY_COLUMNS = (
    "preco_estimado",
    "desconto_pct",
    "desconto_reais",
    "tipo_referencia",
    "amostra_count",
    "referencia_data_inicio",
    "referencia_data_fim",
    "confianca",
    "nota",
    "referencia_primaria",
    "preco_estimado_itbi",
    "desconto_itbi_pct",
    "nota_itbi",
    "nota_qpreco",
    "qpreco_desconto_pct",
    "dispersao_relativa",
    "fator_calibracao",
    "unidade_fingerprint",
    "oportunidade_motivo",
    "oportunidade_fingerprint",
)


def _valid_residential(stmt: Select, city_key: str) -> Select:
    return stmt.where(
        Transaction.city == city_key,
        func.upper(Transaction.occupation_type) == RESIDENTIAL_OCCUPATION,
        Transaction.declared_value > 0,
        Transaction.built_area_acquired > 0,
    )


def latest_reference_date(db: Session, city: str) -> date | None:
    """Latest settlement date of a usable residential ITBI row in the city."""
    city_key = address_key(city)
    if city_key is None:
        return None
    return db.scalar(
        _valid_residential(select(func.max(Transaction.settlement_date)), city_key)
    )


def fetch_reference_sales(db: Session, city: str, start: date, end: date) -> list[Sale]:
    """Usable residential ITBI rows of the city inside the inclusive window."""
    city_key = address_key(city)
    if city_key is None:
        return []
    stmt = _valid_residential(select(*SALE_COLUMNS), city_key).where(
        Transaction.settlement_date >= start,
        Transaction.settlement_date <= end,
    )
    return [
        Sale(
            neighborhood=row.neighborhood,
            street=row.street,
            street_number=row.street_number,
            settlement_date=row.settlement_date,
            declared_value=float(row.declared_value),
            built_area_acquired=float(row.built_area_acquired),
            construction_type=row.construction_type,
            occupation_type=row.occupation_type,
        )
        for row in db.execute(stmt)
    ]


def _as_float(value) -> float | None:
    return float(value) if value is not None else None


def _price_suggestion(listing: MarketComparable) -> PriceSuggestion | None:
    preco = _as_float(listing.price_suggestion_price)
    if preco is None or preco <= 0:
        return None
    return PriceSuggestion(
        preco_sugerido=preco,
        limite_inferior=_as_float(listing.price_suggestion_lower_bound),
        limite_superior=_as_float(listing.price_suggestion_upper_bound),
    )


def _neighbour_index(listings: list[MarketComparable]) -> dict[tuple, list[tuple[float, float]]]:
    """Qpreco por m2 de cada anuncio avaliado, agrupado por rua."""
    index: dict[tuple, list[tuple[float, float]]] = {}
    for row in listings:
        preco = _as_float(row.price_suggestion_price)
        area = _as_float(row.area_util_m2)
        chave = (row.bairro_normalizado, row.rua_normalizada)
        if preco and area and preco > 0 and area > 0 and all(chave):
            index.setdefault(chave, []).append((area, preco / area))
    return index


def _neighbour_estimate(
    listing: MarketComparable, index: dict[tuple, list[tuple[float, float]]]
) -> NeighbourEstimate | None:
    area = _as_float(listing.area_util_m2)
    chave = (listing.bairro_normalizado, listing.rua_normalizada)
    if not area or area <= 0 or not all(chave):
        return None
    proprio = _as_float(listing.price_suggestion_price)
    vizinhos = [
        preco_m2
        for (outra_area, preco_m2) in index.get(chave, [])
        # O proprio anuncio nao e vizinho de si mesmo.
        if not (proprio and abs(preco_m2 * outra_area - proprio) < 0.01 and outra_area == area)
        and abs(outra_area - area) <= area * VIZINHO_AREA_TOLERANCE
    ]
    if len(vizinhos) < VIZINHO_MIN_AMOSTRA:
        return None
    return NeighbourEstimate(
        preco_m2=median(vizinhos),
        dispersao=relative_dispersion(vizinhos),
        amostra=len(vizinhos),
    )


def _listing_input(
    listing: MarketComparable, vizinhos: NeighbourEstimate | None = None
) -> ListingInput:
    return ListingInput(
        source=listing.source,
        listing_id=listing.listing_id,
        tipo_imovel=listing.tipo_imovel,
        area_util_m2=_as_float(listing.area_util_m2),
        preco_total=_as_float(listing.preco_total),
        bairro=listing.bairro_normalizado or listing.bairro,
        rua=listing.rua_normalizada or listing.rua,
        numero=listing.numero_normalizado or listing.numero,
        qpreco=_price_suggestion(listing),
        qpreco_vizinhos=vizinhos,
        area_origem=listing.area_origem,
    )


def _clear(listing: MarketComparable) -> None:
    for column in OPPORTUNITY_COLUMNS:
        setattr(listing, column, None)


def _materialize(
    listing: MarketComparable,
    opportunity: Opportunity,
    *,
    min_discount_pct: float,
    min_confianca: str,
    min_nota: int,
) -> bool:
    listing.preco_estimado = opportunity.preco_estimado
    listing.desconto_pct = opportunity.desconto_pct
    listing.desconto_reais = opportunity.desconto_reais
    listing.tipo_referencia = opportunity.tipo_referencia
    listing.amostra_count = opportunity.amostra_count
    listing.referencia_data_inicio = opportunity.referencia_data_inicio
    listing.referencia_data_fim = opportunity.referencia_data_fim
    listing.confianca = opportunity.confianca
    listing.nota = opportunity.nota
    listing.referencia_primaria = opportunity.referencia_primaria
    listing.preco_estimado_itbi = opportunity.preco_estimado_itbi
    listing.desconto_itbi_pct = opportunity.desconto_itbi_pct
    listing.nota_itbi = opportunity.nota_itbi
    listing.nota_qpreco = opportunity.nota_qpreco
    listing.qpreco_desconto_pct = opportunity.qpreco_desconto_pct
    listing.dispersao_relativa = opportunity.dispersao_relativa
    listing.fator_calibracao = opportunity.fator_calibracao
    listing.unidade_fingerprint = opportunity.unidade_fingerprint
    listing.oportunidade_motivo = "\n".join(opportunity.motivos)
    eligible = is_alert_eligible(
        opportunity,
        min_discount_pct=min_discount_pct,
        min_confianca=min_confianca,
        min_nota=min_nota,
    )
    # Only alertable opportunities get a fingerprint: it is the notification baseline.
    listing.oportunidade_fingerprint = opportunity.fingerprint if eligible else None
    return eligible


def _suppress_duplicate_units(
    listings: list[MarketComparable],
    eligible_units: dict[int, str | None],
    best_of_unit: dict[str, tuple[float, int]],
) -> int:
    """Drop the alert baseline of every listing that repeats a unit already won
    by a deeper discount. The opportunity itself stays on the row - only the
    fingerprint goes, and that is what the notification job reads."""
    suppressed = 0
    for listing in listings:
        unit = eligible_units.get(listing.id)
        if unit is None:
            continue
        winner = best_of_unit.get(unit)
        if winner is not None and winner[1] != listing.id:
            listing.oportunidade_fingerprint = None
            suppressed += 1
    return suppressed


def _active_listings(db: Session, city_key: str, source: str | None) -> list[MarketComparable]:
    stmt = (
        select(MarketComparable)
        .where(
            MarketComparable.cidade_normalizada == city_key,
            MarketComparable.ativo.is_(True),
        )
        .order_by(MarketComparable.id)
    )
    if source:
        stmt = stmt.where(MarketComparable.source == source)
    return list(db.scalars(stmt))


def _naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _stale(quando: datetime | None, now: datetime, ttl_days: int) -> bool:
    """True quando o dado guardado falta ou já é velho o bastante para reperguntar."""
    updated_at = _naive(quando)
    if updated_at is None:
        return True
    return updated_at < _naive(now) - timedelta(days=ttl_days)


def _enrich(
    candidates: list[MarketComparable],
    *,
    fetcher: Callable[[MarketComparable], bool],
    limit: int,
) -> tuple[list[MarketComparable], int, str | None]:
    """Roda o buscador nos candidatos, parando quando o portal manda parar."""
    updated: list[MarketComparable] = []
    failed = 0
    consecutive = 0
    stopped: str | None = None
    for listing in candidates[: max(0, limit)]:
        try:
            fetcher(listing)
        except PortalBlocked:
            # Being refused is the portal saying stop. Draining the budget
            # against it is what turns a throttle into a block.
            failed += 1
            stopped = "bloqueado"
            break
        except Exception:  # noqa: BLE001 - one bad listing must not stop the run
            failed += 1
            consecutive += 1
            if consecutive >= QPRECO_MAX_CONSECUTIVE_FAILURES:
                stopped = "falhas_seguidas"
                break
            continue
        consecutive = 0
        updated.append(listing)
    return updated, failed, stopped


def _qpreco_candidates(
    listings: list[MarketComparable],
    opportunities: dict[int, Opportunity | None],
    *,
    now: datetime,
    ttl_days: int,
    min_discount_pct: float,
    min_confianca: str,
    min_nota: int,
) -> list[MarketComparable]:
    """Anúncios cuja leitura de ITBI já alerta.

    A sugestão só reduz nota, então um anúncio que não passa do piso pelo ITBI
    sozinho nunca chegaria lá com a segunda referência — perguntar gastaria uma
    requisição para não mudar nada.
    """
    candidates = [
        listing
        for listing in listings
        if listing.source == QPRECO_SOURCE
        and (listing.listing_id or "").strip()
        and is_alert_eligible(
            opportunities.get(listing.id),
            min_discount_pct=min_discount_pct,
            min_confianca=min_confianca,
            min_nota=min_nota,
        )
        and _stale(listing.price_suggestion_updated_at, now, ttl_days)
    ]
    candidates.sort(key=lambda row: (-(opportunities[row.id].nota), row.id))
    return candidates


def _similares_candidates(
    listings: list[MarketComparable],
    opportunities: dict[int, Opportunity | None],
    *,
    now: datetime,
    ttl_days: int,
    min_discount_pct: float,
    min_confianca: str,
    min_nota: int,
) -> list[MarketComparable]:
    """Os mesmos anúncios que alertam, de qualquer fonte e com coordenada."""
    candidates = [
        listing
        for listing in listings
        if listing.lat is not None
        and listing.lon is not None
        and is_alert_eligible(
            opportunities.get(listing.id),
            min_discount_pct=min_discount_pct,
            min_confianca=min_confianca,
            min_nota=min_nota,
        )
        and _stale(listing.similares_updated_at, now, ttl_days)
    ]
    candidates.sort(key=lambda row: (-(opportunities[row.id].nota), row.id))
    return candidates


def refresh_opportunities(
    db: Session,
    *,
    city: str,
    source: str | None = None,
    min_discount_pct: float = MIN_DISCOUNT_PCT,
    min_confianca: str = MIN_CONFIDENCE,
    min_nota: int = MIN_SCORE,
    min_calibration_listings: int = MIN_CALIBRATION_LISTINGS,
    min_calibration_sales: int = MIN_CALIBRATION_SALES,
    qpreco_fetcher: Callable[[MarketComparable], bool] | None = None,
    qpreco_limit: int = QPRECO_FETCH_LIMIT,
    qpreco_ttl_days: int = QPRECO_TTL_DAYS,
    similares_fetcher: Callable[[MarketComparable], bool] | None = None,
    similares_limit: int = SIMILARES_FETCH_LIMIT,
    similares_ttl_days: int = SIMILARES_TTL_DAYS,
    now: datetime | None = None,
    commit: bool = True,
) -> dict:
    """Recalculate and persist the opportunity fields of every active listing."""
    city_key = address_key(city)
    summary = {
        "city": city_key,
        "source": source,
        "reference_date": None,
        "listings": 0,
        "calculated": 0,
        "cleared": 0,
        "alta": 0,
        "media": 0,
        "baixa": 0,
        "eligible": 0,
        "duplicates": 0,
        "qpreco_buscados": 0,
        "qpreco_falhas": 0,
        "qpreco_interrompido": None,
        "similares_buscados": 0,
        "similares_falhas": 0,
        "similares_interrompido": None,
    }
    if city_key is None:
        return summary

    listings = _active_listings(db, city_key, source)
    summary["listings"] = len(listings)
    if not listings:
        if commit:
            db.commit()
        return summary

    reference_day = latest_reference_date(db, city_key)
    summary["reference_date"] = reference_day
    if reference_day is None:
        if commit:
            db.commit()
        return summary

    start, end = window_bounds(reference_day)
    sales = fetch_reference_sales(db, city_key, start, end)

    vizinhanca = _neighbour_index(listings)
    inputs = {
        listing.id: _listing_input(listing, _neighbour_estimate(listing, vizinhanca))
        for listing in listings
    }
    index = SaleIndex.build(sales, reference_day)
    calibration = build_calibration(
        inputs.values(),
        index,
        min_listings=min_calibration_listings,
        min_sales=min_calibration_sales,
    )

    # A unit advertised by several agencies, or carried by more than one
    # portal, is one opportunity. Keep the deepest discount and let the rest
    # be calculated but never alerted.
    best_of_unit: dict[str, tuple[float, int]] = {}
    eligible_units: dict[int, str | None] = {}

    opportunities: dict[int, Opportunity | None] = {
        listing.id: compute_opportunity(inputs[listing.id], index, reference_day, calibration)
        for listing in listings
    }

    instante = now or datetime.now(timezone.utc)
    limites = {
        "min_discount_pct": min_discount_pct,
        "min_confianca": min_confianca,
        "min_nota": min_nota,
    }

    # Segunda referência: a estimativa do próprio QuintoAndar, buscada só para
    # os anúncios que o ITBI já sinaliza, e repontuada na mesma execução.
    if qpreco_fetcher is not None:
        updated, failed, stopped = _enrich(
            _qpreco_candidates(
                listings, opportunities, now=instante, ttl_days=qpreco_ttl_days, **limites
            ),
            fetcher=qpreco_fetcher,
            limit=qpreco_limit,
        )
        summary["qpreco_buscados"] = len(updated)
        summary["qpreco_falhas"] = failed
        summary["qpreco_interrompido"] = stopped
        for listing in updated:
            inputs[listing.id] = _listing_input(
                listing, _neighbour_estimate(listing, vizinhanca)
            )
            opportunities[listing.id] = compute_opportunity(
                inputs[listing.id], index, reference_day, calibration
            )

    # Contexto de vizinhança: vale para as três fontes e não repontua nada, por
    # ser média do entorno e não avaliação da unidade.
    if similares_fetcher is not None:
        updated, failed, stopped = _enrich(
            _similares_candidates(
                listings, opportunities, now=instante, ttl_days=similares_ttl_days, **limites
            ),
            fetcher=similares_fetcher,
            limit=similares_limit,
        )
        summary["similares_buscados"] = len(updated)
        summary["similares_falhas"] = failed
        summary["similares_interrompido"] = stopped

    for listing in listings:
        opportunity = opportunities[listing.id]
        if opportunity is None:
            _clear(listing)
            summary["cleared"] += 1
            continue
        eligible = _materialize(
            listing,
            opportunity,
            min_discount_pct=min_discount_pct,
            min_confianca=min_confianca,
            min_nota=min_nota,
        )
        summary["calculated"] += 1
        summary[opportunity.confianca] += 1
        if eligible:
            unit = opportunity.unidade_fingerprint
            eligible_units[listing.id] = unit
            if unit is not None:
                current = best_of_unit.get(unit)
                if current is None or opportunity.desconto_pct > current[0]:
                    best_of_unit[unit] = (opportunity.desconto_pct, listing.id)

    duplicates = _suppress_duplicate_units(listings, eligible_units, best_of_unit)
    summary["duplicates"] = duplicates
    summary["eligible"] = len(eligible_units) - duplicates

    if commit:
        db.commit()
    else:
        db.flush()
    return summary
