# ImovelRadar

Public dataset + API of Brazilian real-estate transactions, sourced from ITBI
(property transfer tax) open data published by city councils. Settled ITBI
implies a real transaction at a real declared value — the goal is to use this
as a price signal. Coverage is limited to cities that publish this data openly.

Currently covered: **Belo Horizonte (MG)**.

## Quick start (Docker)

The easiest way to run the project is with Docker Compose. It builds the API
image, runs Postgres, applies migrations, and starts the server:

```bash
cp .env.example .env
docker compose up --build
```

The app will be available at `http://127.0.0.1:8000` and the API docs at
`http://127.0.0.1:8000/docs`.

### Docker layout (multi-project / VPS-friendly)

This stack is only `web` + `postgres` (no reverse proxy in this repo). Defaults
are safe to run next to other Compose projects on the same machine:

| Concern | Default |
| --- | --- |
| App port on host | `127.0.0.1:8000` (`WEB_PORT`) |
| Postgres port on host | `127.0.0.1:5433` (`POSTGRES_PORT`) — not 5432 |
| Bind addresses | localhost only (not published on `0.0.0.0`) |
| Code in container | image build only (no `.:/app` mount) |
| DB credentials | `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` in `.env` |
| Restart | `unless-stopped` |

Inside Compose, `web` always connects to host `postgres` (service name). The
`DATABASE_URL` in `.env` is for tools running on the **host** (local uvicorn,
Alembic outside Docker).

If another stack already uses 8000 or 5433, change `WEB_PORT` / `POSTGRES_PORT`
in `.env`. On a shared VPS, also set a strong `POSTGRES_PASSWORD` and keep a
host firewall that does not expose these ports publicly.

> Changing `POSTGRES_*` after the first successful Postgres start does **not**
> rewrite an existing data volume. For local dev you can reset with
> `docker compose down -v` (destroys DB data). On a machine with real data,
> keep the original password or migrate deliberately.

No reverse proxy is defined here on purpose — on a shared host it belongs to the
host, not to this repo. Production adds `docker-compose.prod.yml`, which drops the
published app port and joins a shared `edge` network so an external nginx can reach
the container. See [`docs/deploy-oracle-new.md`](docs/deploy-oracle-new.md).

## Local development

Há um `Makefile` com os atalhos do fluxo inteiro (`make` lista todos):

```bash
make setup     # venv + dependências + .env
make db        # sobe o Postgres e espera aceitar conexão
make migrate   # aplica as migrations
make collect   # coleta um bairro nas três fontes
make score     # recalcula as notas
make run       # API em http://localhost:8000/oportunidades
```

Variáveis como `CIDADE`, `BAIRRO`, `SOURCES` e `QPRECO_LIMIT` podem ser
sobrescritas na chamada: `make collect BAIRRO="Lourdes"`.

Os mesmos passos, à mão:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d postgres
PYTHONPATH=. alembic upgrade head
uvicorn app.main:app --reload
```

## Web interface

Acesse `http://localhost:8000/`. A interface tem nove telas:

| Rota | Tela |
| --- | --- |
| `/` | Início — números da base e ranking de R$/m² por bairro |
| `/busca` | Busca de quitações (tabela ou cards), com filtros e ordenação |
| `/imovel` | Histórico de uma unidade: linha do tempo e quitações |
| `/bairro` | Ranking de bairros e o detalhe de cada um |
| `/curiosidades` | Recordes e extremos da base inteira |
| `/comparar` | Até três unidades lado a lado (lista guardada no navegador) |
| `/oportunidades` | Anúncios abaixo do valor estimado por ITBI (`noindex`, fora do sitemap) |
| `/enviar` | Upload administrativo do CSV de ITBI (protegido por Basic Auth no Nginx) |

Filtros de busca aceitam cidade, bairro, rua, número, faixa de valor, área,
tipo de construção/ocupação e data — todos refletidos na URL, então qualquer
busca é compartilhável. Links antigos no formato `/?street=X` continuam
funcionando: a home redireciona para `/busca` preservando a query.

## Ingesting data

### Via web interface (administrativa)

Use `https://radar.leilaolabs.com.br/enviar` after authenticating with the Nginx
Basic Auth credentials. The upload page is intentionally absent from the public
navigation and the upload operation is not published in the public OpenAPI schema.
See [`docs/radar-nginx-auth.conf.example`](docs/radar-nginx-auth.conf.example) for
the proxy protection.

### Via CLI

Download Belo Horizonte's ITBI CSV export and run:

```bash
PYTHONPATH=. python -m app.ingestion.cli --city belo_horizonte --file /path/to/file.csv
```

Re-running ingestion on the same file is safe — rows are deduplicated by content
hash.

## Market comparables / price suggestions

The project can enrich market-comparable listings with price-suggestion data
from QuintoAndar. First, set the session cookie in `.env`:

```bash
QUINTOANDAR_PRICE_SUGGESTION_COOKIE=<your 5AJWT_AUTH cookie value>
```

Then run the enrichment CLI:

```bash
PYTHONPATH=. python -m app.ingestion.cli quintoandar-price-suggestions \
  --limit 100 --workers 1 --worker-index 0
```

Use `--cidade` to filter by city (can be passed multiple times). For parallel
workers, run the same command with `--worker-index` from `0` to `workers - 1`.

## Oportunidades de anúncios

Anúncios de venda do **Loft, QuintoAndar e VivaReal** são coletados, cruzados
com o histórico recente de ITBI e publicados em `/oportunidades` com uma
**nota de 0 a 100**.

### Rodando localmente do zero

Pré-requisitos: Docker (Postgres), Python 3.13, e a base de ITBI de BH
ingerida (veja *Ingesting data*).

```bash
docker compose up -d postgres
PYTHONPATH=. alembic upgrade head        # inclui 0005-0007

# 1. Coletar. Um bairro para experimentar:
PYTHONPATH=. python -m app.ingestion.cli market-refresh \
  --cidade "Belo Horizonte" --bairro Savassi \
  --filtros '{"tipo_imovel": "APARTAMENTO"}'

# ...ou a cidade inteira, bairro a bairro, respeitando os tetos dos portais:
PYTHONPATH=. python -m app.ingestion.cli market-sweep \
  --cidade "Belo Horizonte" --filtros '{"tipo_imovel": "APARTAMENTO"}'

# 2. Calcular notas (não precisa de SMTP nem de configuração de alerta):
PYTHONPATH=. python -m app.ingestion.cli opportunity-refresh --cidade "Belo Horizonte" \
  --qpreco-limit 200   # --sem-qpreco pula a consulta ao QuintoAndar

# 3. Ver:
uvicorn app.main:app --reload    # http://localhost:8000/oportunidades
```

Nada além do Postgres é obrigatório. SMTP e a configuração de alerta só são
necessários para **e-mail**; a tela e a API funcionam sem eles.

Uma cidade inteira leva alguns minutos de coleta (é limitada pela taxa dos
portais, não pelo banco). O cálculo das notas roda em segundos.

### A nota

`nota = 100 x força x plausibilidade`

- **força** — o desconto dividido pelo **erro medido** daquela combinação de
  tier e dispersão (a tabela `EXPECTED_ERROR`, calibrada por validação cruzada).
  A nota chega a 100 quando o desconto é quatro vezes esse erro: 20% contra uma
  amostra apertada de endereço exato, 60% contra uma de rua. É isso que torna
  escopos diferentes comparáveis, em unidade de erro real e não de proxy;
- **plausibilidade** — acima de ~55% de desconto a curva **desce**. Um desconto
  de 85% quase sempre é área errada ou unidade mal rotulada, não achado.

Não há mais termo de profundidade de amostra. Controlando por dispersão, o
tamanho da amostra **não** prevê erro — inverte: na faixa de dispersão acima de
30%, o erro mediano sobe de 13,4% (2 a 9 linhas) para 21,2% (30+), porque
amostra funda é escopo largo. Amostra rasa continua penalizada, mas pelo
caminho certo: abaixo de 4 vendas não há quartis, então ela recebe a dispersão
pessimista de 35% e cai para a pior célula do seu tier.

### A segunda referência: o qpreço do QuintoAndar

O ITBI é uma leitura do valor da unidade; a estimativa que o próprio
QuintoAndar publica (`price-suggestion`, o "qpreço") é outra, independente. Um
desconto só significa alguma coisa quando as duas concordam, então:

- `nota_itbi` sai da referência de ITBI, como descrito acima;
- `nota_qpreco` usa a **mesma fórmula**, trocando o preço estimado pelo valor
  sugerido e a dispersão da amostra pela **meia-largura da faixa** que o portal
  publica (`(superior - inferior) / 2 x sugerido`). Sem faixa, assume-se uma
  dispersão comum. O portal não expõe tamanho de amostra, então esse termo fica
  cheio em vez de punir o anúncio por um número que não existe;
