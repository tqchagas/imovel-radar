# Avaliação de imóvel de leilão — plano de implementação

**Objetivo:** dar, para um imóvel digitado à mão, duas leituras independentes de
valor de mercado — a estimativa da Calculadora QPreço e a mediana dos
comparáveis que o portal reporta como vendidos — com a divergência entre elas
servindo de sinal de confiança, e o ITBI entrando como terceira conferência em
Belo Horizonte.

**Arquitetura:** um cliente HTTP para os dois endpoints públicos do
`brand-calculator`, no molde de `app/pricing/similar_houses.py`; um módulo puro
que filtra os comparáveis e calcula a divergência; uma tabela por imóvel com
histórico de consultas; e uma tela estática `/leilao` no padrão das demais.

**Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Postgres 16, pytest,
HTML+JS estático.

**Spec:** `docs/superpowers/specs/2026-09-04-avaliacao-leilao-design.md`

## Restrições globais

- Comentários e docstrings em **português**, explicando o porquê com o número
  medido junto, no tom dos módulos vizinhos.
- **`save-lead` nunca é chamado.** Nenhum dado pessoal viaja para o portal.
- Ritmo de 3 s entre requisições (`QPRECO_CALC_MIN_INTERVAL_SECONDS`), circuit
  breaker em 401/403/429, TTL de 30 dias — mesmo desenho de `similar_houses.py`.
- Cidade livre: nada pode assumir Belo Horizonte. O cruzamento com ITBI e
  cadastro é opcional e a ausência dele não altera o resultado principal.
- `pytest -v` passa inteiro ao fim de cada tarefa. Testes rodam em SQLite e
  Postgres: nada de tipo só-Postgres sem fallback.
- Migration com o prefixo seguinte ao último aplicado (`0020_portal_buildings`).
- Commits no estilo do repositório (`feat:`, `fix:`, `docs:`), assunto em
  português, no imperativo.

## Estrutura de arquivos

**Criar**
- `app/pricing/qpreco_calculadora.py` — cliente dos dois endpoints
- `app/domain/appraisal.py` — filtro de comparáveis, mediana, divergência (puro)
- `app/models/auction_property.py` — `AuctionProperty` e `AuctionAppraisal`
- `app/services/appraisal.py` — orquestra coordenada, chamadas e gravação
- `app/api/routes/auctions.py` — CRUD e reavaliação
- `app/static/leilao.html`, `app/static/leilao.js`
- `alembic/versions/0021_auction_properties.py`
- `tests/test_pricing/test_qpreco_calculadora.py`
- `tests/test_domain/test_appraisal.py`
- `tests/test_services/test_appraisal.py`

**Modificar**
- `app/main.py` (`PAGES` e `include_router`), `app/ingestion/cli.py`,
  `Makefile`, `README.md`, `.env.example`

---

## Tarefa 1 — Cliente da Calculadora QPreço

**Arquivos:** criar `app/pricing/qpreco_calculadora.py` e
`tests/test_pricing/test_qpreco_calculadora.py`

**Produz**
- `EstimateInput` (frozen): `address`, `address_number`, `neighborhood`, `city`,
  `state`, `country`, `latitude`, `longitude`, `house_type`, `total_area`,
  `bedroom_count`, `bathroom_count`, `suites_count`, `parking_slots`, `floor`,
  `condominium_per_month`, `iptu_per_year`
- `Estimate` (frozen): `suggested_price`, `lower_bound`, `upper_bound`,
  `limit_lower`, `limit_upper`, `certainty`, `percentiles: dict[int, float]`
- `SoldComparable` (frozen): `house_id`, `price`, `price_m2`, `total_area`,
  `bedroom_count`, `parking_slots`, `distance_km`, `sold_at: date | None`,
  `address`, `neighborhood`, `city`, `same_condo`
- `Comparables` (frozen): `sold: tuple[SoldComparable, ...]`,
  `available: tuple[SoldComparable, ...]`, `same_condo: tuple[...]`,
  `on_market_m2`, `off_market_m2`, `days_until_deal`
- `fetch_estimate(entrada, *, request_fn=default_request) -> Estimate`
- `fetch_comparables(entrada, estimate, *, request_fn=default_request) -> Comparables`
- `QprecoUnavailable` — erguida quando o portal responde sem `suggestedPrice`

- [ ] **Passo 1: teste que falha**

