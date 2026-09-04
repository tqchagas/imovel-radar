# Acurácia da área Implementation Plan

> **Estado em 2026-09-04, depois da execução.**
>
> | fase | estado |
> | --- | --- |
> | A — campos livres do QuintoAndar (Tarefa 1) | **feita** |
> | B — perfil de área no cadastro (Tarefa 2) | **feita** |
> | C — diretório de condomínios (Tarefas 3-6) | **feita** |
> | D — área de referência (Tarefas 7-9) | **feita, medida e revertida** |
> | E — recalibrar (Tarefa 10) | **feita**: o dado mandou reverter a Fase D e manter `AREA_BANDS` |
> | F — qualidade do prédio (Tarefa 11) | **não feita**, ver abaixo |
> | docs e scheduler (Tarefa 12) | **feita** |
>
> A Fase D piora o erro em todas as variantes testadas — o relato está no fim de
> `docs/superpowers/specs/2026-09-04-acuracia-area-design.md` e resumido no
> comentário de `AREA_MATCH_FACTOR`. O que sobreviveu dela é
> `registry_addresses.unit_area_profile`.
>
> A Tarefa 11 ficou de fora **de propósito**: ela depende das instalações que o
> diretório de condomínios publica, e o diretório está coletado em uma fração
> dos 19.117 prédios. A própria Tarefa 11 manda reverter se o erro não melhorar,
> e esse critério não é avaliável com a amostra de hoje. Duas medidas rasas já
> enganaram nesta sessão (a seção 4 da especificação, e o erro esperado do
> `endereco_portal`); fazê-la agora seria a terceira. Rode `make condominios`
> por alguns ciclos e então `scripts/validar_calibracao.py` antes de começar.

**Goal:** Tirar a conversão de área do caminho do preço, estimando cada anúncio na área que o cadastro municipal mede, e alcançar o prédio certo pelo `condoId` e pelo diretório de condomínios do QuintoAndar em vez de pela proximidade de lote.

**Architecture:** A escada de referência de ITBI continua igual — muda só qual área a multiplica. Um novo `area_referencia` resolve, por prédio, a área daquele anúncio em espaço de cadastro (mediana do prédio quando homogêneo, casamento por posto quando não), e o fator de calibração passa a ser medido nessa mesma área, o que remove a definição de área do numerador e do denominador. Em paralelo, o `condoId` do QuintoAndar e um diretório público de condomínios entregam o número da rua que os portais não publicam, promovendo Loft e QuintoAndar ao tier de endereço exato.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 (Mapped/mapped_column), Alembic, Postgres 16, pytest, requests.

**Spec:** `docs/superpowers/specs/2026-09-04-acuracia-area-design.md`

## Global Constraints

- Comentários e docstrings novos em **português**, no tom do módulo vizinho: explicam *por que*, com o número medido junto. Nomes de símbolo em inglês onde o módulo já usa inglês (`app/domain/opportunities.py`), em português onde já usa português (`app/ingestion/pbh_registry.py`).
- Cidade coberta: **`belo_horizonte`** apenas. Nada pode assumir outra cidade nem quebrar quando ela chegar.
- Tipo construtivo coberto: **`AP`**. `CA` continua no caminho de hoje.
- Toda migration nova entra em `alembic/versions/` com o prefixo numérico seguinte ao último (`0017_listing_outcomes.py`), `down_revision` apontando para ele.
- Coletores respeitam o piso de ritmo já existente: `min_interval` do `app/core/http_client.request`. O diretório de condomínios usa **1,0 s**.
- `pytest -v` tem de passar inteiro ao fim de cada tarefa. Testes rodam em SQLite e em Postgres, então **nada de tipo só-Postgres sem fallback**: `unit_area_profile` usa `JSON` do SQLAlchemy (`sqlalchemy.JSON`), que vira `jsonb` no Postgres e `TEXT` no SQLite.
- Nenhum segredo, cookie ou credencial nova. O diretório de condomínios responde anonimamente.
- Commits no estilo do repositório (`feat:`, `fix:`, `perf:`, `chore:`, `docs:`), assunto em português, no imperativo.
  ```
  ```

---

## Estrutura de arquivos

**Criar:**
- `app/ingestion/quintoandar_condos.py` — parser puro do sitemap e da página de condomínio. Sem I/O.
- `app/models/portal_building.py` — `PortalBuilding`, o prédio como o portal o publica.
- `app/services/condo_sync.py` — baixa o sitemap e as páginas, grava `portal_buildings`.
- `app/domain/unit_area.py` — resolução de `area_referencia` e casamento por posto. Puro.
- `alembic/versions/0018_condo_fields.py`, `0019_unit_area_profile.py`, `0020_portal_buildings.py`
- `scripts/medir_area_predio.py` — remede o ganho da Tarefa 9 numa cidade nova.
- `tests/test_ingestion/test_quintoandar_condos.py`, `tests/test_services/test_condo_sync.py`, `tests/test_domain/test_unit_area.py`

**Modificar:**
- `app/market_collectors/quintoandar.py` — `FIELDS` e `_parse`
- `app/market_collectors/types.py` — `NormalizedListing`
- `app/market_collectors/normalize.py` — `listing()`
- `app/models/market_comparable.py`, `app/models/registry_address.py`
- `app/services/market_refresh.py` — mapa de colunas
- `app/ingestion/pbh_registry.py` — perfil de decis
- `app/services/registry_sync.py` — coluna no upsert
- `app/domain/buildings.py` — `Building` ganha o perfil
- `app/domain/opportunities.py` — `area_referencia` no lugar de `itbi_area_for`
- `app/services/opportunities.py` — resolução de número por portal, perfil no `ListingInput`
- `app/ingestion/cli.py`, `Makefile`, `README.md`

---

## Fase A — Os campos que o portal já dá de graça

### Task 1: Campos livres da busca do QuintoAndar

**Files:**
- Modify: `app/market_collectors/quintoandar.py:20-42` (`FIELDS`), `:66-104` (`_parse`)
- Modify: `app/market_collectors/types.py:24-53` (`NormalizedListing`)
- Modify: `app/market_collectors/normalize.py:127-155` (`listing`)
- Modify: `app/models/market_comparable.py`
- Modify: `app/services/market_refresh.py:66-95`
- Create: `alembic/versions/0018_condo_fields.py`
- Test: `tests/test_collectors/test_quintoandar.py`

**Interfaces:**
- Consumes: nada.
- Produces: `NormalizedListing.condo_id: str | None`, `NormalizedListing.condo_name: str | None`; colunas `market_comparables.condo_id` (String(50), indexada) e `market_comparables.condo_name` (String(300)); `market_comparables.iptu_value` e `condominium_value` passam a vir preenchidas para o QuintoAndar.

- [ ] **Step 1: Escrever o teste que falha**

Em `tests/test_collectors/test_quintoandar.py`, somar:

```python
def test_collect_captures_condo_and_costs(monkeypatch):
    """condoId identifica o prédio: 998 de 1000 anúncios de BH o trazem, e a
    coordenada dentro de um mesmo condoId não se espalha (p50 0 m, máx 13 m)."""
    payload = {
        "hits": {
            "total": 1,
            "hits": [
                {
                    "_source": {
                        "id": 894942131,
                        "salePrice": 3675000,
                        "area": 271,
                        "address": "Rua Tomé de Souza",
                        "city": "Belo Horizonte",
                        "neighbourhood": "Savassi",
                        "type": "Apartamento",
                        "location": {"lat": -19.9380714, "lon": -43.9293474},
                        "bedrooms": 4,
                        "condoId": 125099,
                        "condoName": "Edifício Montreal",
                        "iptu": 1334,
                        "condominium": 3400,
                    }
                }
            ],
        }
    }
    monkeypatch.setattr(
        "app.market_collectors.quintoandar.request",
        lambda *a, **k: _Response(200, payload),
    )
    result = collect(MarketQuery(uf="MG", cidade="Belo Horizonte", bairro="Savassi"))
    assert result.success
    item = result.listings[0]
    assert item.condo_id == "125099"
    assert item.condo_name == "Edifício Montreal"
    assert item.iptu_value == 1334
    assert item.condominium_value == 3400


def test_fields_ask_for_the_condo_columns():
    """O gateway só devolve o que a lista pede; sem isso a coluna nasce vazia."""
    for campo in ("condoId", "condoName", "iptu", "condominium"):
        assert campo in FIELDS
```

Reaproveitar o `_Response` e os imports que o arquivo já tem; somar `FIELDS` ao import de `app.market_collectors.quintoandar`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_collectors/test_quintoandar.py -v -k condo`
Expected: FAIL — `ImportError: cannot import name 'FIELDS'` ou `AttributeError: 'NormalizedListing' object has no attribute 'condo_id'`.

- [ ] **Step 3: Somar os campos ao pedido do gateway**

Em `app/market_collectors/quintoandar.py`, dentro de `FIELDS`, depois de `"isPrimaryMarket",`:

```python
    # Sondados ao vivo em 1.000 anúncios de BH: condoId vem em 998, condominium
    # em 1.000, iptu em 849, condoName em 272. Nenhuma requisição a mais — o
    # gateway devolve só o que a lista pede, e recusa em silêncio o que não
    # conhece (área discriminada, ano de construção, CEP, andar, datas).
    #
    # condoId é identidade de prédio, não rótulo: agrupando por ele, a
    # coordenada dentro do grupo tem espalhamento mediano de 0 m e máximo de
    # 13 m. É o que faz o anúncio sem número alcançar o prédio sem adivinhar.
    "condoId",
    "condoName",
    "iptu",
    "condominium",
```

- [ ] **Step 4: Levar os campos até o `NormalizedListing`**

Em `app/market_collectors/types.py`, dentro de `NormalizedListing`, logo abaixo de `iptu_value`:

```python
    # Identidade do prédio como o portal a publica. Só o QuintoAndar tem uma;
    # Loft e VivaReal chegam ao prédio pela coordenada.
    condo_id: str | None = None
    condo_name: str | None = None
```

Em `app/market_collectors/normalize.py`, dentro do `return NormalizedListing(...)` de `listing()`, antes de `raw=`:

```python
        condo_id=clean_text(values.get("condo_id")),
        condo_name=clean_text(values.get("condo_name")),
```

Em `app/market_collectors/quintoandar.py`, dentro da chamada `listing(...)` de `_parse`, antes de `coordinate_source=`:

```python
        condo_id=row.get("condoId"),
        condo_name=row.get("condoName"),
        iptu_value=row.get("iptu"),
        condominium_value=row.get("condominium"),
```

- [ ] **Step 5: Rodar o teste de coletor**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_collectors/test_quintoandar.py -v`
Expected: PASS.

- [ ] **Step 6: Colunas no modelo e a migration**

Em `app/models/market_comparable.py`, depois de `coordinate_source`:

```python
    # O prédio como o portal o identifica. O QuintoAndar publica `condoId` em
    # 99,8% dos anúncios e ele agrupa sem erro — é por aqui que o anúncio sem
    # número da rua encontra o prédio, e daí o cadastro e o ITBI.
    condo_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    condo_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
```

Criar `alembic/versions/0018_condo_fields.py`:

```python
"""condo id e nome do prédio no anúncio

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_comparables", sa.Column("condo_id", sa.String(50), nullable=True))
    op.add_column("market_comparables", sa.Column("condo_name", sa.String(300), nullable=True))
    op.create_index(
        "ix_market_comparables_condo_id", "market_comparables", ["condo_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_market_comparables_condo_id", table_name="market_comparables")
    op.drop_column("market_comparables", "condo_name")
    op.drop_column("market_comparables", "condo_id")
```

