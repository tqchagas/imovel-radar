import pytest

from app.domain.flip import (
    MESES_CENARIO,
    PRAZO_MAXIMO_BUSCA,
    VARIACOES_VENDA,
    Imovel,
    Negocio,
    calcular_dre,
    calcular_mao,
    matriz_sensibilidade,
    orcar,
    prazo_limite,
    simular,
    venda_breakeven,
)
from app.domain.flip_premissas import carregar_premissas

PREMISSAS = carregar_premissas()

# Imóvel de referência: 92 m² secos, 2 banheiros, 1 cozinha, 6 portas.
IMOVEL = Imovel(area_seca_m2=92.0, banheiros=2, cozinhas=1, portas=6)
NEGOCIO = Negocio(preco_compra=680_000.0, arv_total=1_080_000.0, meses_carrego=7)


def _grupo(orcamento, chave):
    return next(g for g in orcamento.grupos if g.chave == chave)


def test_areas_secas_somam_taco_e_pintura() -> None:
    # 92 × 0,70 × 75 = 4.830 de taco; 92 × 60 = 5.520 de pintura.
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "areas_secas")
    assert grupo.total == pytest.approx(10_350.0)


def test_orcamento_aferivel_separa_etapas_e_quantidades() -> None:
    imovel = Imovel(
        area_seca_m2=92, banheiros=2, cozinhas=1, portas=6,
        escopo_obra="revenda",
        quantidades={"pintura_paredes_m2": 180, "pintura_teto_m2": 80,
                     "piso_banheiro_m2": 8, "piso_banheiros_medidos": 2,
                     "piso_cozinha_m2": 12, "piso_cozinhas_medidas": 1},
    )
    orcamento = orcar(imovel, PREMISSAS)
    assert {g.chave for g in orcamento.grupos} == {
        "demolicao", "infraestrutura", "acabamentos", "marcenaria", "geral"
    }
    demolicao = _grupo(orcamento, "demolicao")
    assert demolicao.total == pytest.approx(20 * 16.83)
    acabamentos = {i.chave: i for i in _grupo(orcamento, "acabamentos").itens}
    assert acabamentos["sudecap_pintura_paredes"].total == pytest.approx(180 * 16.58)
    assert acabamentos["sudecap_pintura_teto"].total == pytest.approx(80 * 18.68)
    assert acabamentos["sudecap_assentamento_piso"].total == pytest.approx(20 * 57)
    assert "pintura_seca" not in acabamentos
    assert "banho_piso" not in acabamentos
    assert "coz_piso" not in acabamentos
    assert "SUDECAP" in acabamentos["sudecap_pintura_paredes"].fonte


def test_retoques_nao_incluem_reforma_de_banheiro_cozinha_ou_retrofit() -> None:
    imovel = Imovel(area_seca_m2=50, banheiros=2, cozinhas=1,
                    escopo_obra="retoques", quantidades={"piso_banheiro_m2": 8, "piso_banheiros_medidos": 2})
    orcamento = orcar(imovel, PREMISSAS)
    assert _grupo(orcamento, "demolicao").total == 0
    assert _grupo(orcamento, "marcenaria").total == 0
    assert _grupo(orcamento, "infraestrutura").total == 0


def test_pintura_parcial_conserva_provisao_da_superficie_nao_medida() -> None:
    base = Imovel(area_seca_m2=80, banheiros=0, cozinhas=0, escopo_obra="retoques")
    sem_medida = {i.chave: i for i in _grupo(orcar(base, PREMISSAS), "acabamentos").itens}
    assert sem_medida["pintura_seca"].total == 4800

    so_paredes = Imovel(area_seca_m2=80, banheiros=0, cozinhas=0,
                        escopo_obra="retoques", quantidades={"pintura_paredes_m2": 1})
    itens = {i.chave: i for i in _grupo(orcar(so_paredes, PREMISSAS), "acabamentos").itens}
    assert itens["sudecap_pintura_paredes"].total == pytest.approx(16.58)
    assert itens["provisao_pintura_teto"].total == pytest.approx(80 * 15)
    assert "pintura_seca" not in itens

    so_teto = Imovel(area_seca_m2=80, banheiros=0, cozinhas=0,
                     escopo_obra="retoques", quantidades={"pintura_teto_m2": 1})
    itens = {i.chave: i for i in _grupo(orcar(so_teto, PREMISSAS), "acabamentos").itens}
    assert itens["provisao_pintura_paredes"].total == pytest.approx(80 * 45)


