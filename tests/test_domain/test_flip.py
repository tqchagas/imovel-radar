import pytest

from app.domain.flip import Imovel, orcar
from app.domain.flip_premissas import carregar_premissas

PREMISSAS = carregar_premissas()

# Imóvel de referência: 92 m² secos, 2 banheiros, 1 cozinha, 6 portas.
IMOVEL = Imovel(area_seca_m2=92.0, banheiros=2, cozinhas=1, portas=6)


def _grupo(orcamento, chave):
    return next(g for g in orcamento.grupos if g.chave == chave)


def test_areas_secas_somam_taco_e_pintura() -> None:
    # 92 × 0,70 × 75 = 4.830 de taco; 92 × 60 = 5.520 de pintura.
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "areas_secas")
    assert grupo.total == pytest.approx(10_350.0)


def test_banheiro_custa_6100_por_unidade() -> None:
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "banheiros")
    assert grupo.total == pytest.approx(12_200.0)


def test_cozinha_custa_8700() -> None:
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "cozinha")
    assert grupo.total == pytest.approx(8_700.0)


def test_geral_soma_eletrica_portas_e_cacamba() -> None:
    # 2.500 + 6 × 200 + 1.200 = 4.900.
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "geral")
    assert grupo.total == pytest.approx(4_900.0)


def test_sem_retrofit_o_grupo_fica_zerado() -> None:
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "retrofit")
    assert grupo.total == 0.0
    assert grupo.itens == ()


def test_total_aplica_contingencia_sobre_o_subtotal() -> None:
    orcamento = orcar(IMOVEL, PREMISSAS)
    assert orcamento.subtotal == pytest.approx(36_150.0)
    assert orcamento.contingencia == pytest.approx(5_422.5)
    assert orcamento.total == pytest.approx(41_572.5)


def test_contingencia_nao_incide_sobre_si_mesma() -> None:
    # 36.150 × 1,15 = 41.572,50. Se a contingência entrasse no subtotal, o
    # total seria 41.572,50 × 1,15 = 47.808,38.
    orcamento = orcar(IMOVEL, PREMISSAS)
    assert orcamento.total == pytest.approx(orcamento.subtotal * 1.15)


def test_retrofit_completo_soma_os_tres_itens() -> None:
    # 5.000 de elétrica + 2.500 × 2 banheiros + 2.000 de cozinha = 12.000.
    imovel = Imovel(
        area_seca_m2=92.0,
        banheiros=2,
        cozinhas=1,
        portas=6,
        eletrica_completa=True,
        hidraulica_completa_banheiro=True,
        hidraulica_completa_cozinha=True,
    )
    orcamento = orcar(imovel, PREMISSAS)
    assert _grupo(orcamento, "retrofit").total == pytest.approx(12_000.0)
    assert orcamento.subtotal == pytest.approx(48_150.0)
    assert orcamento.total == pytest.approx(55_372.5)


def test_imovel_sem_banheiro_nao_orca_banheiro() -> None:
    orcamento = orcar(Imovel(area_seca_m2=50.0, banheiros=0, cozinhas=0, portas=0), PREMISSAS)
    assert _grupo(orcamento, "banheiros").total == 0.0
    assert _grupo(orcamento, "cozinha").total == 0.0


def test_cada_item_carrega_quantidade_e_custo_unitario() -> None:
    # A tela mostra o caderno de encargos linha a linha; sem isso ela teria de
    # refazer a conta para exibir "6 × R$ 200".
    portas = next(
        item for item in _grupo(orcar(IMOVEL, PREMISSAS), "geral").itens if item.chave == "portas"
    )
    assert portas.quantidade == 6
    assert portas.custo_unitario == pytest.approx(200.0)
    assert portas.total == pytest.approx(1_200.0)
    assert "Portas" in portas.rotulo