Conferir o `revision` real de `0017_listing_outcomes.py` e usar exatamente aquele identificador em `down_revision`.

Em `app/services/market_refresh.py`, no dicionário de `_listing_values`, depois de `"coordinate_source": ...`:

```python
        "condo_id": item.condo_id,
        "condo_name": item.condo_name,
```

- [ ] **Step 7: Rodar a suíte inteira e a migration**

Run: `PYTHONPATH=. .venv/bin/pytest -v`
Expected: PASS.

Run: `PYTHONPATH=. .venv/bin/alembic upgrade head`
Expected: aplica `0018` sem erro.

- [ ] **Step 8: Commit**

```bash
git add app/market_collectors app/models/market_comparable.py app/services/market_refresh.py alembic/versions/0018_condo_fields.py tests/test_collectors/test_quintoandar.py
git commit -m "feat: QuintoAndar entrega o prédio, o IPTU e o condomínio na mesma busca"
```

---

## Fase B — O perfil de área do prédio

### Task 2: Decis das áreas das unidades no cadastro

**Files:**
- Modify: `app/ingestion/pbh_registry.py:62-88` (`RegistryRow`), `:129-200` (`aggregate`), `:202-216` (`_dispersion`)
- Modify: `app/models/registry_address.py`
- Modify: `app/services/registry_sync.py:85-115` (colunas do upsert)
- Modify: `app/domain/buildings.py:47-60` (`Building`), `:190-210` (`buildings_from_rows`)
- Create: `alembic/versions/0019_unit_area_profile.py`
- Test: `tests/test_services/test_registry_sync.py`

**Interfaces:**
- Consumes: nada da Tarefa 1.
- Produces: `RegistryRow.unit_area_profile: list[float] | None` (11 decis, do p0 ao p100); coluna `registry_addresses.unit_area_profile` (`sa.JSON`); `Building.unit_area_profile: list[float] | None`.

- [ ] **Step 1: Escrever o teste que falha**

Em `tests/test_services/test_registry_sync.py`:

```python
from app.ingestion.pbh_registry import aggregate


def _economia(area, numero="100"):
    return {
        "TIPO_CONSTRUTIVO": "APARTAMENTO",
        "TIPO_LOGRADOURO": "RUA",
        "NOME_LOGRADOURO": "DOS TIMBIRAS",
        "NUMERO_IMOVEL": numero,
        "AREA_CONSTRUCAO": str(area),
        "PADRAO_ACABAMENTO": "P4",
        "TIPO_OCUPACAO": "RESIDENCIAL",
        "GEOMETRIA": "",
        "CEP": "30140-060",
    }


def test_profile_has_eleven_deciles_from_p0_to_p100():
    """O casamento por posto precisa do formato do prédio, não só da mediana:
    a janela de área hoje recusa venda do próprio prédio por estar centrada num
    fator único da cidade."""
    areas = [90, 95, 100, 140, 145, 150, 205, 210, 215, 300]
    linhas = list(aggregate(_economia(a) for a in areas))
    perfil = linhas[0].unit_area_profile
    assert perfil is not None
    assert len(perfil) == 11
    assert perfil[0] == 90.0
    assert perfil[-1] == 300.0
    assert perfil == sorted(perfil)


def test_profile_is_none_below_four_units():
    """Abaixo de quatro unidades não há quartil, e três apartamentos não são
    evidência de formato nenhum — o mesmo piso que a dispersão já usa."""
    linhas = list(aggregate(_economia(a) for a in [90, 95, 100]))
    assert linhas[0].unit_area_profile is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_services/test_registry_sync.py -v -k profile`
Expected: FAIL — `AttributeError: 'RegistryRow' object has no attribute 'unit_area_profile'`.

- [ ] **Step 3: Calcular o perfil**

Em `app/ingestion/pbh_registry.py`, somar ao `RegistryRow` (depois de `unit_area_dispersion`):

```python
    unit_area_profile: list[float] | None
```

Somar a função, ao lado de `_dispersion`:

```python
def _profile(areas: list[float]) -> list[float] | None:
    """O formato do prédio: onze decis das áreas das suas unidades.

    A mediana diz o tamanho do apartamento típico e não diz que o prédio tem
    coberturas. Onde as unidades discordam entre si — 24% dos prédios, medido
    pela dispersão interquartil — é o posto do anúncio dentro dessa lista que
    diz qual unidade ele é, e a mediana comparava a cobertura com o quarto e
    sala.

    Onze números cabem em qualquer prédio e bastam para o posto. Abaixo de
    quatro unidades não há quartil a medir, e o mesmo piso da dispersão vale
    aqui: devolve None, e quem lê decide.
    """
    if len(areas) < 4:
        return None
    ordenadas = sorted(areas)
    ultimo = len(ordenadas) - 1
    return [
        round(ordenadas[round(decil * ultimo / 10)], 2) for decil in range(11)
    ]
```

No `yield RegistryRow(...)` de `aggregate`, depois de `unit_area_dispersion=...`:

```python
            unit_area_profile=_profile(grupo["areas"]),
```

- [ ] **Step 4: Rodar o teste**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_services/test_registry_sync.py -v -k profile`
Expected: PASS.

- [ ] **Step 5: Coluna, migration e upsert**

Em `app/models/registry_address.py`, importar `JSON` de `sqlalchemy` e somar depois de `unit_area_dispersion`:

```python
    # Onze decis das áreas das unidades. Onde o prédio é heterogêneo, é o que
    # diz qual unidade o anúncio é — o casamento por posto.
    unit_area_profile: Mapped[list | None] = mapped_column(JSON, nullable=True)
```

Criar `alembic/versions/0019_unit_area_profile.py`:

```python
"""perfil de áreas das unidades no cadastro

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "registry_addresses", sa.Column("unit_area_profile", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("registry_addresses", "unit_area_profile")
```

Em `app/services/registry_sync.py`, dentro da tupla de colunas do `on_conflict_do_update`, depois de `"unit_area_dispersion",`:

```python
                        "unit_area_profile",
```

Em `app/domain/buildings.py`, somar ao `Building`:

```python
    unit_area_profile: list[float] | None = None
```

e em `buildings_from_rows`, depois de `unit_area_dispersion=...`:

```python
            unit_area_profile=row.unit_area_profile,
```

- [ ] **Step 6: Rodar tudo e a migration**

Run: `PYTHONPATH=. .venv/bin/pytest -v`
Expected: PASS.

Run: `PYTHONPATH=. .venv/bin/alembic upgrade head`
Expected: aplica `0019`.

- [ ] **Step 7: Recarregar o cadastro e conferir o preenchimento**

Run: `PYTHONPATH=. .venv/bin/python -m app.ingestion.cli registry-sync --cidade belo_horizonte`

Run:
```bash
docker exec -e PGPASSWORD=imovelradar imovel-radar-postgres-1 psql -U imovelradar -d imovelradar -tAX \
  -c "select count(*), count(unit_area_profile) from registry_addresses where city='belo_horizonte' and construction_type='AP'"
```
Expected: a segunda contagem cobre a maioria dos endereços — os nulos são os prédios de menos de quatro unidades.

- [ ] **Step 8: Commit**

```bash
git add app/ingestion/pbh_registry.py app/models/registry_address.py app/services/registry_sync.py app/domain/buildings.py alembic/versions/0019_unit_area_profile.py tests/test_services/test_registry_sync.py
git commit -m "feat: o cadastro guarda o formato do prédio, não só o tamanho mediano"
```

---

## Fase C — O diretório de condomínios

### Task 3: Parser do sitemap e da página de condomínio

**Files:**
- Create: `app/ingestion/quintoandar_condos.py`
- Test: `tests/test_ingestion/test_quintoandar_condos.py`

**Interfaces:**
- Consumes: `app.domain.slugs.street_key`, `address_key`.
- Produces:
  - `CondoRow` (frozen dataclass): `source: str`, `external_id: str`, `slug: str`, `url: str`, `city: str`, `street: str | None`, `street_number: str | None`, `street_key: str | None`, `number_key: str | None`, `postal_code: str | None`, `neighborhood: str | None`, `lat: float | None`, `lon: float | None`, `min_area: float | None`, `max_area: float | None`, `min_bedrooms: int | None`, `max_bedrooms: int | None`, `installations: list[str] | None`, `doorman: str | None`, `source_lastmod: date | None`
  - `sitemap_parts(index_xml: str) -> list[str]`
  - `condo_entries(sitemap_xml: str, city_slug: str) -> list[tuple[str, date | None]]`
  - `slug_neighborhood(url: str, city_slug: str) -> str | None`
  - `parse_condo_page(html: str, url: str, *, city: str, lastmod: date | None = None) -> CondoRow | None`

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_ingestion/test_quintoandar_condos.py`:

```python
import json
from datetime import date

from app.ingestion.quintoandar_condos import (
    condo_entries,
    parse_condo_page,
    sitemap_parts,
    slug_neighborhood,
)

INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex><sitemap><loc>https://www.quintoandar.com.br/sitemap-v3-base-part-0000.xml</loc></sitemap>
<sitemap><loc>https://www.quintoandar.com.br/sitemap-v3-condos-part-0000.xml</loc></sitemap>
<sitemap><loc>https://www.quintoandar.com.br/sitemap-v3-condos-part-0001.xml</loc></sitemap>
</sitemapindex>"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset><url><loc>https://www.quintoandar.com.br/condominio/rua-professor-moraes-444-funcionarios-belo-horizonte-1d47sjeomd</loc><lastmod>2026-09-03</lastmod></url>
<url><loc>https://www.quintoandar.com.br/condominio/edificio-montreal-savassi-belo-horizonte-abc123xyz9</loc></url>
<url><loc>https://www.quintoandar.com.br/condominio/edificio-paulista-moema-sao-paulo-zzz999aaa1</loc><lastmod>2026-09-03</lastmod></url>
</urlset>"""


def _pagina(condo_info: dict) -> str:
    payload = {"props": {"pageProps": {"condoInfo": condo_info}}}
    return (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script></body></html>"
    )


CONDO_INFO = {
    "hashId": "1d47sjeomd",
    "name": None,
    "slug": "rua-professor-moraes-444-funcionarios-belo-horizonte",
    "lat": -19.937088012695312,
    "lng": -43.93140411376953,
    "address": "Rua Professor Moraes",
    "number": "444",
    "zipCode": "30150-370",
    "neighborhood": "Funcionários",
    "minArea": 27,
    "maxArea": 58,
    "minBedrooms": 1,
    "maxBedrooms": 2,
    "features": {
        "doorman": "NightAndDayShift",
        "installations": [
            {"key": "PORTARIA_24H", "text": "Portaria 24h", "value": "SIM"},
            {"key": "ELEVADOR", "text": "Elevador", "value": "SIM"},
            {"key": "PISCINA", "text": "Piscina", "value": "NAO"},
        ],
    },
}


def test_sitemap_parts_keeps_only_the_condo_partitions():
    assert sitemap_parts(INDEX) == [
        "https://www.quintoandar.com.br/sitemap-v3-condos-part-0000.xml",
        "https://www.quintoandar.com.br/sitemap-v3-condos-part-0001.xml",
    ]


def test_condo_entries_filters_by_city_and_keeps_lastmod():
    """O sitemap é nacional; só o que termina na cidade coberta interessa."""
    entradas = condo_entries(SITEMAP, "belo-horizonte")
    assert len(entradas) == 2
    assert entradas[0][1] == date(2026, 9, 3)
    assert entradas[1][1] is None
    assert all("sao-paulo" not in url for url, _ in entradas)


