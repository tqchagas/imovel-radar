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


class FlipStudyIn(FlipEntradaIn):
    """Um estudo salvo: a entrada do cálculo mais a identidade do imóvel."""

    apelido: str | None = None
    endereco: str
    bairro: str | None = None
    cidade: str = "belo_horizonte"
    area_util_m2: float = Field(gt=0)
    quartos: int = Field(ge=0, default=2)
    status: str = "em_analise"
    origem: str = "manual"
    origem_id: int | None = None


class FlipStudyPatch(BaseModel):
    apelido: str | None = None
    endereco: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    area_util_m2: float | None = Field(default=None, gt=0)
    area_seca_m2: float | None = Field(default=None, gt=0)
    quartos: int | None = Field(default=None, ge=0)
    banheiros: int | None = Field(default=None, ge=0)
    cozinhas: int | None = Field(default=None, ge=0)
    portas: int | None = Field(default=None, ge=0)
    preco_compra: float | None = Field(default=None, gt=0)
    arv_total: float | None = Field(default=None, gt=0)
    meses_carrego: int | None = Field(default=None, ge=0)
    eletrica_completa: bool | None = None
    hidraulica_completa_banheiro: bool | None = None
    hidraulica_completa_cozinha: bool | None = None
    status: str | None = None
    # Não é campo do estudo: é a ordem de refazer o snapshot com os preços de
    # hoje. Fica fora do `setattr` em `editar`.
    atualizar_premissas: bool = False


class FlipStudyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    apelido: str | None
    endereco: str
    bairro: str | None
    cidade: str
    area_util_m2: float
    area_seca_m2: float
    quartos: int
    banheiros: int
    cozinhas: int
    portas: int
    preco_compra: float
    arv_total: float
    meses_carrego: int
    eletrica_completa: bool
    hidraulica_completa_banheiro: bool
    hidraulica_completa_cozinha: bool
    status: str
    origem: str
    origem_id: int | None
    simulacao: SimulacaoOut


class FlipStudyListItem(BaseModel):
    """A linha do pipeline: identidade mais os indicadores recalculados."""

    id: int
    apelido: str | None
    endereco: str
    bairro: str | None
    status: str
    area_util_m2: float
    preco_compra: float
    arv_total: float
    meses_carrego: int
    obra_total: float
    capital_empatado: float
    lucro_liquido: float
    roi: float
    tir_anual: float
    mao: float
