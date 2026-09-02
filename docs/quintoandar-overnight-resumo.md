# Resumo — spike QuintoAndar (acordar)

Atualizado: **2026-08-14 09:23 America/Sao_Paulo** (CUTOFF — loop encerrado)  
Relatório: `docs/quintoandar-condo-negotiations-spike.md`  
Progresso: `docs/quintoandar-overnight-progress.md`  
Branch: `feat/design-escritura`

ImovelRadar continua **ITBI quitado BH / escrituras**, não anúncios. Nada de ingestão, migration ou UI foi implementado. auction-monitor não foi alterado. Não geocodificar os 9.400.

## O que foi tentado

1. **Volume ITBI BH** — SQL no Postgres local. Ok.
2. **Amostra 50 endereços densos** (Savassi, Lourdes, Belvedere, Funcionários, Santo Agostinho). Ok.
3. **Kill-test** `/condo/negotiations` com `houseType`/lat/lon/condo/quartos/banheiros vazios — **50/50 HTTP 400**, 0 itens.
4. **Retry CEP** (5 Belvedere, só preencheu lat/lon) — ainda 400, lift 0.
5. **similar-houses** sem cookie — 5/5 200; `daysOnMarketUntilDealAverage` volta; `negotiatedInTheSameCondo` **não** substitui sameCondo.
6. **Isolar o 400** — path only / houseType / houseType+lat/lon = 400. Só **full typed** = 200.
7–8. CEP BrasilAPI no sample 50: **11 locais / 39 centróide BH**. sameCondo só em 2/11 locais.
9. Nominatim em 5 torres comerciais densas — lift sameCondo **0/5**.
10–11. Tipo ITBI: hits só em AP+RES; cidade tem **9.400** densos AP+RES (89% da cauda ≥10). Amostra original era enviesada comercial (23/50).
12. Mais 10 AP+RES em outros bairros — BrasilAPI **10/10 centróide**; QA não chamado.
13 / 15 / 18. Nominatim + full typed em AP+RES — sameCondo **19/29 (~66%)**.
14. nic em similar-houses vs negotiations — acordo de presença só 3/5.
16–17. Área ITBI como min/max: **não** destrava misses; banda 40–180 cabe em 84,5% das medianas.
19. Preços QA vs ITBI 2024+ no mesmo prédio (~4–11%).
20. CA+RES + `houseType=Casa` — sameCondo **2/5 (40%)**.
21. Relógios: `negotiatedAt` QA vs `settlement_date` ITBI nos 19 hits (sem HTTP novo).

Nenhuma 429/403 em toda a noite. Sem ingestão / schema / UI.

## O que efetivamente deu certo (números reais)

- **507.706** linhas ITBI BH; **90.933** endereços numerados; ≥10 quitações = **10.566** (numerados), dos quais **9.400 (89%)** são modo AP+RES.
- Endpoint vivo: full typed + coords não-centróide devolve 200 e itens.
- AP+RES + Nominatim (não centróide): **19/29 (~66%)** com `sameCondo > 0`. `addressNumber` bateu 100% nos hits. `rentPrice` 100% nos aluguéis.
- CA+RES + `Casa`: **2/5**. Endpoint aceita o tipo (não 400).
- 185 deals QA sameCondo: **96% em 2024+**, **78% em 2025–26**. ITBI nos mesmos 19 endereços: **4.993** quitações 2008–2026, só **9,2%** em 2024+.
- Preços de venda QA no mesmo patamar do ITBI recente (p50 ~−11% a +11% em 5 prédios).
- `similar-houses` responde **sem cookie** (`daysOnMarketUntilDealAverage` presente).

## O que não deu / bloqueou

- **Params vazios (o teste pedido):** 50/50 **400**, cobertura 0%. Omitir chaves também 400.
- ITBI **não tem** lat/lon, condomínio, quartos, banheiros. Sem esses filtros inventados o gateway recusa.
- CEP BrasilAPI ≈ **centróide de BH** (~82% no sample). Pack de bairro repetido, sameCondo 0.
- Nominatim em torre comercial / SL/AC/VC: sameCondo 0 mesmo com rooftop.
- Misses AP+RES mesmo geocodados (Timbiras 2500, Estácio, Zilah, Muzambinho) — sameCondo é o **grafo de condomínio da QA**, não “muitas quitações neste número”.
- Área ITBI mediana **não** é filtro seguro (esconde deals menores que a mediana).
- nic de similar-houses é mais esparso e sem número do imóvel.
- Cookie 5AJWT ausente no `.env` — não inventado; similar-houses não precisou.
- DB ok a noite toda. Sem 429/403.

## Veredito

**No-go** para ingestão de `/condo/negotiations` a partir **só** dos campos ITBI (rua, número, CEP, bairro).

Por quê: o contrato pedido (GET com params vazios) é 400. O que funciona exige Nominatim + `houseType` + área/quartos/condo **inventados**. Mesmo assim sameCondo ~66% em AP+RES geocodados — e o resultado é **negociação recente de listing**, não escritura.

Sem sketch de schema. Sem UI.

QA pode complementar depois (bloco separado, janela ~2 anos, preços no mesmo patamar do ITBI recente). **Não misturar** na timeline de escritura. **Não publicar** deals QA em páginas SEO.

## Decisões que continuam do dono

- Unidade de **yield**.
- **ToS** / uso de dados QuintoAndar.

Não geocodificar os 9.400. Loop `019ffdde1831` encerrado neste cutoff.
