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