def test_piso_medido_em_um_banheiro_mantem_provisao_do_outro() -> None:
    imovel = Imovel(area_seca_m2=80, banheiros=2, cozinhas=0,
                    escopo_obra="revenda", quantidades={
                        "piso_banheiro_m2": 4, "piso_banheiros_medidos": 1,
                    })
    itens = {i.chave: i for i in _grupo(orcar(imovel, PREMISSAS), "acabamentos").itens}
    assert itens["banho_piso"].quantidade == 1
    assert itens["sudecap_assentamento_piso"].quantidade == 4


def test_piso_medido_em_uma_cozinha_mantem_provisao_da_outra() -> None:
    imovel = Imovel(area_seca_m2=80, banheiros=0, cozinhas=2,
                    escopo_obra="revenda", quantidades={
                        "piso_cozinha_m2": 7, "piso_cozinhas_medidas": 1,
                    })
    itens = {i.chave: i for i in _grupo(orcar(imovel, PREMISSAS), "acabamentos").itens}
    assert itens["coz_piso"].quantidade == 1
    assert itens["sudecap_assentamento_piso"].quantidade == 7


def test_retrofit_medido_mostra_rasgo_recomposicao_e_provisoes_sem_duplicar_fixo() -> None:
    imovel = Imovel(area_seca_m2=50, banheiros=1, cozinhas=1,
                    escopo_obra="retrofit", quantidades={
                        "cabo_eletrico_m": 100, "rasgo_eletrico_m": 20,
                        "tubo_agua_m": 15, "rasgo_hidraulico_m": 10,
                    })
    itens = {i.chave: i for i in _grupo(orcar(imovel, PREMISSAS), "infraestrutura").itens}
    assert itens["sudecap_rasgo"].quantidade == 30
    assert itens["sudecap_recomposicao"].quantidade == 30
    assert itens["sudecap_cabo_2_5"].total == pytest.approx(394)
    assert itens["sudecap_tubo_agua_25"].total == pytest.approx(130.2)
    assert "eletrica_completa" not in itens
    assert "hidraulica_completa_banheiro" not in itens
    assert "provisao_eletrica_complementar" in itens



def test_banheiro_custa_6100_por_unidade() -> None:
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "banheiros")
    assert grupo.total == pytest.approx(12_200.0)


def test_cozinha_custa_8700() -> None:
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "cozinha")
    assert grupo.total == pytest.approx(8_700.0)


def test_marcenaria_pode_ser_retirada_do_orcamento() -> None:
    imovel = Imovel(
        area_seca_m2=92.0,
        banheiros=2,
        cozinhas=1,
        portas=6,
        incluir_marcenaria=False,
    )
    orcamento = orcar(imovel, PREMISSAS)

    itens_banheiro = {item.chave for item in _grupo(orcamento, "banheiros").itens}
    itens_cozinha = {item.chave for item in _grupo(orcamento, "cozinha").itens}
    assert "banho_marcenaria" not in itens_banheiro
    assert "coz_marcenaria" not in itens_cozinha
    assert "banho_bancada" in itens_banheiro
    assert "coz_bancada" in itens_cozinha
    assert orcamento.total == pytest.approx(36_282.5)


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


def test_custos_de_aquisicao_saem_das_premissas() -> None:
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    assert dre.itbi == pytest.approx(20_400.0)  # 3% de 680.000
    assert dre.registro == pytest.approx(10_200.0)  # 1,5% de 680.000


def test_carrego_soma_condominio_iptu_e_consumo_por_mes() -> None:
    # (550 + 120 + 80) × 7 = 5.250.
    assert calcular_dre(IMOVEL, NEGOCIO, PREMISSAS).carrego == pytest.approx(5_250.0)


def test_ganho_de_capital_desconta_corretagem_obra_e_aquisicao() -> None:
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    assert dre.corretagem == pytest.approx(54_000.0)
    assert dre.ganho_capital == pytest.approx(273_827.5)
    assert dre.ir_ganho_capital == pytest.approx(41_074.125)


def test_lucro_capital_roi_e_tir_do_caso_de_referencia() -> None:
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    assert dre.obra == pytest.approx(41_572.5)
    assert dre.lucro_liquido == pytest.approx(227_503.375)
    assert dre.capital_empatado == pytest.approx(757_422.5)
    assert dre.roi == pytest.approx(0.3003652, abs=1e-6)
    assert dre.tir_anual == pytest.approx(0.5687025, abs=1e-6)


def test_prejuizo_nao_paga_imposto() -> None:
    # Comprou caro e vende barato: sem ganho, sem IR — e o lucro fica negativo.
    negocio = Negocio(preco_compra=900_000.0, arv_total=800_000.0, meses_carrego=7)
    dre = calcular_dre(IMOVEL, negocio, PREMISSAS)
    assert dre.ganho_capital < 0
    assert dre.ir_ganho_capital == 0.0
    assert dre.lucro_liquido < 0


def test_tir_de_prazo_menor_que_um_ano_anualiza_para_cima() -> None:
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    assert dre.tir_anual > dre.roi