```python
def test_estimate_le_a_faixa_e_a_certeza():
    """`predictionCertainty` é sinal de primeira classe: medido ao vivo, ele
    volta "low" em Itabirito e "medium" em Vila Madalena."""
    resposta = _Resposta(200, {
        "suggestedPrice": 4513000, "suggestedLowerBoundPrice": 3817000,
        "suggestedUpperBoundPrice": 5112000, "lowerBoundLimit": 2903000,
        "upperBoundLimit": 6046500, "predictionCertainty": "low",
        "percentiles": {"10": 2903000, "20": 0, "50": 4513000, "90": 6046500},
    })
    e = fetch_estimate(ENTRADA, request_fn=lambda *a, **k: resposta)

    assert e.suggested_price == 4513000
    assert e.certainty == "low"
    # O portal devolve 0 nos decis que não calcula; guardar zero é guardar mentira.
    assert 20 not in e.percentiles
    assert e.percentiles[50] == 4513000


def test_estimate_sem_preco_e_indisponivel():
    """Sem coordenada o portal responde 200 dizendo que não conseguiu. É a
    mesma resposta que ele dá para imóvel atípico — não dá para distinguir, e
    inventar um número seria pior."""
    resposta = _Resposta(200, {"suggestedPrice": None})
    with pytest.raises(QprecoUnavailable):
        fetch_estimate(ENTRADA, request_fn=lambda *a, **k: resposta)


def test_estimate_nunca_chama_save_lead():
    urls = []
    fetch_estimate(ENTRADA, request_fn=_gravando(urls))
    assert not any("save-lead" in u for u in urls)


def test_comparables_separa_vendidos_de_disponiveis():
    """`unavailableSimilarHouses` é preço de transação, com data e endereço —
    é o dado que a escada de ITBI existe para reconstruir."""
    c = fetch_comparables(ENTRADA, ESTIMATIVA, request_fn=lambda *a, **k: _Resposta(200, PAYLOAD_SIMILARES))

    assert len(c.sold) == 2
    primeiro = c.sold[0]
    assert primeiro.price == 3100000
    assert primeiro.price_m2 == 10333
    assert primeiro.sold_at == date(2026, 4, 17)
    assert primeiro.distance_km == pytest.approx(0.4838, abs=1e-4)
    assert primeiro.same_condo is False


def test_comparables_usa_os_percentis_da_estimativa_na_faixa():
    """A faixa de preço filtra os comparáveis do lado do portal. Mandar a faixa
    da própria estimativa é o que a tela faz, e é o que mantém a resposta
    comparável com a dela."""
    corpos = []
    fetch_comparables(ENTRADA, ESTIMATIVA, request_fn=_gravando_corpo(corpos))
    assert corpos[0]["percentile10"] == ESTIMATIVA.limit_lower
    assert corpos[0]["percentile90"] == ESTIMATIVA.limit_upper


def test_bloqueio_do_portal_aborta():
    for status in (401, 403, 429):
        with pytest.raises(PortalBlocked):
            fetch_estimate(ENTRADA, request_fn=lambda *a, **k: _Resposta(status, {}))
```

- [ ] **Passo 2: rodar e ver falhar**

`PYTHONPATH=. .venv/bin/pytest tests/test_pricing/test_qpreco_calculadora.py -v`
Esperado: `ModuleNotFoundError`.

- [ ] **Passo 3: escrever o cliente**

Cabeçalho do módulo, que é onde o porquê tem de morar:

```python
"""A Calculadora QPreço: o modelo do QuintoAndar sobre um endereço, não sobre um anúncio.

O `price-suggestion` que este projeto já usa resolve tudo pelo id do anúncio e
responde 404 para qualquer outra coisa — medido: coordenada e atributos sem id
devolvem `"House null was not found"`. Imóvel de leilão nunca tem id.

O produto "quanto vale meu imóvel" roda o mesmo modelo a partir de atributos, e
são dois endpoints públicos que respondem sem cookie e sem sessão. A tela deles
dispara ainda um `save-lead`, que registra o interessado no funil; ele é
separado e **não é chamado aqui**.

Coordenada é obrigatória. Sem ela o portal responde 200 dizendo que não
conseguiu calcular — a mesma resposta que dá para imóvel genuinamente atípico —,
e uma coordenada errada por duzentos metros não falha: devolve um número
plausível do quarteirão vizinho. Por isso ela é digitada e conferida por gente,
nunca geocodificada em silêncio.
"""

URL_ESTIMATE = "https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/brand-calculator/estimate"
URL_SIMILARES = "https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/brand-calculator/similar-houses"

MIN_INTERVAL_SECONDS = float(os.getenv("QPRECO_CALC_MIN_INTERVAL_SECONDS", "3.0"))
BLOCKED_STATUS = frozenset({401, 403, 429})

HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://proprietario.quintoandar.com.br",
    "referer": "https://proprietario.quintoandar.com.br/",
}
```

