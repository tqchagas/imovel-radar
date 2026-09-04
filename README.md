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
make setup                              # venv + dependências + .env
make base ARQUIVO=~/Downloads/itbi.csv  # do zero até ter tudo no banco
make run                                # API em http://localhost:8000
```

`make base` roda, em ordem: Postgres, migrations, ITBI, cadastro imobiliário,
varredura dos portais, diretório de condomínios, notas e desfechos. É a única
ordem que funciona — o ITBI é a fundação, o cadastro dá coordenada ao resto, e o
diretório de condomínios só sabe o que buscar depois que há anúncio sem número.

O CSV de ITBI não tem URL estável: baixe em [dados.pbh.gov.br](https://dados.pbh.gov.br)
e passe em `ARQUIVO=`. Sem ele, `make base` avisa e segue — mas nada terá contra
o que comparar.

Depois, para manter em dia:

```bash
make tudo      # cadastro, varredura, condomínios, notas, desfechos e a aferição
make validar   # erro medido da escada de referência e da calibração
```

### Produção

```bash
make deploy            # git pull + rebuild no servidor (pede confirmação)
make deploy-logs       # acompanha a web
make deploy-ps         # o que está de pé
make deploy-base       # roda o ciclo de dados no servidor (horas)
make deploy-scheduler  # liga o container que repete o ciclo sozinho
make deploy-psql       # psql do banco de produção
```

O host sai de `DEPLOY_HOST` (padrão `oracle-new`, do seu `~/.ssh/config`). As
migrations rodam sozinhas no entrypoint. O ITBI **não** entra no `deploy-base`:
em produção ele é ingerido pela tela `/enviar`, protegida por Basic Auth no
Nginx. Veja [`docs/deploy-oracle-new.md`](docs/deploy-oracle-new.md).

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
PYTHONPATH=. alembic upgrade head

# 0. Cadastro imobiliário da prefeitura: endereço, coordenada do lote, padrão
#    de acabamento e área por unidade. Mensal, e vale a pena vir antes de tudo —
#    é o que faz o anúncio sem número de rua alcançar o tier de endereço.
PYTHONPATH=. python -m app.ingestion.cli registry-sync --cidade belo_horizonte

# 0b. Diretório de condomínios do portal: o número da rua que Loft e
#     QuintoAndar não publicam. Sob demanda, dirigido pelo anúncio.
PYTHONPATH=. python -m app.ingestion.cli condo-sync --cidade belo_horizonte --limit 500

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

# 3. Registrar desfechos: anúncio que saiu do ar contra quitação de ITBI.
PYTHONPATH=. python -m app.ingestion.cli outcome-track --cidade belo_horizonte

# 4. Ver:
uvicorn app.main:app --reload    # http://localhost:8000/oportunidades
```

Nada além do Postgres é obrigatório. SMTP e a configuração de alerta só são
necessários para **e-mail**; a tela e a API funcionam sem eles.

Uma cidade inteira leva alguns minutos de coleta (é limitada pela taxa dos
portais, não pelo banco). O cálculo das notas roda em segundos.

### Cadastro imobiliário: como o anúncio encontra o prédio

A escada de referência só alcança o tier de endereço exato — onde o erro medido
é 5-13%, contra 14-25% nos tiers de rua e bairro — quando sabe em que prédio o
anúncio está. Só o VivaReal publica número de rua; Loft e QuintoAndar publicam
a rua e a coordenada.

