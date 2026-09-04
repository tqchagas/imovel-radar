# Acurácia da área: tirar a conversão do caminho do preço

**Data:** 2026-09-04
**Estado:** **implementada e parcialmente revertida.** A parte de identidade de
prédio ficou; a substituição da área **foi medida, piorou e saiu**. Leia a seção
"O que a validação cruzada disse" antes de tentar de novo.

## O problema, em uma frase

O preço é por m², a estimativa multiplica uma área, e a área que o ITBI mede
não é a área que o portal anuncia — a conversão entre as duas é por prédio, vale
de 1,00 a 2,13, e hoje é uma constante da cidade.

## O que foi medido

Todas as medidas abaixo saem do Postgres local (507.706 linhas de ITBI de BH,
253.549 endereços de cadastro, 29.135 anúncios) e de sondagem ao vivo do
QuintoAndar. Os scripts estão em `scripts/` (ver Tarefa 12).

### 1. A área do ITBI não é imprecisa — é outra medida, e é exata

Razão entre `transactions.built_area_acquired` e
`registry_addresses.median_unit_area` no mesmo endereço, apartamento
residencial, janela de 24 meses, n=40.561:

| p25 | p50 | p75 |
| ---: | ---: | ---: |
| 0,995 | **1,000** | 1,013 |

`built_area_acquired` **é** o `AREA_CONSTRUCAO` do cadastro. Mesma régua, mesma
fonte, erro zero. O portal anuncia área útil. O problema nunca foi ruído no
cartório; é diferença de definição.

### 2. A conversão é por prédio, e fingir que é da cidade custa 18,4%

`k = area_cadastro / area_anunciada`, por prédio (n=99, ≥3 ITBIs e ≥2 anúncios):

| p10 | p25 | p50 | p75 | p90 |
| ---: | ---: | ---: | ---: | ---: |
| 1,00 | 1,34 | **1,70** | 1,99 | 2,13 |

Assumir o k global custa **18,4% de erro mediano e 42,4% no p90**. É a mesma
ordem de grandeza do desconto que o produto chama de oportunidade, e é o maior
termo de erro do sistema — maior que a diferença entre qualquer par de tiers.

### 3. O "efeito tamanho" do fator de calibração é artefato de área

`k` por faixa de área anunciada:

| faixa | n | k |
| --- | ---: | ---: |
| < 60 m² | 145 | 1,983 |
| 60–90 | 390 | 1,732 |
| 90–130 | 546 | 1,500 |
| 130–180 | 207 | 1,418 |
| 180–250 | 126 | 1,003 |
| > 250 | 116 | 1,028 |

k cai 1,98 → 1,00 entre a menor e a maior faixa: razão **1,98**. O README
reporta o fator de calibração indo de 2,55x (<60 m²) a 1,27x (>250 m²): razão
**2,01**. É o mesmo número. `AREA_BANDS` está absorvendo um erro de medida e
sendo descrito como comportamento de mercado.

> ⚠️ **A medida 4 abaixo está certa no que mede e errada no que conclui.** Ela
> compara réguas depois de uma recalibração *global*, que é muito mais grosseira
> do que a calibração por bairro e faixa de área que o produto usa. Implementada
> e medida contra a calibração de verdade, a substituição de área **piora**. Veja
> "O que a validação cruzada disse".

### 4. Tirar a área do cálculo corta a cauda (medida enganosa)

Prever o preço pedido de anúncios cujo prédio tem ≥3 ITBIs, n=652. O erro é a
dispersão depois de calibrar pela mediana global, que é o que a calibração já
faz hoje:

| régua | p50 | p75 | **p90** |
| --- | ---: | ---: | ---: |
| A) R$/m² ITBI × área anunciada (hoje) | 19,3% | 38,1% | **67,9%** |
| B) valor mediano da unidade no prédio (sem área) | 20,4% | 29,5% | **42,0%** |
| C) R$/m² ITBI × área do cadastro | 19,5% | 29,7% | 42,6% |

