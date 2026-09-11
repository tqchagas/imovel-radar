"""Viabilidade de um flip: quanto custa a obra, o que sobra na venda, e até
quanto dá para pagar pelo imóvel.

O módulo é puro — recebe as entradas e as premissas, devolve números. Quem fala
com banco é `app/services/flip_studies.py`, e quem formata é a tela.
"""

from dataclasses import dataclass

from app.domain.flip_premissas import Premissas


@dataclass(frozen=True)
class Imovel:
    """A composição que determina o orçamento.

    `area_seca_m2` é digitada, e não derivada da área útil: banheiro e cozinha
    são orçados por unidade, então dividir a área útil exigiria inventar uma
    premissa de quantos m² cada um ocupa.
    """

    area_seca_m2: float
    banheiros: int
    cozinhas: int = 1
    portas: int = 0
    eletrica_completa: bool = False
    hidraulica_completa_banheiro: bool = False
    hidraulica_completa_cozinha: bool = False


@dataclass(frozen=True)
class ItemOrcamento:
    chave: str
    rotulo: str
    quantidade: float
    custo_unitario: float
    total: float


@dataclass(frozen=True)
class GrupoOrcamento:
    chave: str
    rotulo: str
    itens: tuple[ItemOrcamento, ...]
    total: float


@dataclass(frozen=True)
class Orcamento:
    grupos: tuple[GrupoOrcamento, ...]
    subtotal: float
    contingencia: float
    total: float


ITENS_BANHEIRO = (
    "banho_piso",
    "banho_azulejo_box",
    "banho_massa_acrilica",
    "banho_bancada",
    "banho_louca",
    "banho_box_espelho",
    "banho_mao_obra",
    "banho_marcenaria",
)

ITENS_COZINHA = (
    "coz_piso",
    "coz_azulejo",
    "coz_massa_acrilica",
    "coz_bancada",
    "coz_mao_obra",
    "coz_marcenaria",
)


def _item(premissas: Premissas, chave: str, quantidade: float) -> ItemOrcamento:
    unitario = premissas.valor(chave)
    rotulo = next(item.rotulo for item in premissas.itens if item.chave == chave)
    return ItemOrcamento(
        chave=chave,
        rotulo=rotulo,
        quantidade=quantidade,
        custo_unitario=unitario,
        total=unitario * quantidade,
    )


def _grupo(chave: str, rotulo: str, itens: tuple[ItemOrcamento, ...]) -> GrupoOrcamento:
    # Item zerado sai da lista: a tela não deve mostrar "0 × R$ 200".
    vivos = tuple(item for item in itens if item.quantidade > 0)
    return GrupoOrcamento(
        chave=chave,
        rotulo=rotulo,
        itens=vivos,
        total=sum(item.total for item in vivos),
    )


def orcar(imovel: Imovel, premissas: Premissas) -> Orcamento:
    area = max(imovel.area_seca_m2, 0.0)
    secas = _grupo(
        "areas_secas",
        "Áreas secas",
        (
            _item(premissas, "taco", area * premissas.valor("proporcao_taco")),
            _item(premissas, "pintura_seca", area),
        ),
    )
    banheiros = _grupo(
        "banheiros",
        "Banheiros",
        tuple(_item(premissas, chave, imovel.banheiros) for chave in ITENS_BANHEIRO),
    )
    cozinha = _grupo(
        "cozinha",
        "Cozinha e área de serviço",
        tuple(_item(premissas, chave, imovel.cozinhas) for chave in ITENS_COZINHA),
    )
    geral = _grupo(
        "geral",
        "Infraestrutura e serviços gerais",
        (
            _item(premissas, "eletrica_led", 1),
            _item(premissas, "portas", imovel.portas),
            _item(premissas, "cacamba", 1),
        ),
    )
    retrofit = _grupo(
        "retrofit",
        "Retrofit de infraestrutura",
        (
            _item(premissas, "eletrica_completa", 1 if imovel.eletrica_completa else 0),
            _item(
                premissas,
                "hidraulica_completa_banheiro",
                imovel.banheiros if imovel.hidraulica_completa_banheiro else 0,
            ),
            _item(
                premissas,
                "hidraulica_completa_cozinha",
                imovel.cozinhas if imovel.hidraulica_completa_cozinha else 0,
            ),
        ),
    )

    grupos = (secas, banheiros, cozinha, geral, retrofit)
    subtotal = sum(grupo.total for grupo in grupos)
    contingencia = subtotal * premissas.valor("contingencia_pct")
    return Orcamento(
        grupos=grupos,
        subtotal=subtotal,
        contingencia=contingencia,
        total=subtotal + contingencia,
    )


