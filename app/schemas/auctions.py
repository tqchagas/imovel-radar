from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AuctionAppraisalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    consultado_em: datetime | None = None
    preco_qpreco: float | None = None
    preco_rapido: float | None = None
    preco_devagar: float | None = None
    limite_inferior: float | None = None
    limite_superior: float | None = None
    certeza: str | None = None
    preco_vendidos: float | None = None
    comparaveis_usados: int = 0
    divergencia_pct: float | None = None
    atipico: bool = False
    preco_itbi: float | None = None
    itbi_tier: str | None = None
    itbi_amostra: int | None = None
    # Mesmo nome do modelo: o FastAPI serializa por alias, e um alias aqui
    # faria a tela procurar uma chave que a resposta não tem.
    comparaveis_json: list[dict] | None = None
    erro: str | None = None


class AuctionPropertyIn(BaseModel):
    """O que o dono digita. A área é a **útil**, que é o que o modelo lê."""

    apelido: str | None = None
    address: str
    address_number: str | None = None
    neighborhood: str | None = None
    city: str
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    house_type: str = "APARTMENT"
    total_area: float = Field(gt=0)
    bedroom_count: int = 2
    bathroom_count: int = 1
    suites_count: int = 0
    parking_slots: int = 0
    floor: int | None = None
    condominium_per_month: float = 0
    iptu_per_year: float = 0
    data_leilao: date | None = None
    lance_minimo: float | None = None
    edital_url: str | None = None
    observacao: str | None = None


class AuctionPropertyPatch(BaseModel):
    apelido: str | None = None
    address: str | None = None
    address_number: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    house_type: str | None = None
    total_area: float | None = None
    bedroom_count: int | None = None
    bathroom_count: int | None = None
    suites_count: int | None = None
    parking_slots: int | None = None
    floor: int | None = None
    condominium_per_month: float | None = None
    iptu_per_year: float | None = None
    data_leilao: date | None = None
    lance_minimo: float | None = None
    edital_url: str | None = None
    observacao: str | None = None


class AuctionPropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    apelido: str | None = None
    address: str
    address_number: str | None = None
    neighborhood: str | None = None
    city: str
    state: str | None = None
    latitude: float
    longitude: float
    coordenada_fonte: str | None = None
    coordenada_rotulo: str | None = None
    house_type: str
    total_area: float
    bedroom_count: int
    bathroom_count: int
    suites_count: int
    parking_slots: int
    floor: int | None = None
    condominium_per_month: float
    iptu_per_year: float
    data_leilao: date | None = None
    lance_minimo: float | None = None
    edital_url: str | None = None
    observacao: str | None = None
    avaliacao: AuctionAppraisalOut | None = None


class CoordinateSuggestionOut(BaseModel):
    latitude: float
    longitude: float
    fonte: str
    rotulo: str
