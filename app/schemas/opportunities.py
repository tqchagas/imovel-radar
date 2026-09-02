from datetime import date, datetime

from pydantic import BaseModel


class OpportunityOut(BaseModel):
    id: int
    source: str
    listing_id: str
    url: str | None
    cidade: str | None
    bairro: str | None
    rua: str | None
    numero: str | None
    tipo_imovel: str | None
    quartos: int | None
    banheiros: int | None
    vagas: int | None
    area_util_m2: float | None
    preco_anunciado: float | None
    preco_estimado: float | None
    desconto_pct: float | None
    desconto_reais: float | None
    tipo_referencia: str | None
    amostra_count: int | None
    nota: int | None
    nota_itbi: int | None = None
    nota_qpreco: int | None = None
    qpreco_estimado: float | None = None
    qpreco_desconto_pct: float | None = None
    dispersao_relativa: float | None
    fator_calibracao: float | None
    referencia_data_inicio: date | None
    referencia_data_fim: date | None
    confianca: str | None
    motivos: list[str]
    anunciado_em: datetime | None = None
    condominio: float | None = None
    iptu: float | None = None
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class OpportunitySummaryOut(BaseModel):
    total: int
    max_desconto_pct: float | None
    max_nota: int | None
    last_collected_at: datetime | None
    reference_date: date | None


class OpportunityListOut(BaseModel):
    city: str | None
    total: int
    page: int
    page_size: int
    summary: OpportunitySummaryOut
    items: list[OpportunityOut]