`_percentis` descarta as chaves cujo valor é zero — o portal devolve `0` nos
decis que não calcula, e guardar zero é guardar mentira. `sold_at` sai de
`lastTimeOnMarket` por `date.fromisoformat(valor[:10])`, tolerando ausência.

- [ ] **Passo 4: rodar os testes** — todos passam.

- [ ] **Passo 5: conferir contra o portal de verdade**

```bash
PYTHONPATH=. .venv/bin/python -c "
from app.pricing.qpreco_calculadora import EstimateInput, fetch_estimate, fetch_comparables
e = EstimateInput(address='Rua Gonçalves Dias', address_number=865, neighborhood='Funcionários',
                  city='Belo Horizonte', state='MG', country='Brasil',
                  latitude=-19.932468, longitude=-43.933033, house_type='APARTMENT',
                  total_area=295, bedroom_count=4, bathroom_count=3, suites_count=2,
                  parking_slots=2, floor=8, condominium_per_month=1500, iptu_per_year=4800)
est = fetch_estimate(e); print(est.suggested_price, est.certainty)
cmp = fetch_comparables(e, est); print(len(cmp.sold), 'vendidos')
"
```
Esperado: `4513000 low` e `10 vendidos`. Números diferentes são aceitáveis (o
modelo deles se move); estrutura diferente **não** é — nesse caso, parar.

- [ ] **Passo 6: commit** — `feat: cliente da Calculadora QPreço, que precifica endereço sem anúncio`

---

## Tarefa 2 — O que os vendidos dizem

**Arquivos:** criar `app/domain/appraisal.py` e `tests/test_domain/test_appraisal.py`

**Consome:** `SoldComparable`, `Estimate` da Tarefa 1.

**Produz**
- `AREA_TOLERANCE = 0.20`, `MAX_DISTANCE_KM = 1.0`, `DIVERGENCE_ALERT = 0.15`
- `comparaveis_uteis(sold, *, area, quartos) -> tuple[SoldComparable, ...]`
- `mediana_dos_vendidos(uteis, area) -> float | None`
- `Appraisal` (frozen): `preco_qpreco`, `preco_vendidos`, `divergencia_pct`,
  `atipico: bool`, `certeza`, `comparaveis_usados: int`
- `avaliar(estimate, sold, *, area, quartos) -> Appraisal`

- [ ] **Passo 1: teste que falha**

```python
def test_filtra_por_area_quartos_e_distancia():
    """A janela existe para não comparar quarto-e-sala com cobertura. ±20% de
    área, mesmo número de quartos, até 1 km."""
    uteis = comparaveis_uteis([
        _v(area=100, quartos=3, dist=0.4),    # entra
        _v(area=125, quartos=3, dist=0.4),    # área fora de ±20%
        _v(area=100, quartos=2, dist=0.4),    # outro número de quartos
        _v(area=100, quartos=3, dist=1.4),    # longe demais
    ], area=100, quartos=3)
    assert len(uteis) == 1


def test_quartos_ausentes_nao_eliminam_o_comparavel():
    """Metade dos vendidos volta com `bedroomCount` nulo — medido ao vivo, 5 de
    6 numa consulta. Descartá-los esvaziaria a amostra; eles entram pela área."""
    uteis = comparaveis_uteis([_v(area=100, quartos=None, dist=0.3)], area=100, quartos=3)
    assert len(uteis) == 1


def test_mediana_e_por_m2_e_nao_por_preco():
    """Os comparáveis têm áreas diferentes; a mediana dos preços responderia
    sobre o imóvel mediano, não sobre este."""
    uteis = [_v(area=90, preco=900_000), _v(area=110, preco=1_320_000)]
    # R$/m2: 10.000 e 12.000 -> mediana 11.000 -> x 100 m2
    assert mediana_dos_vendidos(uteis, area=100) == pytest.approx(1_100_000)


def test_amostra_rasa_nao_produz_leitura():
    """Com menos de três comparáveis a mediana é o próprio ruído."""
    assert mediana_dos_vendidos([_v(area=100, preco=1_000_000)], area=100) is None


def test_divergencia_acima_do_corte_marca_atipico():
    a = avaliar(_est(1_000_000), [_v(area=100, preco=1_300_000)] * 3, area=100, quartos=3)
    assert a.divergencia_pct == pytest.approx(0.30, abs=0.01)
    assert a.atipico is True


def test_sem_vendidos_a_estimativa_responde_sozinha():
    """Fora dos grandes centros o portal costuma não achar comparável. A
    estimativa continua valendo, e a ausência da segunda leitura é dita."""
    a = avaliar(_est(1_000_000), [], area=100, quartos=3)
    assert a.preco_vendidos is None
    assert a.divergencia_pct is None
    assert a.atipico is False
```

