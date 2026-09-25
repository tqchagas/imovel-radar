from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuantidadesObra(BaseModel):
    pintura_paredes_m2: float = Field(default=0, ge=0)
    pintura_teto_m2: float = Field(default=0, ge=0)
    massa_paredes_m2: float = Field(default=0, ge=0)
    impermeabilizacao_m2: float = Field(default=0, ge=0)
    piso_banheiro_m2: float = Field(default=0, ge=0)
    piso_banheiros_medidos: int = Field(default=0, ge=0)
    piso_cozinha_m2: float = Field(default=0, ge=0)
    piso_cozinhas_medidas: int = Field(default=0, ge=0)
    cabo_eletrico_m: float = Field(default=0, ge=0)
    rasgo_eletrico_m: float = Field(default=0, ge=0)
    tubo_agua_m: float = Field(default=0, ge=0)
    rasgo_hidraulico_m: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def piso_banheiro_completo(self):
        if bool(self.piso_banheiro_m2) != bool(self.piso_banheiros_medidos):
            raise ValueError("Informe a área e quantos banheiros foram medidos juntos")
        if bool(self.piso_cozinha_m2) != bool(self.piso_cozinhas_medidas):
            raise ValueError("Informe a área e quantas cozinhas foram medidas juntas")
        return self


class FlipEntradaIn(BaseModel):
    """O que a tela manda a cada mexida de campo."""

    area_seca_m2: float = Field(gt=0)
    banheiros: int = Field(ge=0, default=1)
    cozinhas: int = Field(ge=0, default=1)
    portas: int = Field(ge=0, default=0)
    incluir_marcenaria: bool = True
    eletrica_completa: bool = False
    hidraulica_completa_banheiro: bool = False
    hidraulica_completa_cozinha: bool = False
    escopo_obra: Literal["legado", "retoques", "revenda", "retrofit"] = "legado"
    quantidades: QuantidadesObra = Field(default_factory=QuantidadesObra)
    preco_compra: float = Field(gt=0)
    arv_total: float = Field(gt=0)
    meses_carrego: int = Field(ge=0, default=7)

    @model_validator(mode="after")
    def conferir_banheiros_medidos(self):
        if self.quantidades.piso_banheiros_medidos > self.banheiros:
            raise ValueError("Banheiros medidos não podem exceder o total de banheiros")
        if self.quantidades.piso_cozinhas_medidas > self.cozinhas:
            raise ValueError("Cozinhas medidas não podem exceder o total de cozinhas")
        return self


class ItemOrcamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chave: str
    rotulo: str
    quantidade: float
    custo_unitario: float
    total: float
    unidade: str
    fonte: str


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
    venda_breakeven: float
    prazo_limite: int | None
    roi_alvo: float
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
    incluir_marcenaria: bool | None = None
    preco_compra: float | None = Field(default=None, gt=0)
    arv_total: float | None = Field(default=None, gt=0)
    meses_carrego: int | None = Field(default=None, ge=0)
    eletrica_completa: bool | None = None
    hidraulica_completa_banheiro: bool | None = None
    hidraulica_completa_cozinha: bool | None = None
    escopo_obra: Literal["legado", "retoques", "revenda", "retrofit"] | None = None
    quantidades: QuantidadesObra | None = None
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
    incluir_marcenaria: bool
    preco_compra: float
    arv_total: float
    meses_carrego: int
    eletrica_completa: bool
    hidraulica_completa_banheiro: bool
    hidraulica_completa_cozinha: bool
    escopo_obra: str
    quantidades: QuantidadesObra
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