def test_slug_neighborhood_reads_the_last_segment_before_the_city():
    assert (
        slug_neighborhood(
            "https://www.quintoandar.com.br/condominio/"
            "rua-professor-moraes-444-funcionarios-belo-horizonte-1d47sjeomd",
            "belo-horizonte",
        )
        == "funcionarios"
    )
    assert (
        slug_neighborhood(
            "https://www.quintoandar.com.br/condominio/"
            "edificio-montreal-savassi-belo-horizonte-abc123xyz9",
            "belo-horizonte",
        )
        == "savassi"
    )


def test_parse_condo_page_extracts_the_street_number():
    """É o número que o anúncio não publica: 59 de 59 páginas o trazem."""
    row = parse_condo_page(
        _pagina(CONDO_INFO),
        "https://www.quintoandar.com.br/condominio/x-1d47sjeomd",
        city="belo_horizonte",
        lastmod=date(2026, 9, 3),
    )
    assert row is not None
    assert row.external_id == "1d47sjeomd"
    assert row.street == "Rua Professor Moraes"
    assert row.street_number == "444"
    assert row.street_key == "rua_professor_moraes"
    assert row.number_key == "444"
    assert row.postal_code == "30150-370"
    assert row.lat == -19.937088 and row.lon == -43.931404
    assert row.min_area == 27 and row.max_area == 58
    assert row.doorman == "NightAndDayShift"
    assert row.installations == ["ELEVADOR", "PORTARIA_24H"]
    assert row.source_lastmod == date(2026, 9, 3)


def test_parse_condo_page_without_number_is_dropped():
    """Sem número a página não responde à pergunta que a fez ser buscada."""
    sem_numero = dict(CONDO_INFO, number=None)
    assert (
        parse_condo_page(_pagina(sem_numero), "https://x/y", city="belo_horizonte")
        is None
    )


def test_parse_condo_page_without_next_data_is_dropped():
    assert parse_condo_page("<html></html>", "https://x/y", city="belo_horizonte") is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_ingestion/test_quintoandar_condos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.quintoandar_condos'`.

- [ ] **Step 3: Escrever o parser**

Criar `app/ingestion/quintoandar_condos.py`:

```python
"""O diretório de condomínios do QuintoAndar: o número da rua que o anúncio não dá.

A limitação que mais custou à escada de referência é que Loft e QuintoAndar
publicam a rua e não publicam o número — sem ele o anúncio nunca alcança o tier
de endereço exato, onde o erro medido é 5-13% contra 14-25% na rua e no bairro.

O portal publica esse número em outro lugar: uma página por prédio, indexada em
`sitemap-v3-condos-part-*.xml` e liberada pelo `robots.txt`. São 19.117 páginas
de Belo Horizonte. Medido em 59 delas sorteadas: 59 trazem o número, 49 (83%)
casam com o cadastro da prefeitura por rua+número, e o ponto que publicam fica a
8 m (mediana) do lote do cadastro e a 1 m do anúncio do próprio portal.

O payload vem no `__NEXT_DATA__` da página, sob `condoInfo`. Responde a `curl`
sem sessão, sem cookie e sem navegador — este módulo é só o parser; o I/O e o
ritmo estão em `app/services/condo_sync.py`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.slugs import address_key, street_key

SOURCE = "quintoandar"
SITEMAP_INDEX = "https://www.quintoandar.com.br/sitemap-v3.xml"

_CONDO_PART = re.compile(r"sitemap-v3-condos-part-\d+\.xml$")
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_URL_BLOCK = re.compile(r"<url\b.*?</url>", re.I | re.S)
_LASTMOD = re.compile(r"<lastmod>\s*(\d{4}-\d{2}-\d{2})", re.I)
_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.I | re.S
)
# O slug termina em `-{hashId}`, dez caracteres alfanuméricos.
_SLUG_TAIL = re.compile(r"-([a-z0-9]{10})$")


@dataclass(frozen=True)
class CondoRow:
    """Um prédio como o portal o publica."""

    source: str
    external_id: str
    slug: str
    url: str
    city: str
    street: str | None
    street_number: str | None
    street_key: str | None
    number_key: str | None
    postal_code: str | None
    neighborhood: str | None
    lat: float | None
    lon: float | None
    min_area: float | None
    max_area: float | None
    min_bedrooms: int | None
    max_bedrooms: int | None
    installations: list[str] | None
    doorman: str | None
    source_lastmod: date | None


def sitemap_parts(index_xml: str) -> list[str]:
    """As partições de condomínio do índice de sitemaps, na ordem em que vêm."""
    return [url for url in _LOC.findall(index_xml) if _CONDO_PART.search(url)]


def condo_entries(sitemap_xml: str, city_slug: str) -> list[tuple[str, date | None]]:
    """(URL, data da última alteração) das páginas daquela cidade.

    O sitemap é nacional e tem centenas de milhares de linhas; a cidade está no
    fim do slug, antes do hash, então filtrar por texto é exato e não exige
    abrir cada página para descobrir que ela é de outro estado.
    """
    encontrados: list[tuple[str, date | None]] = []
    marca = f"-{city_slug}-"
    for bloco in _URL_BLOCK.findall(sitemap_xml):
        achado = _LOC.search(bloco)
        if achado is None or marca not in achado.group(1):
            continue
        quando = _LASTMOD.search(bloco)
        encontrados.append(
            (achado.group(1), date.fromisoformat(quando.group(1)) if quando else None)
        )
    return encontrados


def slug_neighborhood(url: str, city_slug: str) -> str | None:
    """O bairro que o slug declara, que é o que dá para filtrar antes de baixar.

    Metade dos slugs começa pela rua e a outra metade pelo nome do prédio, mas
    todos terminam em `-{bairro}-{cidade}-{hash}`. O bairro é o que permite
    gastar o orçamento de uma execução onde há anúncio sem prédio resolvido.
    """
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = _SLUG_TAIL.sub("", slug)
    marca = f"-{city_slug}"
    if not slug.endswith(marca):
        return None
    resto = slug[: -len(marca)]
    return resto.rsplit("-", 1)[-1] or None


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _int(value: Any) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _condo_info(payload: Any, profundidade: int = 0) -> dict | None:
    """`condoInfo` mora sob `props.pageProps`, mas o portal já moveu a chave de
    lugar entre versões do bundle — procurar é mais barato que reagir a isso."""
    if profundidade > 8 or not isinstance(payload, dict):
        return None
    achado = payload.get("condoInfo")
    if isinstance(achado, dict):
        return achado
    for valor in payload.values():
        if isinstance(valor, dict):
            encontrado = _condo_info(valor, profundidade + 1)
            if encontrado is not None:
                return encontrado
    return None


def parse_condo_page(
    html: str, url: str, *, city: str, lastmod: date | None = None
) -> CondoRow | None:
    """Lê uma página de condomínio, ou devolve None quando ela não serve.

    Sem número da rua a página não responde à pergunta que a fez ser baixada, e
    guardá-la só encheria a tabela — então ela é descartada aqui, e não depois.
    """
    achado = _NEXT_DATA.search(html)
    if achado is None:
        return None
    try:
        payload = json.loads(achado.group(1))
    except json.JSONDecodeError:
        return None
    info = _condo_info(payload)
    if info is None:
        return None

    numero = _clean(info.get("number"))
    rua = _clean(info.get("address"))
    chave_rua, chave_numero = street_key(rua), address_key(numero)
    if not numero or not chave_rua or not chave_numero:
        return None

    features = info.get("features") if isinstance(info.get("features"), dict) else {}
    instalacoes = features.get("installations")
    presentes = (
        sorted(
            _clean(item.get("key"))
            for item in instalacoes
            if isinstance(item, dict)
            and str(item.get("value", "")).strip().upper() == "SIM"
            and _clean(item.get("key"))
        )
        if isinstance(instalacoes, list)
        else None
    )

    lat, lon = _float(info.get("lat")), _float(info.get("lng"))
    return CondoRow(
        source=SOURCE,
        external_id=str(info.get("hashId") or "").strip(),
        slug=str(info.get("slug") or "").strip(),
        url=url,
        city=city,
        street=rua,
        street_number=numero,
        street_key=chave_rua,
        number_key=chave_numero,
        postal_code=_clean(info.get("zipCode")),
        neighborhood=_clean(info.get("neighborhood")),
        # Seis casas bastam para distinguir lotes vizinhos e é a precisão que
        # `registry_addresses` já guarda; o portal devolve o float inteiro.
        lat=round(lat, 6) if lat is not None else None,
        lon=round(lon, 6) if lon is not None else None,
        min_area=_float(info.get("minArea")),
        max_area=_float(info.get("maxArea")),
        min_bedrooms=_int(info.get("minBedrooms")),
        max_bedrooms=_int(info.get("maxBedrooms")),
        installations=presentes or None,
        doorman=_clean(features.get("doorman")),
        source_lastmod=lastmod,
    )
```

- [ ] **Step 4: Rodar o teste**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_ingestion/test_quintoandar_condos.py -v`
Expected: PASS, seis testes.

- [ ] **Step 5: Commit**

```bash
git add app/ingestion/quintoandar_condos.py tests/test_ingestion/test_quintoandar_condos.py
git commit -m "feat: lê o diretório de condomínios do QuintoAndar"
```

---

### Task 4: A tabela dos prédios do portal

**Files:**
- Create: `app/models/portal_building.py`
- Create: `alembic/versions/0020_portal_buildings.py`
- Modify: `app/db/base.py` (se ele importa os modelos explicitamente — conferir antes)
- Test: `tests/test_models/test_portal_building.py`

**Interfaces:**
- Consumes: `CondoRow` da Tarefa 3.
- Produces: `PortalBuilding`, tabela `portal_buildings`, restrição única `uq_portal_buildings_source_external` sobre `(source, external_id)`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_models/test_portal_building.py`:

```python
from datetime import date

from app.models.portal_building import PortalBuilding


def test_portal_building_round_trips(db_session):
    predio = PortalBuilding(
        source="quintoandar",
        external_id="1d47sjeomd",
        slug="rua-professor-moraes-444-funcionarios-belo-horizonte",
        url="https://www.quintoandar.com.br/condominio/x-1d47sjeomd",
        city="belo_horizonte",
        street="Rua Professor Moraes",
        street_number="444",
        street_key="rua_professor_moraes",
        number_key="444",
        postal_code="30150-370",
        neighborhood="Funcionários",
        lat=-19.937088,
        lon=-43.931404,
        min_area=27,
        max_area=58,
        min_bedrooms=1,
        max_bedrooms=2,
        installations=["ELEVADOR", "PORTARIA_24H"],
        doorman="NightAndDayShift",
        source_lastmod=date(2026, 9, 3),
    )
    db_session.add(predio)
    db_session.commit()

    gravado = db_session.query(PortalBuilding).one()
    assert gravado.number_key == "444"
    assert gravado.installations == ["ELEVADOR", "PORTARIA_24H"]
    assert gravado.source_lastmod == date(2026, 9, 3)
```

Usar a fixture de sessão que `tests/conftest.py` já expõe; conferir o nome real antes de escrever (`db_session` é o esperado — se for outro, usar o outro).

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_models/test_portal_building.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.portal_building'`.

- [ ] **Step 3: Escrever o modelo**

Criar `app/models/portal_building.py`:

