from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistryAddress(Base):
    """Um endereço do cadastro imobiliário municipal, com a coordenada do lote.

    A prefeitura publica o cadastro tributário georreferenciado, unidade a
    unidade. Aqui ele é agregado por endereço e tipo construtivo, que é a
    granularidade em que a escada de referência pergunta: "quais vendas de ITBI
    aconteceram neste prédio".

    Serve a duas coisas que nenhuma outra fonte resolve. O anúncio da Loft e do
    QuintoAndar traz a rua e não traz o número, mas traz a coordenada — e daqui
    sai o número. E a área construída por unidade vem do mesmo cadastro que
    alimenta o ITBI, então a conversão entre a área do cartório e a área
    anunciada deixa de ser um fator único da cidade inteira.
    """

    __tablename__ = "registry_addresses"
    __table_args__ = (
        UniqueConstraint(
            "city",
            "street_key",
            "number_key",
            "construction_type",
            name="uq_registry_addresses_endereco",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city: Mapped[str] = mapped_column(String(100), index=True)
    street: Mapped[str] = mapped_column(String(300))
    street_number: Mapped[str] = mapped_column(String(30))
    # Chaves de junção: `street_key` já vem com o tipo do logradouro por
    # extenso, que é a forma que casa com o portal e com o ITBI.
    street_key: Mapped[str] = mapped_column(String(300), index=True)
    number_key: Mapped[str] = mapped_column(String(30))
    postal_code: Mapped[str | None] = mapped_column(String(9), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Mesmo vocabulário do ITBI: AP, CA, LJ.
    construction_type: Mapped[str] = mapped_column(String(10), index=True)
    occupation_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Padrão de acabamento predominante entre as unidades do endereço.
    finish_standard: Mapped[str | None] = mapped_column(String(10), nullable=True)
    units_count: Mapped[int] = mapped_column(Integer, default=0)
    median_unit_area: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # Espalhamento interquartil das áreas das unidades, sobre a mediana. É o
    # que diz se a janela de área tem o que separar dentro deste prédio.
    unit_area_dispersion: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    # Onze decis das áreas das unidades. Onde o prédio é heterogêneo, é o que
    # diz qual unidade o anúncio é — o casamento por posto. A mediana sozinha
    # não separa a cobertura do quarto e sala.
    unit_area_profile: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True, index=True)
    lon: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True, index=True)
    # Data da extração publicada pela prefeitura, não a data em que rodamos.
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