- `nota = min(nota_itbi, nota_qpreco)`.

O `min` é deliberado: a segunda referência **derruba** nota, nunca infla. Assim
um anúncio de Loft ou VivaReal, que não tem qpreço, continua valendo pela nota
de ITBI — nenhuma fonte é punida por um dado que o portal dela não publica.

#### Consumo do endpoint

`POST .../pricing-reports/v1/price-suggestion` **responde sem sessão** — medimos
a mesma resposta, chave por chave, com e sem o cookie `5AJWT_AUTH`. Então
`QUINTOANDAR_PRICE_SUGGESTION_COOKIE` é opcional e fica vazio por padrão: nada
de conta pessoal exposta num job automático.

O que resta é carga sobre o portal, tratada assim:

- **só candidatos**: uma requisição por anúncio, e apenas para os do QuintoAndar
  que **já passariam no alerta** pelo ITBI sozinho — como o qpreço só reduz nota,
  perguntar sobre os demais não mudaria estado nenhum;
- **cache de 30 dias** (`QPRECO_TTL_DAYS`), inclusive para o `not_found`: nenhum
  anúncio é reperguntado dentro da janela;
- **teto por execução**: `--qpreco-limit`, padrão 50, os de maior nota primeiro;
- **ritmo próprio**: `QPRECO_MIN_INTERVAL_SECONDS` (padrão 3 s) em vez do piso de
  0,35 s dos coletores. O endpoint não é paginado — um humano navegando dispara
  um por página, e é essa ordem de grandeza que se imita;
- **serial**: nunca paralelize essa etapa;
- **circuit breaker**: 401/403/429 viram `PortalBlocked` e **abortam a etapa na
  hora**; três falhas seguidas de qualquer tipo também. O summary reporta
  `qpreco_interrompido=bloqueado|falhas_seguidas`. Drenar o teto contra um
  gateway que acabou de recusar é o que transforma throttle em bloqueio.

`--sem-qpreco` desliga a consulta e as notas saem só do ITBI.

### Quanto a referência erra

`scripts/validar_referencia.py` esconde 20% das quitações residenciais, monta a
escada com os 80% restantes e tenta prever o R$/m² de cada linha escondida. Em
Belo Horizonte (8.143 previsões):

| referência | n | erro mediano | p90 | erra >40% |
| --- | ---: | ---: | ---: | ---: |
| endereço exato | 4.697 | **9,0%** | 36,1% | 8,8% |
| rua | 1.634 | 18,3% | 58,9% | 19,5% |
| bairro + área | 1.648 | 21,5% | 71,0% | 23,1% |
| bairro amplo | 164 | 24,8% | 110,9% | 32,3% |

Erro mediano global: **12,6%**. Três leituras:

1. **A escada está na ordem certa**, e o endereço exato vale o dobro dos outros.
   Por isso a conversão de área importa tanto: ela triplicou o alcance do melhor
   tier.
2. **Os pisos foram calibrados pelo erro global, não pelo erro de cada tier.**
   Subir o piso de endereço exato para 10 faz aquele tier exibir 6,7% — e leva o
   global a 15,0%, porque tudo que ele rejeita cai num tier pior. Duas vendas no
   mesmo endereço batem a rua que as substituiria: piso 2 → 12,6% global; 3 →
   13,0%; 5 → 13,9%.
3. **A dispersão da amostra prevê erro, e é o que a nota usa**: 5,4% de erro
   mediano onde a dispersão é menor que 15%, 12,0% entre 15% e 30%, 17,0% acima
   disso. O proxy que sustenta a nota está validado por dado.

O tamanho da amostra, sozinho, **não** prevê erro (11,7% com 1-4 linhas contra
12,9% com 50+), porque amostra grande vem de escopo largo. Ele só informa dentro
do tier de endereço exato, onde vai de 10,7% (3-9 linhas) a 4,2% (100+). O termo
de amostra da nota ainda trata os dois casos igual — é a próxima correção.

### Como o valor estimado é calculado

O valor declarado no ITBI **não é preço de anúncio**: em BH o anúncio pede uma
mediana de 1,74x o R$/m² declarado, e a distância varia com o tamanho (2,55x
abaixo de 60 m², 1,27x acima de 250 m²). Comparar direto reporta todo anúncio
como caro e faz apartamento grande parecer barato.

Então o ITBI define a **forma** da referência — ele resolve a diferença de
preço rua a rua, o que a amostra esparsa de anúncios não consegue — e um
**fator de calibração** converte isso no preço que um comparável pediria:

- janela: 24 meses (inclusiva) terminando na última quitação residencial válida;
- referência, nesta ordem: **endereço exato** (mín. 2 ITBIs), **rua** (mín. 5),
  **bairro + área ±30%** (mín. 15), **bairro amplo** (mín. 1). Os pisos saem de
  validação cruzada, não de intuição — veja abaixo;
- **a área é convertida antes de comparar** (`AREA_MATCH_FACTOR = 1.6`). O
  cartório lança "Área Construída Adquirida" e o portal anuncia área útil: nos
  551 pares do mesmo endereço em BH, o ITBI registra uma mediana de **1,62x** o
  número anunciado (p25 1,24, p75 1,97). A janela de ±30% centrada na área crua
  procurava justamente onde o apartamento não está — corrigido, o tier de
  endereço exato foi de 120 para 405 anúncios e o bairro amplo caiu de 759 para
  529. A conversão vale só para **escolher** os comparáveis; o preço continua
  sendo R$/m² da referência vezes a área anunciada, e o fator de calibração é
  medido nessa mesma área, então o nível de preço não se move. Remeça com
  `PYTHONPATH=. python scripts/medir_area_itbi.py --cidade "..."`;
- `preco_estimado = mediana(R$/m² ITBI da referência) x fator x area_util`;
- o fator é a mediana, por bairro e faixa de área, da razão entre o R$/m² pedido
  e o R$/m² da **própria referência de cada anúncio**. Calibrar contra a mediana
  do bairro inflava a estimativa justamente onde a referência é mais estreita;
- sem fator medido para o escopo, **nenhuma oportunidade é emitida** — nunca se
  cai para 1,0, que é o bug que essa camada existe para evitar;
- só ITBI residencial com valor e área positivos entra; o tipo do anúncio é
  mapeado para `AP` ou `CA`. Sem mapeamento, sem oportunidade.

Anúncios repetidos (mesma unidade em vários anunciantes ou portais) contam uma
vez só: rua + área + preço ao milhar identificam a unidade. O número da rua fica
de fora porque QuintoAndar e Loft nunca o publicam.

### Cobertura e tetos dos portais

Cada fonte limita quanto uma consulta pagina: **QuintoAndar 1.000** resultados
(`pageSize + offset`), **VivaReal 1.500** (`from`), **Loft ~9.000**. Uma consulta
de cidade inteira volta sempre truncada, então `market-sweep` corta por bairro e
corta de novo por quartos o escopo que continuar truncado. Os bairros saem da
tabela de ITBI: anúncio em bairro sem transação nunca poderia ser pontuado.

Coleta truncada grava o que viu mas **nunca inativa** anúncio que não conseguiu
paginar.

O ITBI grava bairro sem acento e em caixa alta (`SANTO ANTONIO`); o VivaReal
casa `addressNeighborhood` exatamente e responde **200 com zero resultados**
para a grafia errada. A varredura traduz o nome usando a grafia que os próprios
anúncios já coletados trazem — inclusive de outra fonte, já que Loft e
QuintoAndar ignoram caixa e acento e aprendem a grafia primeiro. Escopo que
volta vazio é reportado como `vazios`, nunca como coletado.

### Histórico

`listing_price_events` grava `listed`, `price_changed`, `delisted` e `relisted`
com a nota e o desconto do momento. É o que permite perguntar depois o que o
modelo dizia sobre um anúncio que saiu do mercado — a validação de campo que
ainda não existe.

### Configuração de alerta (só para e-mail)

Sem configuração o job de alerta fica desabilitado:

```bash
PYTHONPATH=. python -m app.ingestion.cli opportunity-config \
  --cidade "Belo Horizonte" \
  --destinatario alerta@example.com \
  --bairro Savassi --bairro Lourdes \
  --nota-minima 80 --periodicidade-minutos 720
```

Lista de bairros vazia significa todos os bairros coletados. Alterar cidade,
bairros, desconto, confiança ou nota cria uma nova `rule_version`, que estabelece
nova linha de base sem disparo em massa; mudar apenas destinatários mantém a
versão. O agendamento usa `America/Sao_Paulo`.

