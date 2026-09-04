from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AuctionProperty(Base):
    """Um imóvel de leilão que o dono digitou à mão.

    Nada aqui vem de coleta: o edital é lido por gente, e é gente quem confere
    a área e a coordenada. A área é a **útil**, que é o que a Calculadora
    QPreço lê — o edital costuma trazer a de matrícula, e converter uma na
    outra é justamente o erro que este projeto já mediu valer até 2,1x.
    """

    __tablename__ = "auction_properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    apelido: Mapped[str | None] = mapped_column(String(150), nullable=True)

    address: Mapped[str] = mapped_column(String(300))
    address_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city: Mapped[str] = mapped_column(String(150), index=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # A coordenada é o campo mais sensível que existe aqui: medido, seis metros
    # de diferença moveram a estimativa em 18,4%, de forma determinística. Por
    # isso ela é gravada junto da fonte — quem confia nela precisa saber de onde
    # ela veio.
    latitude: Mapped[float] = mapped_column(Numeric(9, 6))
    longitude: Mapped[float] = mapped_column(Numeric(9, 6))
    coordenada_fonte: Mapped[str | None] = mapped_column(String(50), nullable=True)

    house_type: Mapped[str] = mapped_column(String(20), default="APARTMENT")
    total_area: Mapped[float] = mapped_column(Numeric(10, 2))
    bedroom_count: Mapped[int] = mapped_column(Integer, default=2)
    bathroom_count: Mapped[int] = mapped_column(Integer, default=1)
    suites_count: Mapped[int] = mapped_column(Integer, default=0)
    parking_slots: Mapped[int] = mapped_column(Integer, default=0)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condominium_per_month: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    iptu_per_year: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    # O que é do leilão e não do imóvel. Entra na calculadora de lance do dono,
    # que vive fora deste projeto — aqui é só registro.
    data_leilao: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    lance_minimo: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    edital_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    avaliacoes: Mapped[list["AuctionAppraisal"]] = relationship(
        back_populates="imovel",
        cascade="all, delete-orphan",
        order_by="AuctionAppraisal.consultado_em.desc()",
    )


class AuctionAppraisal(Base):
    """Uma consulta ao portal, guardada com data.

    É tabela à parte, e não colunas na primeira, porque o dono reconsulta antes
    do leilão e o valor está em ver o número se mover — uma coluna sobrescrita
    apagaria exatamente isso.
    """

    __tablename__ = "auction_appraisals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auction_property_id: Mapped[int] = mapped_column(
        ForeignKey("auction_properties.id", ondelete="CASCADE"), index=True
    )
    consultado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # A leitura do modelo do portal.
    preco_qpreco: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Os três preços que o portal publica são o mesmo trio, com dois nomes:
    # `dealObjectiveRanges` chama de FASTER/REGULAR/SLOWER exatamente os valores
    # que ele também devolve como lower/suggested/upper bound — conferido em três
    # imóveis. Então "vender rápido" é o piso e "vender devagar" é o teto, e não
    # uma faixa de incerteza.
    preco_rapido: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    preco_devagar: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Os extremos do modelo (p10 e p90), fora da faixa que ele recomenda pedir.
    limite_inferior: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    limite_superior: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # "low", "medium" ou "high", como o portal declara. Volta "low" com
    # frequência, inclusive em bairro denso — é informação, não erro.
    certeza: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # A leitura das vendas reais do entorno.
    preco_vendidos: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    comparaveis_usados: Mapped[int] = mapped_column(Integer, default=0)
    divergencia_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    atipico: Mapped[bool] = mapped_column(Boolean, default=False)

    # A terceira leitura, só onde há ITBI carregado.
    preco_itbi: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    itbi_tier: Mapped[str | None] = mapped_column(String(30), nullable=True)
    itbi_amostra: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Os comparáveis crus, para auditoria: quem desconfia do número tem de
    # poder ver de onde cada real veio.
    comparaveis_json: Mapped[list | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    erro: Mapped[str | None] = mapped_column(String(300), nullable=True)

    imovel: Mapped["AuctionProperty"] = relationship(back_populates="avaliacoes")