O [cadastro imobiliário da PBH](https://dados.pbh.gov.br) fecha essa lacuna. É
uma extração mensal por regional, com o logradouro na mesma abreviação do ITBI,
o número, o padrão de acabamento, a área construída por unidade e a geometria
do lote em UTM SIRGAS2000. Ele cobre **99,6%** dos endereços de ITBI de
apartamento, e a coordenada do lote cai a **12 m** (mediana) do ponto que o
portal publica para o mesmo endereço.

Casando pela rua que o anúncio declara mais a coordenada, num raio de 50 m, o
número certo sai em **93,5%** dos casos — medido contra os 1.530 anúncios do
VivaReal que publicam número *e* coordenada exata. Como 93,5% não é certeza,
esse endereço é um tier próprio, `endereco_geo`, com erro esperado próprio.

O cadastro também traz o que a calibração não tinha: o padrão de acabamento do
prédio, a única variável de qualidade que o ITBI e o anúncio medem do mesmo
jeito, e a dispersão das áreas das unidades, que diz quando a janela de área
não tem o que separar dentro de um prédio.

    make cadastro     # mensal

### O prédio: quem o portal diz que é

Só o VivaReal publica número de rua. Loft e QuintoAndar publicam a rua e a
coordenada, e sem número o anúncio não alcança o tier de endereço.

Havia uma segunda fonte de número que o projeto não usava: o **diretório de
condomínios do QuintoAndar**, uma página por prédio, indexada em
`sitemap-v3-condos-part-*.xml` e liberada pelo `robots.txt`. São 19.117 prédios
em Belo Horizonte, cada um com rua, número, CEP, coordenada, faixa de área das
unidades e as instalações do edifício. Medido em 59 páginas sorteadas:

| medida | resultado |
| --- | ---: |
| trazem o número | 59/59 |
| casam com o cadastro da prefeitura por rua+número | 83% |
| distância do ponto ao lote do cadastro | p50 8 m, p90 24 m |
| distância do ponto ao anúncio do próprio portal | p50 1 m, máx 27 m |

    make condominios    # a cada ciclo, com teto

A coleta é dirigida pelo anúncio: baixar as 19.117 páginas seria dezessete
gigabytes, então cada execução gasta o teto nos bairros que têm anúncio ativo
sem número, do mais carente ao menos, e o `<lastmod>` do sitemap evita
rebaixar o que não mudou.

O número que sai daí vira o tier `endereco_portal`. Ele **não** herda o erro do
endereço exato: na primeira medida, com o diretório parcialmente coletado, ele
deu 21,2% em 55 previsões, acima dos 19,1% do `endereco_geo` — cinquenta e cinco
previsões não decidem nada, e enquanto a dúvida existe ela não infla nota.

A busca em massa do QuintoAndar também passou a pedir campos que ela já
devolvia de graça: `condoId` (em 99,8% dos anúncios, e agrupa sem erro — a
coordenada dentro de um mesmo id tem espalhamento mediano de 0 m), `condoName`,
`iptu` e `condominium`. Nenhuma requisição a mais.

### Uma correção de área que foi medida e recusada

A área do ITBI e a área anunciada não medem a mesma coisa, e a razão entre elas
varia por prédio — de 1,00 no p10 a 2,13 no p90. Parece óbvio trocar o fator
único da cidade (`AREA_MATCH_FACTOR`) pela área que o cadastro publica por
prédio. Foi implementado e validado:

| régua | p50 | p75 | p90 |
| --- | ---: | ---: | ---: |
| **fator único da cidade (o que está no código)** | **21,6%** | **39,6%** | **64,4%** |
| área do cadastro, `k` por prédio (≥2 anúncios) | 24,8% | 47,0% | 75,8% |
| idem, exigindo ≥12 anúncios no prédio | 22,2% | 41,2% | 68,3% |
| área do cadastro só na janela de comparáveis | 24,3% | 45,6% | 80,2% |

**Piora em todas as variantes.** A calibração por bairro e faixa de área já
absorve a mediana da conversão em cada célula, e um `k` estimado a partir de
poucos anúncios do prédio traz mais ruído do que o viés que remove. O relato
completo, com o porquê e o que teria de mudar para valer a pena, está em
[`docs/superpowers/specs/2026-09-04-acuracia-area-design.md`](docs/superpowers/specs/2026-09-04-acuracia-area-design.md).

O que ficou do experimento é o `unit_area_profile` no cadastro — os onze decis
das áreas das unidades de cada endereço —, que é dado barato e é a entrada de
qualquer nova tentativa.

### Se um alerta prestou

Duas validações medem se uma estimativa acerta um número que já existe:

    make validar

`validar_referencia.py` esconde 20% das quitações de ITBI e prevê o R$/m² de
cada uma pela escada montada com o resto. `validar_calibracao.py` esconde 20%
dos anúncios ativos e prevê o preço que eles pedem — é o único teste do fator
que converte ITBI em preço pedido, que a validação de ITBI contra ITBI não
alcança.

Nenhuma das duas responde se o imóvel **era** uma oportunidade. Essa resposta
só vem do encontro das duas fontes: um anúncio que sai do ar e reaparece como
quitação de ITBI no mesmo endereço entrega o preço pelo qual o negócio de fato
fechou.

    make desfechos    # a cada ciclo de coleta

Isso amadurece com o calendário, não com o código: o ITBI de Belo Horizonte
chega com dois meses de atraso, então um desfecho aberto hoje só fecha meses
adiante. Enquanto `matched_at` é nulo, a ausência de par não é resposta — é
dado que ainda não chegou.

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

### Quem responde "quanto vale"

Validação cruzada em 3.958 anúncios escondidos: prever o **preço pedido** pela
escada de ITBI erra **22,2%** na mediana, e passa de 40% em um quarto dos casos
— a mesma ordem de grandeza do desconto que chamamos de oportunidade. Por tier:
15,6% no endereço exato, 22,2% na rua, 23,2% no bairro.

O qpreço avalia a unidade e publica uma faixa de ~5%. Então, **onde ele existe,
é ele quem responde**, e a leitura de ITBI fica guardada ao lado como
conferência (`preco_estimado_itbi`, `desconto_itbi_pct`).

A referência mais precisa decide; a outra só derruba quando **contradiz** — ou
seja, quando diz que o anúncio pede *acima* do esperado por margem maior que o
próprio erro dela. Não basta ser morna: na base, quase todo anúncio 15% abaixo
do qpreço também tem desconto positivo pelo ITBI, e mesmo assim tirava nota
baixa por ser dividido pelos 22% de erro. Deixar isso vetar devolvia o ruído da
régua grossa à decisão.

**Sem qpreço próprio, a régua vem dos vizinhos.** Loft e VivaReal nunca terão um
— o endpoint resolve por id do QuintoAndar — mas 48% e 69% deles dividem rua e
faixa de área (±20%) com um anúncio que tem. A mediana do qpreço por m² desses
vizinhos vira a estimativa. Validado escondendo o qpreço do próprio anúncio e
prevendo pelos vizinhos, em 974 casos:

| dispersão dos vizinhos | erro mediano |
| --- | ---: |
| < 15% | 3,5% |
| 15-30% | 9,2% |
| > 30% | 13,2% |

Contra os 22,2% da escada de ITBI. E não há viés de fonte: a razão entre a
estimativa emprestada e o preço pedido dá 0,91 no Loft, 0,87 no QuintoAndar e
0,93 no VivaReal, contra 0,92 do controle em que o próprio qpreço responde.

A ordem de precedência é: **qpreço próprio → qpreço dos vizinhos → escada de
ITBI**, sempre a régua mais fina disponível.

O piso de desconto acompanha o erro de quem respondeu (`MIN_DISCOUNT_MULTIPLE`,
1,5x): 30% contra a rua, 7,5% contra um qpreço de faixa estreita. Um desconto de
12% não significa a mesma coisa nas duas réguas.

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
- QuintoAndar e Loft não publicam o número da rua no anúncio. O diretório de
  condomínios do portal resolve isso, mas ele é coletado sob demanda e com teto,
  então a cobertura cresce a cada ciclo em vez de estar completa desde o
  primeiro dia;
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

## Avaliação de imóvel de leilão (`/leilao`)

Edital de leilão traz endereço, área e uma avaliação judicial que costuma estar
velha. O imóvel não está anunciado, então nada da coleta o alcança.

A **Calculadora QPreço** do QuintoAndar responde por endereço arbitrário, sem
anúncio e sem sessão — é o produto "quanto vale meu imóvel", e `Interessado` é
uma das relações que o próprio formulário oferece. Na mesma consulta ela
devolve os comparáveis que o portal reporta como **vendidos**, com preço, mês,
área, distância e rua.

A tela mostra três leituras independentes e **não arbitra entre elas**:

| leitura | de onde vem |
| --- | --- |
| Valor QuintoAndar | o modelo deles, com a certeza que eles mesmos declaram |
| Mediana das vendas reais | R$/m² mediano dos vendidos comparáveis (±20% de área, mesmos quartos, ≤1 km) |
| Mediana de ITBI | a escada de referência no endereço — só onde há ITBI carregado |

O que decide a confiança é a **divergência** entre as duas primeiras: acima de
15% o imóvel é marcado como atípico e pede olho humano. É a mesma forma do
`min(nota_itbi, nota_qpreco)` da nota de oportunidade — a segunda referência
serve para desconfiar, não para inflar.

O lance máximo não sai daqui: isso é conta do dono, com os custos de arremate,
a reforma e a margem que ele exige.

### Conferindo contra o site deles

A página do QPreço mostra três números com nomes próprios, e o destaque **não é
o do meio**:

| na tela do portal | no payload | exemplo |
| --- | --- | ---: |
| "Venda por ... **Ideal**" | `suggestedLowerBoundPrice` = `FASTER` | R$ 568.000 |
| (não exibido em destaque) | `suggestedPrice` = `REGULAR` | R$ 634.000 |
| "**Na média dos similares** na região" | `suggestedUpperBoundPrice` = `SLOWER` | R$ 713.000 |

Conferido idêntico em três imóveis: `dealObjectiveRanges` e os *bounds* são os
mesmos valores com dois nomes. A tela usa os rótulos do portal para que a
comparação seja direta.

**Cuidado ao comparar.** O site tenta casar o endereço com o que ele já conhece
(`matchType=full_match`) e, quando acerta, **preenche os atributos sozinho e não
pergunta**. Medido na Rua dos Crenaques, 385: ele assumiu 154 m², 1 banheiro,
condomínio de R$ 250 e IPTU de R$ 16.225 — e respondeu sobre essa unidade, não
sobre a de 107 m² que se queria avaliar. A diferença foi de 24%.

Aqui os atributos são sempre os que você digita, porque num leilão a unidade é
uma unidade específica e não a que o portal tem em cadastro.

### A coordenada domina o resultado

Medido em 2026-09-04, no mesmo imóvel e no mesmo corpo de requisição:

```
-19.932468, -43.933033  (ponto do prédio no QuintoAndar)   R$ 4.513.000
-19.932521, -43.933081  (lote do cadastro da prefeitura)   R$ 3.681.000
```

Seis metros, 18,4% de diferença, de forma determinística — os dois se repetem
idênticos. É o campo mais sensível de toda a conta, mais que a área.

Pior: **coordenada errada não dá erro.** Sem ela o portal responde 200 dizendo
que não conseguiu calcular, que é a mesma resposta que dá para imóvel
genuinamente atípico; com ela errada por duzentos metros, devolve um número
plausível do quarteirão vizinho.

Por isso a coordenada nunca é geocodificada em silêncio. Em Belo Horizonte a
tela *sugere* um ponto por rua+número — primeiro o do diretório de condomínios,
que é o que o próprio portal usa para o prédio, depois o lote do cadastro — e o
dono confirma. Fora dali, ele cola a do mapa. A tela sempre mostra a coordenada
e a origem dela, e avisa quando não é a do portal.

### Comandos

```bash
# a tela faz isso num clique; o comando existe para agendar ou reavaliar em lote
PYTHONPATH=. python -m app.ingestion.cli avaliar-leilao --id 1 --force
```

`/leilao` é `noindex`, fora do sitemap e fora da navegação pública, como
`/oportunidades` e `/enviar`. Passada a data do leilão a linha sai da lista, mas
nada é apagado.

### O que este produto não chama

A tela do portal dispara um terceiro POST, `save-lead`, que registra um
interessado no funil deles. Ele é uma chamada separada e **nunca é feita aqui** —
`estimate` e `similar-houses` respondem 200 sem ele. Nenhum dado pessoal viaja.

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
- `GET /auctions`, `POST /auctions`, `PATCH /auctions/{id}`, `DELETE /auctions/{id}`,
  `POST /auctions/{id}/avaliar`, `GET /auctions/{id}/historico` e
  `GET /auctions/coordenada` — imóveis de leilão digitados à mão.
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