- [ ] **Passo 2: rodar e ver falhar.**
- [ ] **Passo 3: escrever o módulo.** `divergencia_pct` é
      `(preco_vendidos - preco_qpreco) / preco_qpreco`, e `atipico` é
      `abs(divergencia_pct) > DIVERGENCE_ALERT` quando as duas leituras existem.
- [ ] **Passo 4: rodar os testes.**
- [ ] **Passo 5: commit** — `feat: mediana dos vendidos e a divergência como sinal`

---

## Tarefa 3 — A tabela do imóvel e das consultas

**Arquivos:** criar `app/models/auction_property.py`,
`alembic/versions/0021_auction_properties.py`,
`tests/test_models/test_auction_property.py`

**Produz**
- `AuctionProperty`: `id`, `apelido`, `address`, `address_number`,
  `neighborhood`, `city`, `state`, `latitude`, `longitude`, `house_type`,
  `total_area`, `bedroom_count`, `bathroom_count`, `suites_count`,
  `parking_slots`, `floor`, `condominium_per_month`, `iptu_per_year`,
  `data_leilao`, `lance_minimo`, `edital_url`, `observacao`, `created_at`,
  `updated_at`
- `AuctionAppraisal`: `id`, `auction_property_id` (FK), `consultado_em`,
  `preco_qpreco`, `faixa_inferior`, `faixa_superior`, `certeza`,
  `preco_vendidos`, `comparaveis_usados`, `divergencia_pct`, `atipico`,
  `preco_itbi`, `itbi_tier`, `itbi_amostra`, `comparaveis_json` (JSON, os dez
  crus para auditoria)

O histórico é uma tabela à parte, e não colunas na primeira: o dono reconsulta
antes do leilão, e o valor de guardar está em ver o número se mover.

- [ ] Passos: teste de round-trip → falhar → modelo + migration → passar →
      `alembic upgrade head` → commit
      `feat: tabela do imóvel de leilão e do histórico de avaliações`

---

## Tarefa 4 — O serviço que junta tudo

**Arquivos:** criar `app/services/appraisal.py` e `tests/test_services/test_appraisal.py`

**Consome:** Tarefas 1-3, e `fetch_registry_buildings` / `fetch_portal_buildings`
de `app/services/opportunities.py`.

**Produz**
- `sugerir_coordenada(db, *, city, street, number) -> tuple[float, float] | None`
  — só Belo Horizonte, consultando `portal_buildings` e depois
  `registry_addresses` por rua+número. É sugestão para o dono confirmar, nunca
  usada sem confirmação.
- `conferencia_itbi(db, imovel) -> tuple[float, str, int] | None` — a escada de
  referência no endereço, quando a cidade tem ITBI carregado.
- `avaliar_imovel(db, imovel, *, force=False, request_fn=...) -> AuctionAppraisal`
  — respeita o TTL de 30 dias salvo `force`.

- [ ] **Passo 1: testes que falham**

```python
def test_sugere_coordenada_em_bh_pelo_diretorio_de_condominios(db_session):
    """O ponto do condomínio fica a 1 m do anúncio na mediana — é a melhor
    coordenada que temos sem o dono abrir o mapa."""
    _condo(db_session, rua="rua_goncalves_dias", numero="865", lat=-19.932468, lon=-43.933033)
    assert sugerir_coordenada(db_session, city="Belo Horizonte",
                              street="Rua Gonçalves Dias", number="865") == (-19.932468, -43.933033)


def test_nao_sugere_coordenada_fora_de_bh(db_session):
    """Sem cadastro nem diretório não há o que sugerir, e chutar é o modo de
    falha que este desenho existe para evitar."""
    assert sugerir_coordenada(db_session, city="São Paulo",
                              street="Rua Harmonia", number="1000") is None


def test_avaliar_grava_as_duas_leituras_e_os_comparaveis_crus(db_session):
    imovel = _imovel(db_session)
    a = avaliar_imovel(db_session, imovel, request_fn=_portal_falso())

    assert a.preco_qpreco == 4513000
    assert a.preco_vendidos is not None
    assert json.loads(a.comparaveis_json)["sold"]
    assert a.certeza == "low"


def test_avaliar_respeita_o_ttl(db_session):
    imovel = _imovel(db_session)
    chamadas = []
    avaliar_imovel(db_session, imovel, request_fn=_contando(chamadas))
    avaliar_imovel(db_session, imovel, request_fn=_contando(chamadas))
    assert len(chamadas) == 2          # estimate + similar-houses, uma vez só


def test_force_reconsulta_mesmo_dentro_do_ttl(db_session):
    imovel = _imovel(db_session)
    chamadas = []
    avaliar_imovel(db_session, imovel, request_fn=_contando(chamadas))
    avaliar_imovel(db_session, imovel, force=True, request_fn=_contando(chamadas))
    assert len(chamadas) == 4


def test_itbi_entra_como_terceira_leitura_em_bh(db_session):
    """Fora de BH a coluna fica nula e nada mais muda."""
    _itbi(db_session, rua="Rua Gonçalves Dias", numero="865", n=6)
    imovel = _imovel(db_session, city="Belo Horizonte")
    a = avaliar_imovel(db_session, imovel, request_fn=_portal_falso())
    assert a.preco_itbi is not None and a.itbi_tier == "endereco_exato"
```