```python
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
    tabela sabe o que o portal chama de prédio, e é o que liga um anúncio sem
    número ao endereço. As duas se encontram por rua + número.

    Medido em 59 páginas de Belo Horizonte: 83% casam com o cadastro por
    rua+número, e o ponto publicado fica a 8 m (mediana) do lote do cadastro.
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
    # Só as instalações presentes ("SIM"). O padrão de acabamento do cadastro
    # responde a mesma pergunta pelo lado da prefeitura.
    installations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    doorman: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # A data que o próprio sitemap declara, que é o que torna a recoleta
    # incremental — e não a data em que rodamos.
    source_lastmod: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

Criar `alembic/versions/0020_portal_buildings.py` com o `op.create_table` correspondente, `revision = "0020"`, `down_revision = "0019"`, e os índices em `source`, `city`, `street_key`, `neighborhood`, `lat`, `lon`, mais a `UniqueConstraint`. No `downgrade`, `op.drop_table("portal_buildings")`.

Se `app/db/base.py` importar os modelos um a um, somar `from app.models.portal_building import PortalBuilding  # noqa: F401`.

- [ ] **Step 4: Rodar o teste e a migration**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_models/test_portal_building.py -v`
Expected: PASS.

Run: `PYTHONPATH=. .venv/bin/alembic upgrade head`
Expected: aplica `0020`.

- [ ] **Step 5: Commit**

```bash
git add app/models/portal_building.py app/db/base.py alembic/versions/0020_portal_buildings.py tests/test_models/test_portal_building.py
git commit -m "feat: tabela dos prédios que o portal publica"
```

---

### Task 5: Coleta sob demanda do diretório

**Files:**
- Create: `app/services/condo_sync.py`
- Modify: `app/ingestion/cli.py`
- Modify: `Makefile`
- Test: `tests/test_services/test_condo_sync.py`

**Interfaces:**
- Consumes: `sitemap_parts`, `condo_entries`, `slug_neighborhood`, `parse_condo_page`, `CondoRow`, `PortalBuilding`.
- Produces:
  - `pending_neighborhoods(db: Session, city_key: str) -> list[str]` — bairros normalizados com anúncio ativo sem número, do mais carente ao menos
  - `select_targets(entries, bairros, conhecidos, *, limit) -> list[tuple[str, date | None]]`
  - `save_buildings(db: Session, rows: Iterable[CondoRow]) -> int`
  - `sync_condos(db, *, city="belo_horizonte", city_slug="belo-horizonte", limit=500, fetch=..., progress=None) -> dict`
  - CLI: `python -m app.ingestion.cli condo-sync --cidade belo_horizonte --limit 500`

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_services/test_condo_sync.py`:

```python
from datetime import date

from app.services.condo_sync import select_targets


def test_select_targets_prefers_needy_neighborhoods_and_respects_the_budget():
    """O orçamento de uma execução vai onde há anúncio sem prédio resolvido."""
    entradas = [
        ("https://q/condominio/a-savassi-belo-horizonte-aaaaaaaaaa", date(2026, 9, 3)),
        ("https://q/condominio/b-buritis-belo-horizonte-bbbbbbbbbb", None),
        ("https://q/condominio/c-savassi-belo-horizonte-cccccccccc", None),
        ("https://q/condominio/d-castelo-belo-horizonte-dddddddddd", None),
    ]
    alvos = select_targets(
        entradas, ["savassi", "buritis"], conhecidos={}, limit=3, city_slug="belo-horizonte"
    )
    urls = [url for url, _ in alvos]
    assert len(urls) == 3
    assert all("castelo" not in url for url in urls)
    assert sum("savassi" in url for url in urls) == 2


def test_select_targets_skips_pages_already_stored_and_unchanged():
    """O sitemap declara a data; repetir a mesma página é gasto sem resposta."""
    entradas = [
        ("https://q/condominio/a-savassi-belo-horizonte-aaaaaaaaaa", date(2026, 9, 3)),
        ("https://q/condominio/b-savassi-belo-horizonte-bbbbbbbbbb", date(2026, 9, 3)),
    ]
    conhecidos = {
        "https://q/condominio/a-savassi-belo-horizonte-aaaaaaaaaa": date(2026, 9, 3),
        "https://q/condominio/b-savassi-belo-horizonte-bbbbbbbbbb": date(2026, 8, 1),
    }
    alvos = select_targets(
        entradas, ["savassi"], conhecidos=conhecidos, limit=10, city_slug="belo-horizonte"
    )
    assert [url for url, _ in alvos] == [
        "https://q/condominio/b-savassi-belo-horizonte-bbbbbbbbbb"
    ]


def test_select_targets_keeps_a_page_without_lastmod_only_once():
    """Sem data declarada, uma página já gravada não volta a ser baixada."""
    entradas = [("https://q/condominio/a-savassi-belo-horizonte-aaaaaaaaaa", None)]
    conhecidos = {"https://q/condominio/a-savassi-belo-horizonte-aaaaaaaaaa": None}
    assert (
        select_targets(
            entradas, ["savassi"], conhecidos=conhecidos, limit=10, city_slug="belo-horizonte"
        )
        == []
    )
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_services/test_condo_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.condo_sync'`.

- [ ] **Step 3: Escrever o serviço**

Criar `app/services/condo_sync.py`:

```python
"""Baixa as páginas de condomínio de que a nota precisa, e só elas.

São 19.117 páginas de Belo Horizonte, de quase um megabyte cada. Baixar todas
seria dezessete gigabytes para responder a uma pergunta que só interessa onde
existe anúncio: qual o número da rua deste prédio.

Então a coleta é dirigida pelo anúncio. O bairro está no fim do slug, antes do
hash, o que permite escolher o alvo sem abrir a página; a ordem é a dos bairros
com mais anúncio ativo sem número resolvido, e cada execução tem teto. O
`<lastmod>` do sitemap faz o resto: página já gravada e não alterada não volta.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

import requests
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.ingestion.quintoandar_condos import (
    SITEMAP_INDEX,
    CondoRow,
    condo_entries,
    parse_condo_page,
    sitemap_parts,
    slug_neighborhood,
)
from app.models.market_comparable import MarketComparable
from app.models.portal_building import PortalBuilding

logger = logging.getLogger(__name__)

# O mesmo ritmo do qpreço: uma página é o que um humano navegando dispara, e é
# essa ordem de grandeza que se imita. O sitemap existe para ser lido, mas o
# volume aqui é de milhares e não de dezenas.
MIN_INTERVAL_SECONDS = float(os.getenv("CONDO_MIN_INTERVAL_SECONDS", "1.0"))
DEFAULT_LIMIT = 500
HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": "Mozilla/5.0 (compatible; ImovelRadar/1.0)",
}
TIMEOUT = (15, 60)
# Portal recusando é resposta, não soluço: para a etapa em vez de gastar o
# resto do orçamento contra um gateway que acabou de negar.
BLOCKED_STATUS = frozenset({401, 403, 429})


class PortalBlockedError(RuntimeError):
    pass


def _get(url: str) -> str:
    resposta = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if resposta.status_code in BLOCKED_STATUS:
        raise PortalBlockedError(f"http_{resposta.status_code}")
    resposta.raise_for_status()
    return resposta.text


def pending_neighborhoods(db: Session, city_key: str) -> list[str]:
    """Bairros com anúncio ativo sem número, do mais carente ao menos."""
    linhas = db.execute(
        select(
            MarketComparable.bairro_normalizado,
            func.count(MarketComparable.id).label("quantos"),
        )
        .where(MarketComparable.ativo.is_(True))
        .where(MarketComparable.cidade_normalizada == city_key)
        .where(MarketComparable.numero_normalizado.is_(None))
        .where(MarketComparable.bairro_normalizado.is_not(None))
        .group_by(MarketComparable.bairro_normalizado)
        .order_by(func.count(MarketComparable.id).desc())
    ).all()
    return [bairro for bairro, _ in linhas]


def known_pages(db: Session, city: str) -> dict[str, date | None]:
    """URL -> `lastmod` já gravado, para não rebaixar o que não mudou."""
    linhas = db.execute(
        select(PortalBuilding.url, PortalBuilding.source_lastmod).where(
            PortalBuilding.city == city
        )
    ).all()
    return {url: quando for url, quando in linhas}


def select_targets(
    entries: Iterable[tuple[str, date | None]],
    bairros: list[str],
    *,
    conhecidos: dict[str, date | None],
    limit: int,
    city_slug: str,
) -> list[tuple[str, date | None]]:
    """As páginas a baixar nesta execução, na ordem da carência.

    Um bairro fora da lista não tem anúncio sem número, então a página dele não
    mudaria nota nenhuma hoje. Ela volta quando um anúncio aparecer lá.
    """
    posicao = {bairro: indice for indice, bairro in enumerate(bairros)}
    candidatos: list[tuple[int, str, date | None]] = []
    for url, lastmod in entries:
        bairro = slug_neighborhood(url, city_slug)
        if bairro is None or bairro not in posicao:
            continue
        if url in conhecidos:
            gravado = conhecidos[url]
            # Sem data declarada não há como saber que mudou; baixar de novo
            # seria repetir para sempre a mesma resposta.
            if lastmod is None or (gravado is not None and gravado >= lastmod):
                continue
        candidatos.append((posicao[bairro], url, lastmod))
    candidatos.sort(key=lambda item: (item[0], item[1]))
    return [(url, lastmod) for _, url, lastmod in candidatos[: max(0, limit)]]


def save_buildings(db: Session, rows: Iterable[CondoRow]) -> int:
    """Grava os prédios, atualizando o que já existe."""
    unicos: dict[tuple[str, str], dict] = {}
    for row in rows:
        if not row.external_id:
            continue
        unicos[(row.source, row.external_id)] = row.__dict__.copy()
    if not unicos:
        return 0

    dialeto = db.bind.dialect.name
    insert = sqlite_insert if dialeto == "sqlite" else postgresql_insert
    for valores in unicos.values():
        stmt = insert(PortalBuilding).values(**valores)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[PortalBuilding.source, PortalBuilding.external_id],
                set_={
                    coluna: stmt.excluded[coluna]
                    for coluna in valores
                    if coluna not in {"source", "external_id"}
                },
            )
        )
    db.commit()
    return len(unicos)


def sync_condos(
    db: Session,
    *,
    city: str = "belo_horizonte",
    city_slug: str = "belo-horizonte",
    limit: int = DEFAULT_LIMIT,
    fetch: Callable[[str], str] = _get,
    sleep: Callable[[float], None] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Uma passada da coleta: escolhe os alvos, baixa, grava."""
    import time

    pausa = sleep if sleep is not None else time.sleep

    bairros = pending_neighborhoods(db, city)
    if not bairros:
        return {"city": city, "alvos": 0, "gravados": 0, "falhas": 0, "motivo": "sem bairro pendente"}

    entradas: list[tuple[str, date | None]] = []
    for parte in sitemap_parts(fetch(SITEMAP_INDEX)):
        pausa(MIN_INTERVAL_SECONDS)
        entradas.extend(condo_entries(fetch(parte), city_slug))

    alvos = select_targets(
        entradas, bairros, conhecidos=known_pages(db, city), limit=limit, city_slug=city_slug
    )
    if progress:
        progress(f"[condo-sync] bairros={len(bairros)} sitemap={len(entradas)} alvos={len(alvos)}")

    linhas: list[CondoRow] = []
    falhas = 0
    interrompido: str | None = None
    for indice, (url, lastmod) in enumerate(alvos, start=1):
        pausa(MIN_INTERVAL_SECONDS)
        try:
            pagina = fetch(url)
        except PortalBlockedError as erro:
            interrompido = f"bloqueado:{erro}"
            break
        except Exception as erro:  # noqa: BLE001 - contado e seguido
            falhas += 1
            logger.warning("[condo-sync] status=error url=%s error=%s", url, erro)
            continue
        row = parse_condo_page(pagina, url, city=city, lastmod=lastmod)
        if row is None:
            falhas += 1
            continue
        linhas.append(row)
        if progress and indice % 50 == 0:
            progress(f"[condo-sync] {indice}/{len(alvos)} lidos={len(linhas)} falhas={falhas}")

    gravados = save_buildings(db, linhas)
    return {
        "city": city,
        "alvos": len(alvos),
        "gravados": gravados,
        "falhas": falhas,
        "interrompido": interrompido,
    }
```