### SMTP

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=usuario
SMTP_PASSWORD=senha
SMTP_FROM=alertas@imovelradar.local
SMTP_USE_TLS=true
SMTP_SUBJECT_PREFIX=[ImovelRadar]
```

`SMTP_HOST` vazio faz o envio falhar e o evento é registrado como `failed`.
As URLs dos portais são configuráveis por `LOFT_SEARCH_API_URL`,
`QUINTOANDAR_SEARCH_API_URL` e `VIVAREAL_API_URL`; a retentativa e o ritmo das
requisições, por `HTTP_*` (veja `.env.example`).

### Comandos

```bash
# coleta de um escopo
python -m app.ingestion.cli market-refresh --cidade "Belo Horizonte" --bairro Savassi

# recalcula notas sem enviar nada
python -m app.ingestion.cli opportunity-refresh --cidade "Belo Horizonte" \
  --qpreco-limit 200   # --sem-qpreco pula a consulta ao QuintoAndar

# varredura da cidade inteira, dividindo o que estourar o teto
python -m app.ingestion.cli market-sweep --cidade "Belo Horizonte"

# coleta + cálculo + e-mail (agendável)
python -m app.ingestion.cli opportunity-alerts --cidade "Belo Horizonte" --dry-run
```

Opções: `--skip-refresh` (só recalcula e alerta), `--no-deactivate`,
`--force-initial` (disparo inicial de uma nova `rule_version`) e `--dry-run`.

### Coleta agendada

Um container opcional roda o ciclo sozinho (varredura + alertas), fora por
padrão para que `docker compose up` continue sendo só um servidor web:

```bash
docker compose --profile scheduler up -d
```

Ajuste `SWEEP_CITY`, `SWEEP_SOURCES` e `SWEEP_INTERVAL_SECONDS` no `.env`.
Uma varredura que falha não derruba o loop — o próximo ciclo é a retentativa.

### Regras de envio

Um alerta exige nota ≥ a configurada (padrão 80). Nunca mais de um e-mail por
anúncio em 24 horas. Depois disso, só há reenvio se o preço anunciado variar
≥3%, o desconto variar ≥5 pontos percentuais ou a estimativa variar ≥5%.
Anúncio que sai e volta gera novo alerta mesmo sem mudança de números. Eventos
`failed` e `pending` abandonados há mais de uma hora são retentados.

### Limitações

- só Belo Horizonte tem base ITBI carregada;
- QuintoAndar e Loft **não publicam o número da rua**, então só o VivaReal
  alcança a referência de endereço exato;
- a calibração precisa de anúncios suficientes por bairro e faixa de área; com
  poucos, o fator colapsa no próprio anúncio e o desconto vira zero — por isso
  os mínimos, e por isso escopo sem calibração não emite nada;
- resta um viés de ~+9% na faixa de endereço exato: são poucos anúncios na
  cidade para calibrar essa faixa separadamente;
- nada disso foi validado contra vendas reais; `listing_price_events` é a
  infraestrutura para isso, mas a resposta só vem depois de meses de coleta;
- a estimativa é estatística e não substitui avaliação;
- anúncios e oportunidades **não** entram nas páginas SEO nem no sitemap: a
  tela `/oportunidades` é `noindex`.

## Endpoints

- `GET /transactions` — filter by `city`, `neighborhood`, `min_value`,
  `max_value`, `min_area`, `max_area`, `construction_type`, `occupation_type`,
  `date_from`, `date_to`; order with `sort` (`date_desc`, `date_asc`,
  `value_desc`, `value_asc`, `m2_desc`, `m2_asc`); paginate with
  `limit`/`offset`.
- `GET /transactions/{id}`
- `GET /cities`
- `GET /neighborhoods?city=belo_horizonte`
- `GET /stats/overview`, `GET /stats/neighborhoods`,
  `GET /stats/neighborhoods/{neighborhood}`
- `GET /stats/curiosities?city=belo_horizonte` — records and extremes over the
  whole history. It is a full scan, so the result is memoized per city and
  recomputed only when the row count or the last settlement date changes.
- `GET /opportunities` — filter by `city`, `neighborhood`, `source`,
  `tipo_imovel`, `min_nota` (0-100), `confianca`, `min_confianca`,
  `min_desconto_pct`, `max_preco`; order with `sort` (`nota_desc` default,
  `desconto_desc`, `desconto_asc`, `preco_asc`, `preco_desc`, `recente_desc`);
  paginate with `page`/`page_size`.
- `GET /opportunities/{id}` — only active, calculated listings.
- The administrative `POST /upload` operation is intentionally omitted from the
  public API documentation and must only be reachable through the authenticated
  Nginx location.

## Tests

```bash
pytest -v
```

For Docker-based tests, run them inside the `web` container:

```bash
docker compose exec web pytest -v
```