def test_obra_pode_ser_injetada_para_nao_reorcar() -> None:
    # A matriz roda nove cenários que mudam venda e prazo, nunca a obra.
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS, obra_total=100_000.0)
    assert dre.obra == pytest.approx(100_000.0)


def test_carrego_zerado_nao_quebra_a_tir() -> None:
    # 12/0 seria divisão por zero; a TIR de prazo nulo é o próprio ROI.
    negocio = Negocio(preco_compra=680_000.0, arv_total=1_080_000.0, meses_carrego=0)
    dre = calcular_dre(IMOVEL, negocio, PREMISSAS)
    assert dre.carrego == 0.0
    assert dre.tir_anual == pytest.approx(dre.roi)


def test_comprar_no_mao_devolve_exatamente_o_roi_alvo() -> None:
    # É o teste que prova a bisseção: recalcular o DRE com o preço que ela achou
    # tem de cair em 18%.
    mao = calcular_mao(IMOVEL, NEGOCIO, PREMISSAS)
    dre = calcular_dre(IMOVEL, Negocio(mao, NEGOCIO.arv_total, NEGOCIO.meses_carrego), PREMISSAS)
    assert dre.roi == pytest.approx(0.18, abs=1e-4)


def test_mao_fica_acima_do_preco_quando_o_roi_atual_supera_o_alvo() -> None:
    # O caso de referência dá ROI de 30%, acima dos 18% alvo: o teto está acima
    # do preço pedido, e comprar por 680k sobra margem.
    assert calcular_mao(IMOVEL, NEGOCIO, PREMISSAS) > NEGOCIO.preco_compra


def test_mao_cai_quando_o_roi_alvo_sobe() -> None:
    exigente = calcular_mao(IMOVEL, NEGOCIO, PREMISSAS, roi_alvo=0.35)
    frouxo = calcular_mao(IMOVEL, NEGOCIO, PREMISSAS, roi_alvo=0.05)
    assert exigente < frouxo


def test_mao_cai_quando_a_obra_encarece() -> None:
    caro = Imovel(
        area_seca_m2=92.0,
        banheiros=2,
        cozinhas=1,
        portas=6,
        eletrica_completa=True,
        hidraulica_completa_banheiro=True,
        hidraulica_completa_cozinha=True,
    )
    assert calcular_mao(caro, NEGOCIO, PREMISSAS) < calcular_mao(IMOVEL, NEGOCIO, PREMISSAS)


def test_negocio_impossivel_tem_mao_zero() -> None:
    # Venda que não cobre nem a obra: não existe preço de compra positivo que
    # entregue 18%, e o teto honesto é zero.
    ruim = Negocio(preco_compra=680_000.0, arv_total=30_000.0, meses_carrego=7)
    assert calcular_mao(IMOVEL, ruim, PREMISSAS) == 0.0


def test_matriz_cobre_de_tres_a_quinze_meses() -> None:
    # Uma coluna por mês: prazo de obra mais venda raramente fecha em dois
    # meses, e quinze já é o cenário pessimista longo.
    assert MESES_CENARIO == tuple(range(3, 16))
    celulas = matriz_sensibilidade(IMOVEL, NEGOCIO, PREMISSAS)
    assert len(celulas) == len(VARIACOES_VENDA) * len(MESES_CENARIO)


def test_carrego_fora_da_faixa_vira_coluna_extra() -> None:
    # Sem isso o cenário base não teria célula, e a tela mostraria uma matriz
    # que não contém o próprio estudo.
    negocio = Negocio(preco_compra=680_000.0, arv_total=1_080_000.0, meses_carrego=20)
    meses = {c.meses for c in matriz_sensibilidade(IMOVEL, negocio, PREMISSAS)}
    assert meses == set(MESES_CENARIO) | {20}


def test_carrego_dentro_da_faixa_nao_duplica_coluna() -> None:
    meses = [c.meses for c in matriz_sensibilidade(IMOVEL, NEGOCIO, PREMISSAS) if c.variacao_venda == 0.0]
    assert meses == sorted(set(meses))


def test_matriz_cobre_todas_as_combinacoes() -> None:
    celulas = matriz_sensibilidade(IMOVEL, NEGOCIO, PREMISSAS)
    assert {(c.variacao_venda, c.meses) for c in celulas} == {
        (variacao, meses) for variacao in VARIACOES_VENDA for meses in MESES_CENARIO
    }


def test_celula_central_bate_com_o_cenario_base() -> None:
    # Divergência aqui significa que a matriz e o DRE discordam — o erro mais
    # caro possível, porque a tela mostraria dois números para a mesma conta.
    base = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    central = next(
        c
        for c in matriz_sensibilidade(IMOVEL, NEGOCIO, PREMISSAS)
        if c.variacao_venda == 0.0 and c.meses == NEGOCIO.meses_carrego
    )
    assert central.roi == pytest.approx(base.roi)
    assert central.lucro_liquido == pytest.approx(base.lucro_liquido)
    assert central.venda == pytest.approx(NEGOCIO.arv_total)