- [ ] **Step 4: Rodar o teste**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_services/test_condo_sync.py -v`
Expected: PASS, três testes.

- [ ] **Step 5: Somar o comando de CLI**

Em `app/ingestion/cli.py`, seguindo o padrão dos subcomandos já existentes (`registry-sync` é o mais próximo), somar `condo-sync` com `--cidade` (padrão `belo_horizonte`) e `--limit` (padrão 500), que abre a sessão, chama `sync_condos(db, city=..., limit=..., progress=print)` e imprime o resumo.

No `Makefile`, ao lado de `cadastro`:

```make
condominios:  ## baixa as páginas de condomínio dos bairros com anúncio sem número
	PYTHONPATH=. $(PY) -m app.ingestion.cli condo-sync --cidade $(CIDADE_KEY) --limit $(CONDO_LIMIT)
```

com `CONDO_LIMIT ?= 500` junto das outras variáveis do topo, e `CIDADE_KEY ?= belo_horizonte` se ainda não existir.

- [ ] **Step 6: Rodar de verdade, com teto pequeno**

Run: `PYTHONPATH=. .venv/bin/python -m app.ingestion.cli condo-sync --cidade belo_horizonte --limit 50`
Expected: imprime o resumo com `gravados` próximo de 50 e `falhas` baixo. Se vier `interrompido=bloqueado`, parar e relatar — não repetir.

Run:
```bash
docker exec -e PGPASSWORD=imovelradar imovel-radar-postgres-1 psql -U imovelradar -d imovelradar -tAX \
  -c "select count(*), count(number_key), count(lat) from portal_buildings where city='belo_horizonte'"
```
Expected: as três contagens próximas.

- [ ] **Step 7: Rodar a suíte e commitar**

Run: `PYTHONPATH=. .venv/bin/pytest -v`
Expected: PASS.

```bash
git add app/services/condo_sync.py app/ingestion/cli.py Makefile tests/test_services/test_condo_sync.py
git commit -m "feat: coleta as páginas de condomínio dirigida pelo anúncio sem número"
```

---

### Task 6: O anúncio encontra o número pelo prédio do portal

**Files:**
- Modify: `app/domain/buildings.py` (somar `PortalBuildingIndex`)
- Modify: `app/services/opportunities.py:196-268` (`fetch_registry_buildings`, `_resolved_number`, `_building`, `_listing_input`)
- Modify: `app/domain/opportunities.py` (constante `NUMERO_ORIGEM_PORTAL`, tier e erro esperado)
- Test: `tests/test_domain/test_buildings.py` (criar se não existir), `tests/test_services/test_opportunities.py`

**Interfaces:**
- Consumes: `PortalBuilding` (Tarefa 4), `MarketComparable.condo_id` (Tarefa 1).
- Produces:
  - `PortalBuildingIndex.build(rows) -> PortalBuildingIndex`
  - `PortalBuildingIndex.resolve(street_key, lat, lon, *, radius_m=30.0) -> str | None`
  - `app.domain.opportunities.NUMERO_ORIGEM_PORTAL = "portal"`
  - `EXPECTED_ERROR["endereco_portal"] = (0.05, 0.10, 0.13)` e `REFERENCE_CONFIDENCE["endereco_portal"] = "alta"`

- [ ] **Step 1: Escrever o teste que falha**

Em `tests/test_domain/test_buildings.py`:

```python
from app.domain.buildings import PortalBuilding as _  # noqa: F401  (ver Step 3)
from app.domain.buildings import PortalBuildingIndex, PortalPoint


def test_portal_index_resolves_the_number_from_the_condo_point():
    """O ponto do condo fica a 1 m (mediana) do anúncio do próprio portal —
    uma ordem de grandeza mais perto do que o lote do cadastro, a 8 m."""
    index = PortalBuildingIndex.build(
        [
            PortalPoint("rua_professor_moraes", "444", -19.937088, -43.931404),
            PortalPoint("rua_professor_moraes", "500", -19.938500, -43.931900),
        ]
    )
    assert index.resolve("rua_professor_moraes", -19.937090, -43.931400) == "444"


def test_portal_index_never_crosses_streets():
    """Um ponto a 20 m pode estar na rua de trás, e comparar contra o prédio
    errado de outra rua é pior do que não resolver."""
    index = PortalBuildingIndex.build(
        [PortalPoint("rua_professor_moraes", "444", -19.937088, -43.931404)]
    )
    assert index.resolve("rua_tome_de_souza", -19.937090, -43.931400) is None


def test_portal_index_ignores_points_beyond_the_radius():
    index = PortalBuildingIndex.build(
        [PortalPoint("rua_professor_moraes", "444", -19.937088, -43.931404)]
    )
    assert index.resolve("rua_professor_moraes", -19.940000, -43.931404) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_domain/test_buildings.py -v`
Expected: FAIL — `ImportError: cannot import name 'PortalBuildingIndex'`.

- [ ] **Step 3: Somar o índice de prédios do portal**

Em `app/domain/buildings.py`, somar ao final:

```python
# O ponto que o portal publica para o prédio fica a 1 m (mediana) e no máximo
# 27 m do anúncio daquele prédio — contra 8 m e 24 m do lote do cadastro. Como
# as duas pontas saem da mesma fonte, o raio pode ser bem mais apertado, e um
# raio apertado é o que evita colar o anúncio no prédio vizinho.
PORTAL_MATCH_RADIUS_M = 30.0


@dataclass(frozen=True)
class PortalPoint:
    """Um prédio do diretório do portal, reduzido ao que a busca precisa."""

    street_key: str
    number_key: str
    lat: float
    lon: float


@dataclass(frozen=True)
class PortalBuildingIndex:
    """Os prédios do portal, indexados por célula como os lotes do cadastro."""

    by_cell: Mapping[tuple[str, int, int], list[PortalPoint]] = field(default_factory=dict)

    @classmethod
    def build(cls, points: Iterable[PortalPoint]) -> "PortalBuildingIndex":
        by_cell: dict[tuple[str, int, int], list[PortalPoint]] = defaultdict(list)
        for ponto in points:
            if ponto.lat is None or ponto.lon is None or not ponto.street_key:
                continue
            by_cell[_cell_of(ponto.street_key, ponto.lat, ponto.lon)].append(ponto)
        return cls(dict(by_cell))

    def resolve(
        self,
        street_key: str | None,
        lat: float | None,
        lon: float | None,
        *,
        radius_m: float = PORTAL_MATCH_RADIUS_M,
    ) -> str | None:
        """Número do prédio do portal mais próximo na mesma rua, ou None."""
        if not street_key or lat is None or lon is None:
            return None
        melhor: PortalPoint | None = None
        distancia = radius_m
        cy, cx = _cell_index(lat, lon)
        alcance = _cell_span(radius_m)
        for dy in range(-alcance, alcance + 1):
            for dx in range(-alcance, alcance + 1):
                for ponto in self.by_cell.get((street_key, cy + dy, cx + dx), ()):
                    d = haversine_m(lat, lon, ponto.lat, ponto.lon)
                    if d < distancia:
                        melhor, distancia = ponto, d
        return melhor.number_key if melhor is not None else None


def portal_points_from_rows(rows: Sequence) -> list[PortalPoint]:
    """Converte linhas de `portal_buildings` em `PortalPoint`."""
    return [
        PortalPoint(
            street_key=row.street_key,
            number_key=row.number_key,
            lat=float(row.lat),
            lon=float(row.lon),
        )
        for row in rows
        if row.street_key and row.number_key and row.lat is not None and row.lon is not None
    ]
```

Remover a primeira linha do teste (`from app.domain.buildings import PortalBuilding as _`) — foi um lapso do esqueleto; o módulo não exporta esse nome.

- [ ] **Step 4: Rodar o teste**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_domain/test_buildings.py -v`
Expected: PASS.

- [ ] **Step 5: Somar o tier e ligar no serviço**

Em `app/domain/opportunities.py`:

```python
# Número resolvido pelo diretório de condomínios do portal, e não pela
# proximidade do lote. É o próprio portal dizendo em que prédio o anúncio está,
# então a pergunta "é mesmo este prédio?" tem resposta melhor do que os 93,5%
# do `endereco_geo`: o ponto do condo fica a 1 m do anúncio na mediana.
NUMERO_ORIGEM_PORTAL = "portal"
```

Somar a `EXPECTED_ERROR`, junto de `endereco_exato`:

```python
    # O portal publica o prédio do anúncio; a incerteza que sobra é a mesma do
    # endereço declarado, não a da coordenada.
    "endereco_portal": (0.05, 0.10, 0.13),
```

Somar a `REFERENCE_CONFIDENCE`: `"endereco_portal": "alta"`, e a `REFERENCE_LABEL`:
`"endereco_portal": "endereço, pelo condomínio do portal"`.

Em `select_reference`, na escolha do tier de endereço, trocar a linha única por:

```python
            tier = {
                NUMERO_ORIGEM_CADASTRO: "endereco_geo",
                NUMERO_ORIGEM_PORTAL: "endereco_portal",
            }.get(listing.numero_origem, "endereco_exato")
```

Em `build_calibration`, somar `"endereco_portal"` ao conjunto isento do piso de amostra, junto de `"endereco_exato"` e `"endereco_geo"`.

Em `app/services/opportunities.py`, `_resolved_number` passa a tentar, nesta ordem: o número que o anúncio publica; o prédio do portal pelo `condo_id`, quando outro anúncio do mesmo `condo_id` já tem número resolvido; o prédio do portal pela coordenada (`PortalBuildingIndex.resolve`); e por fim o lote do cadastro (`BuildingIndex.resolve`), como hoje. Cada caminho devolve também a origem, que vira o tier.

Somar `fetch_portal_buildings(db, city) -> PortalBuildingIndex`, no molde de `fetch_registry_buildings`, lendo `PortalBuilding` filtrado por `city` e passando por `portal_points_from_rows`.

- [ ] **Step 6: Rodar tudo**

Run: `PYTHONPATH=. .venv/bin/pytest -v`
Expected: PASS.

- [ ] **Step 7: Medir o ganho de cobertura**

Run: `PYTHONPATH=. .venv/bin/python -m app.ingestion.cli opportunity-refresh --cidade "Belo Horizonte" --sem-qpreco`

Run:
```bash
docker exec -e PGPASSWORD=imovelradar imovel-radar-postgres-1 psql -U imovelradar -d imovelradar -tAX -F' | ' \
  -c "select tipo_referencia, count(*) from market_comparables where ativo and nota is not null group by 1 order by 2 desc"
```
Expected: `endereco_portal` aparece, e a soma dos tiers de endereço cresce contra a linha de base anotada antes da tarefa. Registrar os dois números na mensagem de commit.

- [ ] **Step 8: Commit**

```bash
git add app/domain/buildings.py app/domain/opportunities.py app/services/opportunities.py tests/test_domain/test_buildings.py tests/test_services/test_opportunities.py
git commit -m "feat: o anúncio acha o número pelo condomínio que o portal publica"
```

---

## Fase D — A área de referência

### Task 7: Resolver a área do anúncio em espaço de cadastro

**Files:**
- Create: `app/domain/unit_area.py`
- Test: `tests/test_domain/test_unit_area.py`

