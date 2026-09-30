from datetime import datetime

from pydantic import BaseModel


class FlipOpportunityOut(BaseModel):
    source: str
    listing_id: str
    url: str
    tipo_imovel: str
    bairro: str
    rua: str | None
    area_util_m2: float
    quartos: int | None
    vagas: int
    condominio: float | None
    preco_pedido: float
    preco_m2_anuncio: float
    preco_m2_bairro: float
    gap_pct: float
    status: str
    faixa_area: str
    comparaveis_count: int
    pagina_verificada_em: datetime
    anuncio_atualizado_em: datetime


class FlipOpportunityListOut(BaseModel):
    cidade: str
    total: int
    minimo_comparaveis: int
    bairros_prioritarios: list[str]
    bairros_complementares: list[str]
    items: list[FlipOpportunityOut]
