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


class PortalBuilding(Base):
    """Um prédio como o portal o publica, com o número da rua.

    O cadastro da prefeitura (`registry_addresses`) sabe o que existe; esta
    tabela sabe o que o portal chama de prédio — e é ela que liga um anúncio
    sem número a um endereço. As duas se encontram por rua + número.

    Medido em 59 páginas de Belo Horizonte sorteadas do sitemap: 83% casam com
    o cadastro por rua+número, o ponto publicado fica a 8 m (mediana) do lote
    do cadastro, e a 1 m do anúncio do próprio portal. É uma ordem de grandeza
    mais perto do que a resolução por proximidade de lote consegue, porque as
    duas pontas saem da mesma fonte.
    """

    __tablename__ = "portal_buildings"
    __table_args__ = (
        UniqueConstraint(
            "source", "external_id", name="uq_portal_buildings_source_external"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    external_id: Mapped[str] = mapped_column(String(50))
    slug: Mapped[str | None] = mapped_column(String(300), nullable=True)
    url: Mapped[str] = mapped_column(String(1000))
    city: Mapped[str] = mapped_column(String(100), index=True)
    street: Mapped[str | None] = mapped_column(String(300), nullable=True)
    street_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Chaves de junção, na mesma forma que o cadastro e o ITBI usam.
    street_key: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    number_key: Mapped[str | None] = mapped_column(String(30), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(9), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True, index=True)
    lon: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True, index=True)
    # A faixa de área das unidades que o portal conhece naquele prédio. É outra
    # leitura do formato, em área anunciada, ao lado da do cadastro em área
    # construída.
    min_area: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_area: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    min_bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Só as instalações presentes. O padrão de acabamento do cadastro responde
    # a mesma pergunta pelo lado da prefeitura, e ganha quando existe.
    installations: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    doorman: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # A data que o próprio sitemap declara, que é o que torna a recoleta
    # incremental — e não a data em que rodamos.
    source_lastmod: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