**Interfaces:**
- Consumes: `Building.unit_area_profile`, `Building.median_unit_area`, `Building.unit_area_dispersion` (Tarefa 2).
- Produces:
  - `HOMOGENEOUS_DISPERSION = 0.30`
  - `rank_of(value: float, peers: Sequence[float]) -> float` — posição de 0 a 1 do valor entre os pares, inclusive ele mesmo
  - `area_at_rank(profile: Sequence[float], rank: float) -> float` — interpolação linear nos decis
  - `reference_area(area_anunciada, *, profile, median_unit_area, dispersion, peers, fallback_factor) -> tuple[float, str]` — devolve `(área em espaço de cadastro, origem)` com origem em `{"predio_mediana", "predio_posto", "fator"}`

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_domain/test_unit_area.py`:

```python
import pytest

from app.domain.unit_area import area_at_rank, rank_of, reference_area

PERFIL = [90.0, 95.0, 100.0, 140.0, 145.0, 150.0, 205.0, 210.0, 215.0, 260.0, 300.0]


def test_rank_of_places_the_only_listing_in_the_middle():
    """Com um anúncio só no prédio não há posto a medir, e a mediana é a
    resposta menos errada."""
    assert rank_of(80.0, [80.0]) == pytest.approx(0.5)


def test_rank_of_orders_the_listings_of_a_building():
    assert rank_of(60.0, [60.0, 120.0, 240.0]) == pytest.approx(0.0)
    assert rank_of(120.0, [60.0, 120.0, 240.0]) == pytest.approx(0.5)
    assert rank_of(240.0, [60.0, 120.0, 240.0]) == pytest.approx(1.0)


def test_area_at_rank_interpolates_between_deciles():
    assert area_at_rank(PERFIL, 0.0) == pytest.approx(90.0)
    assert area_at_rank(PERFIL, 1.0) == pytest.approx(300.0)
    assert area_at_rank(PERFIL, 0.5) == pytest.approx(150.0)
    assert area_at_rank(PERFIL, 0.55) == pytest.approx(177.5)


def test_reference_area_uses_the_building_median_when_units_agree():
    """Dentro de um prédio homogêneo a janela de área não tem o que separar:
    a dispersão mediana das áreas de um endereço é 0,09."""
    area, origem = reference_area(
        80.0, profile=PERFIL, median_unit_area=145.0, dispersion=0.09,
        peers=[80.0, 82.0], fallback_factor=1.6,
    )
    assert area == pytest.approx(145.0)
    assert origem == "predio_mediana"


def test_reference_area_matches_by_rank_when_units_disagree():
    """No prédio heterogêneo o posto diz qual unidade o anúncio é — a mediana
    comparava a cobertura com o quarto e sala."""
    area, origem = reference_area(
        180.0, profile=PERFIL, median_unit_area=145.0, dispersion=0.55,
        peers=[60.0, 120.0, 180.0], fallback_factor=1.6,
    )
    assert area == pytest.approx(300.0)
    assert origem == "predio_posto"


def test_reference_area_falls_back_to_the_city_factor_without_a_building():
    """Sem prédio conhecido não há o que melhorar, e o tier já é rua ou bairro."""
    area, origem = reference_area(
        80.0, profile=None, median_unit_area=None, dispersion=None,
        peers=[], fallback_factor=1.6,
    )
    assert area == pytest.approx(128.0)
    assert origem == "fator"


def test_reference_area_falls_back_when_the_building_is_too_small_to_profile():
    """Menos de quatro unidades: sem quartil, sem perfil, sem posto."""
    area, origem = reference_area(
        80.0, profile=None, median_unit_area=110.0, dispersion=None,
        peers=[80.0], fallback_factor=1.6,
    )
    assert area == pytest.approx(110.0)
    assert origem == "predio_mediana"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_domain/test_unit_area.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.unit_area'`.

- [ ] **Step 3: Escrever o módulo**

Criar `app/domain/unit_area.py`:

```python
"""A área do anúncio em espaço de cadastro, que é o espaço do ITBI.

O cartório lança "Área Construída Adquirida" e o portal anuncia área útil, e as
duas nunca foram a mesma coisa. O que faltava saber é que a primeira é *exata*:
medida contra o cadastro imobiliário no mesmo endereço, em 40.561 linhas, a
razão entre elas é 1,000 na mediana (p25 0,995, p75 1,013). São a mesma régua,
da mesma prefeitura.

O que varia é a conversão para a área anunciada, e ela varia por prédio: de 1,00
no p10 a 2,13 no p90. Tratá-la como uma constante da cidade custa 18,4% de erro
mediano e 42,4% no p90 — a mesma ordem de grandeza do desconto que o produto
chama de oportunidade, e o maior termo de erro do sistema.

A saída é não converter. Onde o prédio é conhecido, a área que multiplica o
R$/m² do ITBI vem do cadastro, e a conversão desaparece dos dois lados da conta.
Medido em 652 anúncios: o erro p90 de prever o preço pedido cai de 67,9% para
42,6%. A mediana quase não se move, porque a calibração já comia o viés central
— é a cauda que a conversão fabricava, e é a cauda que vira alerta falso.
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Sequence

# Acima disso as unidades do prédio discordam o bastante para que a mediana
# esteja descrevendo um apartamento que ninguém tem. Medida no cadastro, a
# dispersão interquartil das áreas de um endereço tem mediana 0,09 e 76% dos
# prédios ficam abaixo deste corte.
HOMOGENEOUS_DISPERSION = 0.30

ORIGEM_MEDIANA = "predio_mediana"
ORIGEM_POSTO = "predio_posto"
ORIGEM_FATOR = "fator"


def rank_of(value: float, peers: Sequence[float]) -> float:
    """Posição do valor entre os seus pares, de 0 a 1.

    O anúncio sozinho no prédio recebe 0,5: não há posto a medir, e a mediana é
    a resposta menos errada. O posto é sobre as áreas *anunciadas*, então a
    definição de área é a mesma nos dois lados da comparação e se cancela — que
    é a única forma de usar área anunciada sem reintroduzir o erro.
    """
    ordenados = sorted(peers)
    if len(ordenados) < 2:
        return 0.5
    return bisect_left(ordenados, value) / (len(ordenados) - 1)


def area_at_rank(profile: Sequence[float], rank: float) -> float:
    """A área do cadastro naquele posto, interpolada entre os decis."""
    ordenado = sorted(profile)
    ultimo = len(ordenado) - 1
    if ultimo <= 0:
        return float(ordenado[0])
    posicao = min(max(rank, 0.0), 1.0) * ultimo
    baixo = int(posicao)
    if baixo >= ultimo:
        return float(ordenado[ultimo])
    resto = posicao - baixo
    return float(ordenado[baixo] + (ordenado[baixo + 1] - ordenado[baixo]) * resto)


def reference_area(
    area_anunciada: float,
    *,
    profile: Sequence[float] | None,
    median_unit_area: float | None,
    dispersion: float | None,
    peers: Sequence[float],
    fallback_factor: float,
) -> tuple[float, str]:
    """A área a usar contra o ITBI, e de onde ela veio.

    Três caminhos, do melhor ao pior:

    1. prédio conhecido cujas unidades concordam — a mediana do cadastro;
    2. prédio conhecido cujas unidades discordam — a área do cadastro no mesmo
       posto que o anúncio ocupa entre os anúncios daquele prédio;
    3. prédio desconhecido — a conversão de cidade, como antes. Sem prédio não
       há o que melhorar, e nesse caso o tier já é rua ou bairro.
    """
    concorda = dispersion is not None and dispersion <= HOMOGENEOUS_DISPERSION
    if median_unit_area and (concorda or not profile or len(profile) < 2):
        return float(median_unit_area), ORIGEM_MEDIANA
    if profile and len(profile) >= 2:
        return area_at_rank(profile, rank_of(area_anunciada, peers)), ORIGEM_POSTO
    if median_unit_area:
        return float(median_unit_area), ORIGEM_MEDIANA
    return float(area_anunciada) * fallback_factor, ORIGEM_FATOR
```

- [ ] **Step 4: Rodar o teste**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_domain/test_unit_area.py -v`
Expected: PASS, sete testes.

- [ ] **Step 5: Commit**

```bash
git add app/domain/unit_area.py tests/test_domain/test_unit_area.py
git commit -m "feat: resolve a área do anúncio no espaço que o cadastro mede"
```

---

### Task 8: A estimativa passa a multiplicar a área de referência

**Files:**
- Modify: `app/domain/opportunities.py:236-256` (`ListingInput`), `:520-527` (`itbi_area_for`), `:559-616` (`select_reference`), `:440-518` (`build_calibration`), `:851-900` (`compute_opportunity`), `:800-840` (`_motivos`)
- Test: `tests/test_services/test_opportunities.py`

**Interfaces:**
- Consumes: `reference_area`, `ORIGEM_FATOR` (Tarefa 7).
- Produces: `ListingInput.predio_area_profile: list[float] | None`, `ListingInput.predio_area_mediana: float | None`, `ListingInput.predio_areas_anunciadas: tuple[float, ...]`; `Opportunity.area_referencia: float` e `Opportunity.area_referencia_origem: str`; a função `listing_reference_area(listing) -> tuple[float, str] | None`.

- [ ] **Step 1: Escrever o teste que falha**

Em `tests/test_services/test_opportunities.py`:

```python
def test_estimate_uses_the_registry_area_not_the_converted_one():
    """A área do ITBI é a do cadastro (razão 1,000 em 40.561 linhas), então o
    preço sai da área do cadastro e a conversão some da conta."""
    vendas = [
        _venda(street="Rua dos Timbiras", numero="100", area=140, valor=1_400_000),
        _venda(street="Rua dos Timbiras", numero="100", area=145, valor=1_450_000),
        _venda(street="Rua dos Timbiras", numero="100", area=142, valor=1_420_000),
    ]
    anuncio = ListingInput(
        source="quintoandar",
        listing_id="1",
        tipo_imovel="Apartamento",
        area_util_m2=85.0,
        preco_total=1_000_000.0,
        bairro="Funcionários",
        rua="Rua dos Timbiras",
        numero="100",
        predio_dispersao_area=0.08,
        predio_area_mediana=142.0,
        predio_area_profile=[138.0, 140.0, 142.0, 144.0, 145.0],
    )
    oportunidade = compute_opportunity(
        anuncio, vendas, None, Calibration.flat(1.0)
    )
    assert oportunidade is not None
    assert oportunidade.area_referencia == pytest.approx(142.0)
    assert oportunidade.area_referencia_origem == "predio_mediana"
    # R$/m2 mediano de 10.000 x 142 m2 do cadastro x fator 1,0
    assert oportunidade.preco_estimado_itbi == pytest.approx(1_420_000, rel=1e-3)


def test_estimate_falls_back_to_the_city_factor_without_a_building():
    """Sem cadastro o comportamento é o de antes, e o tier já é rua ou bairro."""
    vendas = [
        _venda(street="Rua dos Timbiras", numero=str(n), area=140, valor=1_400_000)
        for n in range(1, 8)
    ]
    anuncio = ListingInput(
        source="loft",
        listing_id="2",
        tipo_imovel="Apartamento",
        area_util_m2=85.0,
        preco_total=1_000_000.0,
        bairro="Funcionários",
        rua="Rua dos Timbiras",
    )
    oportunidade = compute_opportunity(anuncio, vendas, None, Calibration.flat(1.0))
    assert oportunidade is not None
    assert oportunidade.area_referencia_origem == "fator"
    assert oportunidade.area_referencia == pytest.approx(85.0 * AREA_MATCH_FACTOR)
```

Reaproveitar o helper de venda que o arquivo já tem; se ele se chamar outra coisa, usar o nome real. Importar `AREA_MATCH_FACTOR` e `pytest`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_services/test_opportunities.py -v -k registry_area`
Expected: FAIL — `TypeError: ListingInput.__init__() got an unexpected keyword argument 'predio_area_mediana'`.