A mediana não se move — a calibração já come o viés central. **O p90 cai 26
pontos.** Essa cauda é onde nascem os alertas falsos de "85% abaixo", e
`SCORE_IMPLAUSIBLE` existe hoje para suprimi-los depois do fato.

B e C são equivalentes porque a área do ITBI é a do cadastro (medida 1). **C é a
forma escolhida**: mantém a escada de R$/m² intacta e troca só qual área
multiplica, então generaliza para o prédio heterogêneo e para os tiers de rua e
bairro sem um segundo caminho de código.

### 5. IPTU como âncora sem área — testado, rejeitado

IPTU declarado pelo anunciante (Loft e VivaReal, n=365) contra a
`calc_base_value` do ITBI no mesmo endereço: alíquota implícita mediana de
0,082% com **erro p90 de 955%**. O número declarado pelo anunciante não sustenta
nada. Não implementar.

### 6. QuintoAndar: campos que a busca em massa já devolve

Sondagem ao vivo de `house-listing-search/v3/search/list` — o mesmo endpoint
que `app/market_collectors/quintoandar.py` já chama. Custo zero, é só somar à
lista `FIELDS`. Preenchimento medido em 1.000 anúncios de BH:

| campo | preenchimento | o que é |
| --- | ---: | --- |
| `condoId` | **998/1000** | id do prédio |
| `condominium` | 1000/1000 | condomínio mensal |
| `iptu` | 849/1000 | IPTU mensal |
| `condoName` | 272/1000 | nome do prédio |
| `amenities`, `installations` | — | comodidades da unidade e do prédio |
| `isFurnished`, `visitStatus`, `coverImage` | — | — |

Recusados pelo gateway (respondem com o campo ausente): área discriminada, ano
de construção, qualquer campo de data, CEP, andar.

**`condoId` é um identificador rigoroso de prédio.** Agrupando os 998 anúncios
por ele, o espalhamento da coordenada dentro de um grupo é **0 m na mediana e 13
m no máximo** (179 grupos com ≥2 anúncios). Ou seja: o QuintoAndar já publica a
identidade do prédio, e o `endereco_geo` resolvido por proximidade de lote não
precisa mais adivinhar de qual prédio o anúncio é — só de qual **número** ele é.

### 7. QuintoAndar: diretório público de condomínios, com o número da rua

`https://www.quintoandar.com.br/condominio/{slug}-{hashId}`

- Indexado em `sitemap-v3-condos-part-0000..0003.xml`; `robots.txt` libera
  `/condominio/*` (`Allow: /`, e o diretório não está entre os `Disallow`).
- **19.117 páginas de Belo Horizonte**, 9.750 já com o número no próprio slug.
- Responde a `curl` server-side. Sem cookie, sem browser, sem sessão.
- O payload vem no `__NEXT_DATA__` da página, em `condoInfo`:

```json
{"hashId":"1d47sjeomd","name":null,
 "slug":"rua-professor-moraes-444-funcionarios-belo-horizonte",
 "lat":-19.937088,"lng":-43.931404,
 "address":"Rua Professor Moraes","number":"444","zipCode":"30150-370",
 "neighborhood":"Funcionários",
 "minArea":27,"maxArea":58,"minBedrooms":1,"maxBedrooms":2,
 "minBathrooms":1,"maxBathrooms":2,"maxParkingSlots":2,
 "features":{"doorman":"NightAndDayShift",
   "installations":[{"key":"PORTARIA_24H","value":"SIM"},
                    {"key":"ELEVADOR","value":"SIM"},
                    {"key":"ACADEMIA","value":"SIM"},
                    {"key":"PISCINA","value":"SIM"}]}}
```

Validado em 59 condomínios de BH sorteados do sitemap:

| medida | resultado |
| --- | ---: |
| trazem `number` | 59/59 |
| casam com o cadastro da PBH por rua+número | **49/59 (83%)** |
| distância entre o ponto do condo e o lote do cadastro | **p50 8 m, p90 24 m** |
| têm ITBI de 24 meses no mesmo endereço | 33/59 (56%) |
| distância entre o ponto do condo e o anúncio do QA | **p50 1 m, máx 27 m** |

**Isto encerra a limitação "QuintoAndar e Loft não publicam o número da rua".**

### 8. A cadeia de identidade que sai daí

```
anuncio QuintoAndar --condoId (99,8%)--> grupo de predio (espalhamento 0 m)
grupo de predio     --coordenada (p50 1 m)--> pagina /condominio  --> numero da rua
numero da rua       --rua+numero (83%)--> cadastro PBH --> area por unidade, padrao
cadastro PBH        --rua+numero--> ITBI no endereco exato
```

A Loft publica coordenada em 99,3% dos anúncios (medido em
`app/domain/buildings.py`), então entra na cadeia a partir do segundo passo. O
VivaReal já publica o número e entra direto no terceiro.

## Decisões

### D1 — A área de referência  ~~decidida~~ **revertida, ver o fim do documento**

Introduzir `area_referencia`: a área daquele anúncio **em espaço de cadastro**,
que é o mesmo espaço do ITBI. Ela substitui `area_util × AREA_MATCH_FACTOR`
tanto na escolha dos comparáveis quanto no cálculo do preço.

Ordem de resolução:

1. **Prédio conhecido e homogêneo** (`unit_area_dispersion <= 0,30`):
   `area_referencia = median_unit_area`.
2. **Prédio conhecido e heterogêneo**: casamento por posto. Ordenam-se as áreas
   anunciadas dos anúncios ativos daquele prédio e o perfil de áreas do cadastro
   (decis, ver D2); o anúncio no posto *p* recebe a área do cadastro no posto
   *p*. Com um anúncio só no prédio, o posto é a mediana.
3. **Prédio desconhecido**: `area_util × AREA_MATCH_FACTOR`, como hoje. Sem
   prédio não há o que melhorar, e o tier já é rua ou bairro.

O fator de calibração passa a ser medido **na mesma área**:
`(preco_anunciado / area_referencia) / preco_m2_ref`. Sem contaminação de
definição de área, é o prêmio de anúncio puro.

`preco_estimado = preco_m2_mediano × fator × area_referencia`.

### D2 — Perfil de área no cadastro

`registry_addresses` ganha `unit_area_profile` (JSONB): os decis das áreas das
unidades daquele endereço, 11 números. Cabe em qualquer prédio, é o suficiente
para o casamento por posto, e não obriga a guardar unidade a unidade.

Nulo abaixo de 4 unidades — o mesmo piso que `unit_area_dispersion` já usa,
porque abaixo disso não há quartil e três apartamentos não são evidência.

### D3 — Coleta do diretório de condomínios

Sob demanda, dirigida por anúncio: filtra o sitemap pelas ruas que têm anúncio
ativo na cidade, e busca só essas páginas. Incremental por `<lastmod>`.
Ritmo de 1 req/s, o mesmo piso dos coletores. Isso troca 19.117 requisições por
alguns milhares e alcança ~100% do que a nota usa.

### D4 — Não implementar

- IPTU como âncora de valor (medida 5).
- Faixas de área no fator de calibração. A medida 3 sugeria que elas eram a
  conversão de área disfarçada; como a substituição de área foi revertida, elas
  continuam sendo o mecanismo que absorve essa conversão, e **ficam**.

## O que fica de fora

- Cidades além de Belo Horizonte: a cadeia depende do cadastro municipal, que só
  BH publica hoje.
- Casas (`CA`). O cadastro tem o tipo, mas o diretório de condomínios é de
  prédio e a validação toda foi em `AP`.
- ToS do QuintoAndar. Continua decisão do dono, como já registrado em
  `docs/quintoandar-overnight-resumo.md`.


---

# O que a validação cruzada disse

