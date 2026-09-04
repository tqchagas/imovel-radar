from datetime import date

import pytest

from app.domain.appraisal import (
    DIVERGENCIA_ALERTA,
    MIN_COMPARAVEIS,
    avaliar,
    comparaveis_uteis,
    mediana_dos_vendidos,
)
from app.pricing.qpreco_calculadora import Estimate, SoldComparable


def _v(area=100.0, preco=1_000_000.0, quartos=3, dist=0.3, condo=False):
    return SoldComparable(
        house_id=1,
        price=preco,
        price_m2=preco / area,
        total_area=area,
        bedroom_count=quartos,
        parking_slots=1,
        distance_km=dist,
        sold_at=date(2026, 4, 1),
        address="Rua X",
        neighborhood="Y",
        city="Belo Horizonte",
        same_condo=condo,
    )


def _est(preco=1_000_000.0, certeza="medium"):
    return Estimate(
        suggested_price=preco,
        lower_bound=preco * 0.85,
        upper_bound=preco * 1.15,
        limit_lower=preco * 0.65,
        limit_upper=preco * 1.35,
        certainty=certeza,
        percentiles={50: preco},
    )


def test_filtra_por_area_quartos_e_distancia():
    """A janela existe para não comparar quarto-e-sala com cobertura."""
    uteis = comparaveis_uteis(
        [
            _v(area=100, quartos=3, dist=0.4),
            _v(area=125, quartos=3, dist=0.4),
            _v(area=100, quartos=2, dist=0.4),
            _v(area=100, quartos=3, dist=1.4),
        ],
        area=100,
        quartos=3,
    )
    assert len(uteis) == 1


def test_quartos_ausentes_nao_eliminam_o_comparavel():
    """`bedroomCount` volta nulo na maioria dos vendidos — 5 de 6 numa consulta
    medida ao vivo. Descartá-los esvaziaria a amostra; eles entram pela área."""
    uteis = comparaveis_uteis([_v(quartos=None)], area=100, quartos=3)
    assert len(uteis) == 1


def test_comparavel_sem_area_ou_sem_m2_nao_entra():
    sem_area = SoldComparable(1, 1_000_000, None, None, 3, 1, 0.3, None, "R", "B", "C", False)
    assert comparaveis_uteis([sem_area], area=100, quartos=3) == ()


def test_distancia_ausente_nao_elimina():
    """Sem distância declarada não há como saber que está longe, e o portal já
    devolveu essa lista como sendo do entorno."""
    assert len(comparaveis_uteis([_v(dist=None)], area=100, quartos=3)) == 1


def test_mediana_e_por_m2_e_nao_por_preco():
    """Os comparáveis têm áreas diferentes; a mediana dos preços responderia
    sobre o imóvel mediano da lista, não sobre este."""
    uteis = [_v(area=90, preco=900_000), _v(area=110, preco=1_320_000), _v(area=100, preco=1_100_000)]
    # R$/m2: 10.000, 12.000, 11.000 -> mediana 11.000 -> x 100 m2
    assert mediana_dos_vendidos(uteis, area=100) == pytest.approx(1_100_000)


def test_amostra_rasa_nao_produz_leitura():
    """Abaixo de três comparáveis a mediana é o próprio ruído."""
    poucos = [_v() for _ in range(MIN_COMPARAVEIS - 1)]
    assert mediana_dos_vendidos(poucos, area=100) is None


def test_divergencia_acima_do_corte_marca_atipico():
    a = avaliar(_est(1_000_000), [_v(preco=1_300_000) for _ in range(3)], area=100, quartos=3)

    assert a.preco_vendidos == pytest.approx(1_300_000)
    assert a.divergencia_pct == pytest.approx(0.30, abs=0.01)
    assert a.atipico is True
    assert a.comparaveis_usados == 3


def test_divergencia_pequena_nao_marca():
    a = avaliar(_est(1_000_000), [_v(preco=1_050_000) for _ in range(3)], area=100, quartos=3)

    assert abs(a.divergencia_pct) < DIVERGENCIA_ALERTA
    assert a.atipico is False


def test_sem_vendidos_a_estimativa_responde_sozinha():
    """Fora dos grandes centros o portal costuma não achar comparável. A
    estimativa continua valendo, e a ausência da segunda leitura é dita."""
    a = avaliar(_est(1_000_000), [], area=100, quartos=3)

    assert a.preco_qpreco == 1_000_000
    assert a.preco_vendidos is None
    assert a.divergencia_pct is None
    assert a.atipico is False
    assert a.comparaveis_usados == 0


def test_a_certeza_do_portal_atravessa():
    """`predictionCertainty` volta "low" com frequência, inclusive em bairro
    denso. É informação para quem lê, não erro."""
    assert avaliar(_est(certeza="low"), [], area=100, quartos=3).certeza == "low"