- [ ] **Step 3: Somar os campos ao `ListingInput`**

Em `app/domain/opportunities.py`, dentro de `ListingInput`, junto de `predio_dispersao_area`:

```python
    # A mediana e os decis das áreas das unidades do prédio, do cadastro
    # imobiliário. É a área que o ITBI mede — a mesma régua, razão 1,000 —, e é
    # ela que multiplica o R$/m², em vez da área anunciada convertida.
    predio_area_mediana: float | None = None
    predio_area_profile: tuple[float, ...] | None = None
    # As áreas que os anúncios ativos daquele prédio publicam. Servem só para o
    # posto: comparar área anunciada com área anunciada cancela a definição.
    predio_areas_anunciadas: tuple[float, ...] = ()
```

- [ ] **Step 4: Escrever `listing_reference_area` e usá-la nos dois lugares**

Em `app/domain/opportunities.py`, importar no topo:

```python
from app.domain.unit_area import ORIGEM_FATOR, reference_area
```

Somar, ao lado de `itbi_area_for`:

```python
def listing_reference_area(listing: ListingInput) -> tuple[float, str] | None:
    """A área deste anúncio em espaço de cadastro, e de onde ela veio."""
    area = _positive(listing.area_util_m2)
    if area is None:
        return None
    return reference_area(
        area,
        profile=listing.predio_area_profile,
        median_unit_area=listing.predio_area_mediana,
        dispersion=listing.predio_dispersao_area,
        peers=listing.predio_areas_anunciadas or (area,),
        fallback_factor=AREA_MATCH_FACTOR,
    )
```

Marcar `itbi_area_for` como o caminho antigo, mantendo-a só para o fallback:

```python
def itbi_area_for(area: float) -> float:
    """Conversão de cidade, usada só onde o prédio é desconhecido.

    Ela é a fonte do maior termo de erro que o sistema tinha (18,4% mediano,
    42,4% no p90), porque a razão real varia de 1,00 a 2,13 entre prédios.
    `listing_reference_area` a evita sempre que o cadastro conhece o prédio.
    """
    return area * AREA_MATCH_FACTOR
```

Em `select_reference`, trocar o bloco que calcula `esperada` por:

```python
    # A janela tem de ficar onde o cartório registra esta unidade. Com o prédio
    # conhecido isso não é mais uma conversão, é a própria área do cadastro.
    resolvida = listing_reference_area(listing)
    esperada = resolvida[0] if resolvida else None
```

Em `build_calibration`, trocar `ratio = (price / area) / reference.preco_m2_mediano` por:

```python
        resolvida = listing_reference_area(listing)
        if resolvida is None:
            continue
        area_ref, _origem = resolvida
        # O fator é medido na mesma área que a estimativa multiplica. Enquanto
        # ele era medido em área anunciada e aplicado sobre R$/m² de área
        # construída, ele carregava a conversão junto — e era isso que fazia o
        # fator parecer variar com o tamanho do imóvel (2,55x abaixo de 60 m²
        # contra 1,27x acima de 250 m²). A razão entre esses dois é 2,01, e a
        # razão entre a conversão de área nas mesmas faixas é 1,98: era o mesmo
        # número, medido duas vezes.
        ratio = (price / area_ref) / reference.preco_m2_mediano
```

Em `compute_opportunity`, depois de obter `reference`:

```python
    resolvida = listing_reference_area(listing)
    if resolvida is None:
        return None
    area_referencia, area_referencia_origem = resolvida
```

e trocar o cálculo do preço:

```python
    preco_m2_esperado = reference.preco_m2_mediano * fator
    preco_estimado = round(preco_m2_esperado * area_referencia, 2)
```

Somar os dois campos ao `Opportunity` (`area_referencia: float = 0.0`, `area_referencia_origem: str = ORIGEM_FATOR`) e preenchê-los no `return`.

Em `_motivos`, receber `area_referencia` e `area_referencia_origem` e trocar as duas últimas frases por:

```python
    if area_referencia_origem == ORIGEM_FATOR:
        onde_area = (
            f"Área comparada por conversão de cidade ({AREA_MATCH_FACTOR}x): "
            f"{_area(area)} anunciados viram {_area(area_referencia)} construídos."
        )
    else:
        onde_area = (
            f"Área da unidade no cadastro da prefeitura: {_area(area_referencia)} "
            f"construídos, a mesma régua do ITBI — sem conversão."
        )
    motivos = [
        f"Mediana de {reference.amostra_count} ITBIs residenciais por {onde}.",
        f"Janela de {WINDOW_MONTHS} meses entre "
        f"{reference.referencia_data_inicio.isoformat()} e "
        f"{reference.referencia_data_fim.isoformat()}.",
        f"ITBI de {_money(reference.preco_m2_mediano)}/m² construído ajustado pelo "
        f"fator {fator:.2f}x de prêmio de anúncio, chegando a "
        f"{_money(preco_m2_esperado)}/m².",
        onde_area,
    ]
```

- [ ] **Step 5: Rodar o teste e a suíte**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_services/test_opportunities.py -v`
Expected: PASS. Outros testes do arquivo podem quebrar por causa da mudança de estimativa — corrigir os números esperados, não a lógica, e só depois de conferir à mão que o novo número é o certo.

Run: `PYTHONPATH=. .venv/bin/pytest -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/domain/opportunities.py tests/test_services/test_opportunities.py
git commit -m "feat: a estimativa multiplica a área do cadastro, não a área convertida"
```

---

### Task 9: O serviço alimenta o prédio e as áreas dos vizinhos

**Files:**
- Modify: `app/services/opportunities.py:196-268` (`fetch_registry_buildings`, `_building`, `_listing_input`), `:474-560` (`refresh_opportunities`)
- Modify: `app/models/market_comparable.py` + `alembic/versions/0021_area_referencia.py`
- Test: `tests/test_services/test_opportunities.py`

**Interfaces:**
- Consumes: `Building.unit_area_profile` (Tarefa 2), `listing_reference_area` (Tarefa 8).
- Produces: colunas `market_comparables.area_referencia` (Numeric(10,2)) e `area_referencia_origem` (String(20)); `_building_listing_areas(listings) -> dict[tuple[str, str], tuple[float, ...]]`.

- [ ] **Step 1: Escrever o teste que falha**

Em `tests/test_services/test_opportunities.py`:

```python
def test_refresh_records_the_reference_area_and_its_origin(db_session):
    """A tela e a validação precisam saber qual área respondeu."""
    _seed_registry(db_session, street="Rua dos Timbiras", numero="100",
                   mediana=142.0, dispersao=0.08, perfil=[138.0, 142.0, 145.0])
    _seed_itbi(db_session, street="Rua dos Timbiras", numero="100", n=3,
               area=142, valor=1_420_000)
    _seed_listing(db_session, source="vivareal", rua="Rua dos Timbiras",
                  numero="100", area=85.0, preco=1_000_000.0)

    refresh_opportunities(db_session, cidade="Belo Horizonte", sem_qpreco=True)

    linha = db_session.query(MarketComparable).one()
    assert float(linha.area_referencia) == pytest.approx(142.0)
    assert linha.area_referencia_origem == "predio_mediana"
```

Escrever os helpers `_seed_registry`, `_seed_itbi` e `_seed_listing` seguindo os que o arquivo já usa; se equivalentes já existirem, usar os existentes em vez de duplicar.

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_services/test_opportunities.py -v -k reference_area`
Expected: FAIL — coluna inexistente.

- [ ] **Step 3: Colunas e migration**

Em `app/models/market_comparable.py`, junto de `fator_calibracao`:

```python
    # A área que respondeu, e de onde ela veio: `predio_mediana`,
    # `predio_posto` ou `fator`. Guardar a origem é o que permite medir depois
    # quanto o cadastro melhorou a estimativa, em vez de acreditar.
    area_referencia: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    area_referencia_origem: Mapped[str | None] = mapped_column(String(20), nullable=True)
```

Criar `alembic/versions/0021_area_referencia.py` com `revision = "0021"`, `down_revision = "0020"`, somando as duas colunas a `market_comparables`.

- [ ] **Step 4: Alimentar o `ListingInput`**

Em `app/services/opportunities.py`, somar:

```python
def _building_listing_areas(
    listings: list[MarketComparable],
) -> dict[tuple[str, str], tuple[float, ...]]:
    """Áreas anunciadas por prédio, para o casamento por posto.

    Só área anunciada entra aqui: o posto compara anúncio com anúncio, e é essa
    simetria que faz a definição de área se cancelar.
    """
    por_predio: dict[tuple[str, str], list[float]] = {}
    for item in listings:
        rua, numero = item.rua_normalizada, item.numero_normalizado
        area = _as_float(item.area_util_m2)
        if rua and numero and area and area > 0:
            por_predio.setdefault((rua, numero), []).append(area)
    return {chave: tuple(sorted(areas)) for chave, areas in por_predio.items()}
```

Em `_listing_input`, depois de resolver `predio`:

```python
        predio_area_mediana=predio.median_unit_area if predio else None,
        predio_area_profile=(
            tuple(predio.unit_area_profile)
            if predio and predio.unit_area_profile
            else None
        ),
        predio_areas_anunciadas=areas_por_predio.get((rua_chave, numero), ()),
```

passando `areas_por_predio` e a chave resolvida como argumentos. Em `refresh_opportunities`, calcular `areas_por_predio = _building_listing_areas(listings)` uma vez, antes do laço, e repassar.

Em `_materialize`, gravar as duas colunas novas a partir do `Opportunity`, e em `_clear`, zerá-las junto das demais.

- [ ] **Step 5: Rodar o teste e a suíte**

Run: `PYTHONPATH=. .venv/bin/pytest -v`
Expected: PASS.

Run: `PYTHONPATH=. .venv/bin/alembic upgrade head`
Expected: aplica `0021`.

- [ ] **Step 6: Recalcular e medir a cobertura da área do cadastro**

Run: `PYTHONPATH=. .venv/bin/python -m app.ingestion.cli opportunity-refresh --cidade "Belo Horizonte" --sem-qpreco`

Run:
```bash
docker exec -e PGPASSWORD=imovelradar imovel-radar-postgres-1 psql -U imovelradar -d imovelradar -tAX -F' | ' \
  -c "select area_referencia_origem, count(*) from market_comparables where ativo and nota is not null group by 1 order by 2 desc"
```
Expected: `predio_mediana` e `predio_posto` somam a maioria dos anúncios pontuados. Anotar os números.

- [ ] **Step 7: Commit**

```bash
git add app/services/opportunities.py app/models/market_comparable.py alembic/versions/0021_area_referencia.py tests/test_services/test_opportunities.py
git commit -m "feat: o cálculo recebe o formato do prédio e grava qual área respondeu"
```

---

## Fase E — Revalidar, e deixar o dado decidir

### Task 10: Medir o ganho e reescrever as constantes com o número novo

**Files:**
- Create: `scripts/medir_area_predio.py`
- Modify: `scripts/validar_referencia.py`, `scripts/validar_calibracao.py` (só o que quebrar por assinatura)
- Modify: `app/domain/opportunities.py` (`EXPECTED_ERROR`, `AREA_BANDS`)
- Modify: `Makefile`

**Interfaces:**
- Consumes: tudo das fases anteriores.
- Produces: `scripts/medir_area_predio.py`, que imprime a razão por prédio e o custo de assumi-la global; `EXPECTED_ERROR` remedido.

- [ ] **Step 1: Escrever o medidor**

