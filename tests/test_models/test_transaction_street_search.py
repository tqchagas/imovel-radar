"""A coluna normalizada tem que nascer preenchida, venha de onde vier a linha."""

from datetime import date

from app.ingestion.base import ParsedTransaction
from app.models.transaction import Transaction


def _campos_obrigatorios() -> dict:
    return dict(
        city="belo_horizonte",
        source_row_hash="hash-x",
        raw_address="AVE AUGUSTO DE LIMA 100 - CENTRO",
        street_number="100",
        complement=None,
        postal_code=None,
        neighborhood="CENTRO",
        construction_year=None,
        land_area=None,
        built_area_acquired=None,
        acquired_area_total=None,
        finish_standard=None,
        acquired_fraction=None,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        declared_value=1.0,
        calc_base_value=1.0,
        zoning=None,
        settlement_date=date(2026, 1, 1),
    )


def test_orm_preenche_street_search():
    tx = Transaction(street="AVE AUGUSTO DE LIMA", **_campos_obrigatorios())
    assert tx.street_search == "avenida augusto de lima"


def test_linha_da_ingestao_ja_traz_street_search():
    # A ingestão insere pelo Core (`insert(Transaction), chunk`), que não passa
    # pelo ORM: o valor precisa vir pronto no dicionário.
    parsed = ParsedTransaction(street="Rua José Bonifácio", **_campos_obrigatorios())
    assert parsed.__dict__["street_search"] == "rua jose bonifacio"