def test_venda_menor_e_prazo_maior_pioram_o_roi() -> None:
    celulas = {
        (c.variacao_venda, c.meses): c.roi
        for c in matriz_sensibilidade(IMOVEL, NEGOCIO, PREMISSAS)
    }
    assert celulas[(-0.05, 15)] < celulas[(0.0, 7)] < celulas[(0.05, 3)]


def test_simular_devolve_orcamento_dre_mao_e_matriz_coerentes() -> None:
    simulacao = simular(IMOVEL, NEGOCIO, PREMISSAS)
    assert simulacao.orcamento.total == pytest.approx(41_572.5)
    assert simulacao.dre.lucro_liquido == pytest.approx(227_503.375)
    assert simulacao.dre.obra == pytest.approx(simulacao.orcamento.total)
    assert simulacao.mao == pytest.approx(calcular_mao(IMOVEL, NEGOCIO, PREMISSAS))
    assert len(simulacao.matriz) == len(VARIACOES_VENDA) * len(MESES_CENARIO)


def test_venda_breakeven_zera_o_lucro() -> None:
    # É o número que vai para a negociação: abaixo dele a operação dá prejuízo.
    venda = venda_breakeven(IMOVEL, NEGOCIO, PREMISSAS)
    dre = calcular_dre(
        IMOVEL, Negocio(NEGOCIO.preco_compra, venda, NEGOCIO.meses_carrego), PREMISSAS
    )
    assert dre.lucro_liquido == pytest.approx(0.0, abs=0.5)


def test_breakeven_fica_abaixo_da_venda_projetada_quando_ha_lucro() -> None:
    assert venda_breakeven(IMOVEL, NEGOCIO, PREMISSAS) < NEGOCIO.arv_total


def test_breakeven_sobe_com_obra_mais_cara() -> None:
    caro = Imovel(
        area_seca_m2=92.0,
        banheiros=2,
        cozinhas=1,
        portas=6,
        eletrica_completa=True,
        hidraulica_completa_banheiro=True,
        hidraulica_completa_cozinha=True,
    )
    assert venda_breakeven(caro, NEGOCIO, PREMISSAS) > venda_breakeven(IMOVEL, NEGOCIO, PREMISSAS)


def test_prazo_limite_e_o_ultimo_mes_que_ainda_cumpre_a_meta() -> None:
    # Margem apertada: o carrego come o retorno dentro do horizonte de busca.
    negocio = Negocio(preco_compra=755_000.0, arv_total=1_080_000.0, meses_carrego=7)
    limite = prazo_limite(IMOVEL, negocio, PREMISSAS)
    assert limite is not None and limite < PRAZO_MAXIMO_BUSCA
    no_limite = calcular_dre(IMOVEL, Negocio(negocio.preco_compra, negocio.arv_total, limite), PREMISSAS)
    depois = calcular_dre(
        IMOVEL, Negocio(negocio.preco_compra, negocio.arv_total, limite + 1), PREMISSAS
    )
    assert no_limite.roi >= PREMISSAS.valor("roi_alvo_mao")
    assert depois.roi < PREMISSAS.valor("roi_alvo_mao")


def test_prazo_limite_satura_no_horizonte_quando_nada_fura() -> None:
    # Negócio folgado: nem cinco anos de carrego derrubam a meta. A tela lê o
    # teto como "aguenta mais que o horizonte", e não como uma data real.
    assert prazo_limite(IMOVEL, NEGOCIO, PREMISSAS) == PRAZO_MAXIMO_BUSCA


def test_prazo_limite_e_nulo_quando_nem_o_prazo_minimo_cumpre() -> None:
    # Comprou caro demais: nenhum prazo salva, e a tela precisa dizer isso em
    # vez de mostrar um mês que não existe.
    ruim = Negocio(preco_compra=850_000.0, arv_total=1_080_000.0, meses_carrego=7)
    assert prazo_limite(IMOVEL, ruim, PREMISSAS) is None


def test_simular_traz_breakeven_prazo_limite_e_roi_alvo() -> None:
    simulacao = simular(IMOVEL, NEGOCIO, PREMISSAS)
    assert simulacao.venda_breakeven == pytest.approx(venda_breakeven(IMOVEL, NEGOCIO, PREMISSAS))
    assert simulacao.prazo_limite == prazo_limite(IMOVEL, NEGOCIO, PREMISSAS)
    assert simulacao.roi_alvo == PREMISSAS.valor("roi_alvo_mao")