Criar `scripts/medir_area_predio.py`, no molde de `scripts/medir_area_itbi.py`, que:
1. lê `registry_addresses`, `transactions` e `market_comparables` da cidade;
2. imprime a razão `area_cadastro / area_anunciada` por prédio (p10/p25/p50/p75/p90) e o erro de assumir a mediana global;
3. imprime essa razão por faixa de área anunciada, que é o que mostra se o "efeito tamanho" é de mercado ou de medida;
4. compara três réguas de previsão do preço pedido — área anunciada convertida, valor mediano da unidade, e R$/m² × área do cadastro — reportando p50, p75 e p90 de cada.

Os números que ele tem de reproduzir na base atual de BH estão na especificação, seções 2, 3 e 4. Se divergirem em mais de 2 pontos percentuais, **parar e investigar** antes de mexer em constante: a especificação foi medida em 2026-09-04 e o dado pode ter mudado, mas uma divergência grande é mais provavelmente um erro de junção.

- [ ] **Step 2: Rodar as três medidas**

Run: `PYTHONPATH=. .venv/bin/python scripts/medir_area_predio.py --cidade "Belo Horizonte"`
Expected: razão por prédio com p50 ≈ 1,70; razão caindo de ≈1,98 (<60 m²) para ≈1,00 (>180 m²); régua C com p90 ≈ 42%.

- [ ] **Step 3: Revalidar a escada e a calibração**

Run: `PYTHONPATH=. .venv/bin/python scripts/validar_referencia.py --cidade "Belo Horizonte"`
Run: `PYTHONPATH=. .venv/bin/python scripts/validar_calibracao.py --cidade "Belo Horizonte"`

Anotar, para cada tier e faixa de dispersão, o erro mediano novo. É esta tabela que substitui `EXPECTED_ERROR`.

- [ ] **Step 4: Reescrever `EXPECTED_ERROR` com o medido**

Substituir a tabela em `app/domain/opportunities.py` pelos números da Step 3, mantendo o comentário que diz de onde eles vieram e trocando a data. Não inventar célula: onde a amostra for rasa, herdar o valor do tier, como o comentário atual já documenta com o asterisco.

- [ ] **Step 5: Decidir sobre `AREA_BANDS` com o dado**

Rodar `validar_calibracao.py` duas vezes: uma como está, outra com `AREA_BANDS = ()` (fator sem faixa de área). Comparar o erro mediano e o p90.

- Se o erro **não piorar** além de 1 ponto percentual sem as faixas, remover `AREA_BANDS` e as entradas `by_band` / `by_city_band` da `Calibration`, deixando `by_band_finish` virar `by_finish`. O comentário que fica registra que as faixas eram a conversão de área disfarçada, com os dois números lado a lado (2,01 e 1,98).
- Se **piorar**, mantê-las e escrever no comentário quanto elas ainda valem depois da correção, com o número. A especificação previu o colapso; o dado é quem decide.

- [ ] **Step 6: Rodar a suíte e o ciclo inteiro**

Run: `PYTHONPATH=. .venv/bin/pytest -v`
Expected: PASS.

Run: `PYTHONPATH=. .venv/bin/python -m app.ingestion.cli opportunity-refresh --cidade "Belo Horizonte" --sem-qpreco`
Expected: o volume de alertas (nota ≥ 80) fica na mesma ordem de grandeza de antes. Uma explosão ou um colapso é sinal de constante errada, não de descoberta — investigar antes de seguir.

- [ ] **Step 7: `make validar` cobre o novo medidor**

No `Makefile`, somar `scripts/medir_area_predio.py` ao alvo `validar`.

- [ ] **Step 8: Commit**

```bash
git add scripts/medir_area_predio.py scripts/validar_referencia.py scripts/validar_calibracao.py app/domain/opportunities.py Makefile
git commit -m "perf: recalibra o erro esperado sobre a área que o cadastro mede"
```

---

## Fase F — Qualidade do prédio pelas duas pontas

### Task 11: Cruzar as instalações do portal com o padrão do cadastro

**Files:**
- Modify: `app/domain/opportunities.py` (`ListingInput`, `build_calibration`)
- Modify: `app/services/opportunities.py` (`_listing_input`)
- Test: `tests/test_services/test_opportunities.py`

**Interfaces:**
- Consumes: `PortalBuilding.installations` (Tarefa 4), `Building.finish_standard` (já existe).
- Produces: `ListingInput.predio_instalacoes: tuple[str, ...]`; `building_quality(finish_standard, installations) -> str | None`.

- [ ] **Step 1: Escrever o teste que falha**

```python
from app.domain.opportunities import building_quality


def test_building_quality_prefers_the_registry_standard():
    """O padrão de acabamento é a única variável de qualidade que o ITBI e o
    cadastro medem do mesmo jeito — quando ele existe, é ele que responde."""
    assert building_quality("P4", ("PISCINA", "ACADEMIA")) == "P4"


def test_building_quality_falls_back_to_the_portal_installations():
    """Sem cadastro, a contagem de instalações do portal é o que sobra. Os
    cortes seguem a distribuição do próprio padrão: prédio sem elevador nem
    portaria é o de baixo, prédio com lazer completo é o de cima."""
    assert building_quality(None, ()) == "I0"
    assert building_quality(None, ("ELEVADOR", "PORTARIA_24H")) == "I2"
    assert building_quality(
        None, ("ELEVADOR", "PORTARIA_24H", "PISCINA", "ACADEMIA", "SALAO_DE_FESTAS")
    ) == "I5"


def test_building_quality_is_none_without_either_source():
    assert building_quality(None, None) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_services/test_opportunities.py -v -k building_quality`
Expected: FAIL — `ImportError: cannot import name 'building_quality'`.

- [ ] **Step 3: Escrever a função e ligá-la à calibração**

Em `app/domain/opportunities.py`:

```python
# Quantas instalações o portal lista para o prédio, agrupadas. Serve só onde o
# cadastro não alcança: o padrão de acabamento é a mesma variável medida pelo
# ITBI e pelo cadastro, e ela ganha sempre que existe.
INSTALLATION_BANDS = (1, 2, 3, 5)


def building_quality(
    finish_standard: str | None, installations: Sequence[str] | None
) -> str | None:
    """Uma etiqueta de qualidade do prédio, da melhor fonte disponível."""
    if finish_standard:
        return finish_standard
    if installations is None:
        return None
    quantas = len(installations)
    return f"I{bisect_right(INSTALLATION_BANDS, quantas)}" if quantas == 0 else (
        f"I{quantas if quantas <= 5 else 5}"
    )
```

Ajustar a implementação até os quatro testes passarem — o contrato são os testes, não este esboço.

Somar `predio_instalacoes: tuple[str, ...] = ()` ao `ListingInput`, e em `build_calibration` trocar `listing.predio_padrao_acabamento` por
`building_quality(listing.predio_padrao_acabamento, listing.predio_instalacoes)`,
fazendo o mesmo na chamada `calibration.factor(...)` de `compute_opportunity`.

Em `app/services/opportunities.py`, `_listing_input` passa a preencher
`predio_instalacoes` a partir do `PortalBuilding` resolvido na Tarefa 6.

- [ ] **Step 4: Rodar e medir se vale**

Run: `PYTHONPATH=. .venv/bin/pytest -v`
Expected: PASS.

Run: `PYTHONPATH=. .venv/bin/python scripts/validar_calibracao.py --cidade "Belo Horizonte"`

**Se o erro não melhorar, reverter esta tarefa.** O padrão de acabamento derrubou o erro de 19,9% para 16,9% no tier de endereço quando entrou; uma segunda variável de qualidade que não move o número é complexidade sem retorno, e o repositório já tem o hábito de remover o que não paga.

- [ ] **Step 5: Commit**

```bash
git add app/domain/opportunities.py app/services/opportunities.py tests/test_services/test_opportunities.py
git commit -m "feat: qualidade do prédio pelas duas pontas, cadastro e portal"
```

---

### Task 12: README e o ciclo agendado

**Files:**
- Modify: `README.md`
- Modify: `scheduler.sh`
- Modify: `.env.example`

- [ ] **Step 1: Reescrever a seção de área do README**

As seções "Como o valor estimado é calculado" e "Quanto a referência erra" descrevem hoje uma conversão que deixou de existir no caminho principal. Reescrevê-las com:

- a medida de que a área do ITBI **é** a do cadastro (razão 1,000 em 40.561 linhas);
- a razão por prédio (p10 1,00 / p50 1,70 / p90 2,13) e o custo de 18,4% / 42,4% de assumi-la global;
- a tabela das três réguas (67,9% → 42,0% no p90);
- o que a Tarefa 10 decidiu sobre `AREA_BANDS`, com o número;
- a nova escada de resolução de número: anúncio → `condoId` → diretório de condomínios → cadastro, com os 83% e os 8 m;
- em "Limitações", remover "QuintoAndar e Loft não publicam o número da rua" e pôr no lugar o que sobrou: cobertura do diretório e o que acontece com o prédio que ele não conhece.

Somar a seção de comando:

```bash
# Diretório de condomínios do portal: o número da rua que o anúncio não publica.
PYTHONPATH=. python -m app.ingestion.cli condo-sync --cidade belo_horizonte --limit 500
```

- [ ] **Step 2: Somar ao ciclo agendado**

Em `scheduler.sh`, chamar `condo-sync` uma vez por ciclo, com teto, **depois** da varredura de anúncios (ela é quem cria a demanda) e **antes** do `opportunity-refresh`. Uma falha ali não derruba o loop, no mesmo padrão das outras etapas.

Em `.env.example`, somar `CONDO_MIN_INTERVAL_SECONDS=1.0` e `CONDO_LIMIT=500`, cada um com a linha de comentário que explica o que ele protege.

- [ ] **Step 3: Rodar a suíte inteira uma última vez**

Run: `PYTHONPATH=. .venv/bin/pytest -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md scheduler.sh .env.example
git commit -m "docs: a área do cadastro e o diretório de condomínios no README"
```

---

## Auto-revisão

**Cobertura da especificação:**

| seção da spec | tarefa |
| --- | --- |
| 1 — área do ITBI é a do cadastro | 7, 8 (fundamento) |
| 2 — razão por prédio | 7, 8, 10 |
| 3 — efeito tamanho é artefato | 8 (fator na mesma área), 10 (decisão sobre `AREA_BANDS`) |
| 4 — tirar área corta a cauda | 7, 8, 9, 10 |
| 5 — IPTU rejeitado | D4: nada a implementar |
| 6 — campos livres da busca | 1 |
| 7 — diretório de condomínios | 3, 4, 5 |
| 8 — cadeia de identidade | 6 |
| D1 — área de referência | 7, 8, 9 |
| D2 — perfil de área | 2 |
| D3 — coleta sob demanda | 5 |

**Consistência de tipos:** `unit_area_profile` é `list[float] | None` no `RegistryRow`, no modelo e no `Building`; vira `tuple[float, ...] | None` na fronteira do `ListingInput`, porque ele é `frozen`. A conversão está explícita na Tarefa 9, Step 4. `reference_area` devolve `tuple[float, str]` em todos os caminhos e nunca `None` — quem pode devolver `None` é `listing_reference_area`, e só quando a área do anúncio é ausente ou não positiva.

**Riscos anotados:**
- A Tarefa 8 muda todos os preços estimados da base. Os testes existentes de `test_opportunities.py` vão quebrar em números; a instrução é conferir à mão antes de reescrever cada expectativa.
- A Tarefa 5 depende de um sitemap de terceiro. Se o formato mudar, `sitemap_parts` devolve lista vazia e o serviço reporta zero alvos — falha silenciosa, não exceção. A Step 6 da Tarefa 5 é o que a pega.
- A Tarefa 11 tem instrução explícita de reverter se não pagar.