@dataclass(frozen=True)
class Negocio:
    preco_compra: float
    arv_total: float
    meses_carrego: int


@dataclass(frozen=True)
class DRE:
    venda: float
    corretagem: float
    ganho_capital: float
    ir_ganho_capital: float
    preco_compra: float
    itbi: float
    registro: float
    obra: float
    carrego: float
    lucro_liquido: float
    capital_empatado: float
    roi: float
    tir_anual: float


def calcular_dre(
    imovel: Imovel,
    negocio: Negocio,
    premissas: Premissas,
    obra_total: float | None = None,
) -> DRE:
    """O resultado da operação inteira, do sinal à escritura de venda.

    `obra_total` existe para a matriz de sensibilidade, que varia venda e prazo
    nove vezes sobre o mesmo orçamento — reorçar a cada célula daria o mesmo
    número nove vezes.
    """
    obra = orcar(imovel, premissas).total if obra_total is None else obra_total
    compra = negocio.preco_compra
    itbi = compra * premissas.valor("itbi_pct")
    registro = compra * premissas.valor("registro_pct")
    mensal = (
        premissas.valor("condominio_mensal")
        + premissas.valor("iptu_mensal")
        + premissas.valor("consumo_mensal")
    )
    carrego = mensal * max(negocio.meses_carrego, 0)

    venda = negocio.arv_total
    corretagem = venda * premissas.valor("corretagem_pct")
    # Benfeitoria comprovada entra no custo de aquisição para efeito de ganho de
    # capital; é por isso que a obra aparece aqui e de novo no lucro.
    ganho = venda - corretagem - (compra + itbi + registro + obra)
    ir = max(ganho, 0.0) * premissas.valor("ir_ganho_capital_pct")

    lucro = venda - corretagem - ir - compra - itbi - registro - obra - carrego
    capital = compra + itbi + registro + obra + carrego
    roi = lucro / capital if capital > 0 else 0.0
    meses = max(negocio.meses_carrego, 0)
    # (1 + ROI) elevado a fração estoura com ROI ≤ −100%; abaixo disso o capital
    # virou pó e anualizar não significa nada.
    if meses == 0 or roi <= -1.0:
        tir = roi
    else:
        tir = (1.0 + roi) ** (12.0 / meses) - 1.0

    return DRE(
        venda=venda,
        corretagem=corretagem,
        ganho_capital=ganho,
        ir_ganho_capital=ir,
        preco_compra=compra,
        itbi=itbi,
        registro=registro,
        obra=obra,
        carrego=carrego,
        lucro_liquido=lucro,
        capital_empatado=capital,
        roi=roi,
        tir_anual=tir,
    )


def calcular_mao(
    imovel: Imovel,
    negocio: Negocio,
    premissas: Premissas,
    roi_alvo: float | None = None,
) -> float:
    """O maior preço de compra que ainda entrega o ROI alvo.

    Bisseção, e não fórmula fechada: o IR é `max(ganho, 0)`, e esse joelho
    quebra a linearidade em preço. O ROI cai monotonicamente conforme o preço
    sobe, então a busca converge sempre.
    """
    alvo = premissas.valor("roi_alvo_mao") if roi_alvo is None else roi_alvo
    obra = orcar(imovel, premissas).total

    def roi_de(preco: float) -> float:
        return calcular_dre(
            imovel,
            Negocio(preco, negocio.arv_total, negocio.meses_carrego),
            premissas,
            obra_total=obra,
        ).roi

    # Comprar de graça é o cenário mais generoso possível. Se nem ele bate o
    # alvo, o negócio não fecha a nenhum preço.
    if roi_de(0.0) < alvo:
        return 0.0

    baixo, alto = 0.0, max(negocio.arv_total, negocio.preco_compra) * 2.0
    if roi_de(alto) >= alvo:
        return alto
    for _ in range(80):
        meio = (baixo + alto) / 2.0
        if roi_de(meio) >= alvo:
            baixo = meio
        else:
            alto = meio
    return baixo