A decisão D1 foi implementada por inteiro — `area_referencia`, perfil de decis,
casamento por posto, calibração medida na mesma área — e então validada com
`scripts/validar_calibracao.py`, que esconde 20% dos anúncios ativos, monta a
calibração com os 80% restantes e prevê o preço pedido de cada escondido.

**Ela piora, em todas as variantes testadas.** 4.972 previsões, mesma semente,
mesmo conjunto escondido:

| variante | p50 | p75 | p90 |
| --- | ---: | ---: | ---: |
| **controle — fator único da cidade (o que está no código)** | **21,6%** | **39,6%** | **64,4%** |
| área do cadastro no lugar da anunciada (1ª implementação) | 23,7% | 44,7% | 76,3% |
| `k` do prédio aplicado à área anunciada, ≥2 anúncios no prédio | 24,8% | 47,0% | 75,8% |
| idem, ≥3 | 24,5% | 46,7% | 76,1% |
| idem, ≥5 | 23,1% | 44,4% | 72,9% |
| idem, ≥8 | 22,3% | 42,7% | 70,9% |
| idem, ≥12 | 22,2% | 41,2% | 68,3% |
| ≥2 + calibração separada por origem da área | 24,2% | 44,9% | 71,7% |
| ≥8 + calibração separada por origem da área | 22,1% | 41,8% | 68,5% |
| área do cadastro **só** na janela de comparáveis | 24,3% | 45,6% | 80,2% |

A correção converge para o controle conforme o limiar sobe — porque cada
degrau desliga a correção para mais anúncios — e **nunca o ultrapassa**.

## Por que

Duas razões, e as duas são sobre identificação, não sobre a medida da razão `k`
estar errada (ela não está: 1,00 no p10 a 2,13 no p90, como a seção 2 mostra).

1. **A calibração já fazia esse trabalho, e melhor.** O fator é medido por
   bairro × faixa de área × padrão de acabamento, e cada célula dessas já
   absorve a *mediana* da conversão de área dos prédios que ela contém. O que
   sobrava para o `k` por prédio corrigir era o desvio dentro da célula — e um
   `k` estimado a partir de dois a doze anúncios do prédio carrega mais ruído do
   que esse desvio.

2. **Com poucos anúncios no prédio, `k` não é identificável.** "Unidade pequena
   num prédio de unidades grandes" e "prédio cujo `k` é pequeno" produzem a
   mesma observação. A primeira implementação, que trocava a área anunciada pela
   mediana do prédio, chegava a descartar o único sinal específico da unidade —
   e o preço disso apareceu inteiro no tier de bairro amplo, onde a referência
   não tem mais nada segurando a estimativa: a mediana foi de 37,3% para 72,1%,
   e o p90 de 103,9% para 605,5%.

## O que foi mantido

- `registry_addresses.unit_area_profile` — os onze decis das áreas das unidades.
  É dado barato, já coletado, e é a entrada de qualquer nova tentativa.
- Toda a cadeia de **identidade de prédio** (seções 6, 7 e 8), que é
  independente da área e resolve outro problema: em que endereço o anúncio está.

## O que teria de mudar para valer a pena

Uma fonte de `k` que **não dependa de contar anúncios do prédio**. As
candidatas, em ordem de plausibilidade:

- `minArea`/`maxArea` do diretório de condomínios, que são área anunciada
  agregada pelo próprio portal sobre todo o histórico do prédio — muito mais
  fundo do que os anúncios ativos de hoje;
- um `k` predito por atributos do prédio (padrão de acabamento, número de
  unidades, instalações), estimado uma vez sobre os prédios que têm anúncios
  suficientes e aplicado aos que não têm;
- o desfecho (`listing_outcomes`), que quando amadurecer dá o preço real de
  fechamento e permite medir `k` contra transação em vez de contra pedido.

Enquanto nenhuma delas existir, o fator único da cidade é a melhor resposta
disponível, e é ela que está no código.
