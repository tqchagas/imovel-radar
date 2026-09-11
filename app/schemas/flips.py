from pydantic import BaseModel, ConfigDict, Field


class FlipEntradaIn(BaseModel):
    """O que a tela manda a cada mexida de campo."""

    area_seca_m2: float = Field(gt=0)
    banheiros: int = Field(ge=0, default=1)
    cozinhas: int = Field(ge=0, default=1)
    portas: int = Field(ge=0, default=0)
    eletrica_completa: bool = False
    hidraulica_completa_banheiro: bool = False
    hidraulica_completa_cozinha: bool = False
    preco_compra: float = Field(gt=0)
    arv_total: float = Field(gt=0)
    meses_carrego: int = Field(ge=0, default=7)


class ItemOrcamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chave: str
    rotulo: str
    quantidade: float
    custo_unitario: float
    total: float


class GrupoOrcamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chave: str
    rotulo: str
    itens: list[ItemOrcamentoOut]
    total: float


class OrcamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grupos: list[GrupoOrcamentoOut]
    subtotal: float
    contingencia: float
    total: float


class DREOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class CenarioMatrizOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variacao_venda: float
    meses: int
    venda: float
    lucro_liquido: float
    roi: float


class SimulacaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orcamento: OrcamentoOut
    dre: DREOut
    mao: float
    matriz: list[CenarioMatrizOut]


class PremissaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chave: str
    rotulo: str
    unidade: str
    valor: float