- [ ] Passos 2-5: falhar → implementar → passar → commit
      `feat: avalia o imóvel de leilão pelas duas leituras, com o ITBI de conferência`

---

## Tarefa 5 — API

**Arquivos:** criar `app/api/routes/auctions.py`; modificar `app/main.py`

- `GET /auctions` — ativos (data do leilão nula ou no futuro), com a última
  avaliação embutida
- `POST /auctions` — cria; responde a coordenada sugerida quando houver
- `PATCH /auctions/{id}` / `DELETE /auctions/{id}`
- `POST /auctions/{id}/avaliar?force=` — reavalia
- `GET /auctions/{id}/historico` — as avaliações, mais recente primeiro

D8: a listagem esconde o que já passou da data. Nada é apagado — a linha some da
lista ativa e continua no banco.

- [ ] Testes de rota com `TestClient`, no molde de `tests/test_api/`; commit
      `feat: API dos imóveis de leilão`

---

## Tarefa 6 — Tela `/leilao`

**Arquivos:** criar `app/static/leilao.html` e `app/static/leilao.js`;
registrar `"/leilao": "leilao.html"` no `PAGES` de `app/main.py`

Cada linha mostra as duas leituras lado a lado, a divergência, a certeza que o
portal declarou e — quando existir — o ITBI. Formulário com os campos da
Tarefa 3; ao digitar cidade, rua e número em Belo Horizonte, a coordenada vem
sugerida e o dono confirma. Botão de reavaliar por linha.

`noindex`, fora do sitemap e fora da navegação pública, como `/oportunidades` e
`/enviar` já são.

- [ ] commit `feat: tela de acompanhamento dos imóveis de leilão`

---

## Tarefa 7 — CLI, README e ambiente

- `python -m app.ingestion.cli avaliar-leilao --id N [--force]` para reavaliar
  fora da tela
- `make leilao` no molde dos demais alvos
- `.env.example`: `QPRECO_CALC_MIN_INTERVAL_SECONDS=3.0`, com o comentário do
  que ele protege
- README: seção nova descrevendo as duas leituras, a divergência, a
  obrigatoriedade da coordenada e o motivo de ela ser digitada; e o registro de
  que `save-lead` não é chamado

- [ ] commit `docs: avaliação de imóvel de leilão no README e no Makefile`

---

## Riscos anotados

- **A coordenada é o ponto único de falha silenciosa.** Errada, o portal não
  reclama: devolve o número do quarteirão vizinho. A tela precisa deixar a
  coordenada visível e conferível, não escondida num campo.
- **`bedroomCount` volta nulo em boa parte dos vendidos** (5 de 6 numa consulta
  medida). O filtro trata nulo como compatível de propósito; se isso se mostrar
  frouxo, o corte de área é quem segura.
- **O contrato é interno do portal e pode mudar sem aviso.** O passo 5 da
  Tarefa 1 é o canário, e vale repeti-lo depois de qualquer falha em produção.
- **`predictionCertainty` volta "low" com frequência** — inclusive em Funcionários,
  bairro denso. Não tratar "low" como erro; é informação para a tela.

## Fora deste plano, mas descoberto por ele

`app/pricing/similar_houses.py` chama exatamente o mesmo `similar-houses` e
guarda só três campos do `summary`, descartando dez comparáveis **vendidos** por
consulta — preço de transação com data, endereço e distância, em 28.681 anúncios
ativos. É a descoberta de maior valor desta investigação e merece plano próprio.
