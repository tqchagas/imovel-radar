# QuintoAndar overnight spike — progress

Branch: `feat/design-escritura`
Started: 2026-08-13 (fresh fire, no prior chat)
Constraint: one increment per fire. No production ingestion/schema/UI.

## Status

| Step | What | State |
|------|------|--------|
| 1 | Volume: distinct BH addresses + quitacoes/address distribution | **DONE** (2026-08-13) |
| 2 | Sample ~50 real BH addresses with dense ITBI (Savassi, Lourdes, Belvedere, Funcionários, Santo Agostinho) | **DONE** (2026-08-13 23:24 -03) |
| 3 | Kill-test `/condo/negotiations` with empty lat/lon/condo/bed/bath | **DONE** (2026-08-13 23:56–23:58 -03) |
| 4 | Optional daysOnMarket probe (max 5 similar-houses calls) | **DONE** (2026-08-14 00:24 -03) |
| 5 | Final report `docs/quintoandar-condo-negotiations-spike.md` | **DONE** (2026-08-14 00:54 -03) |

## Step 1 — volume (Postgres)

Source: local `imovel-radar-postgres-1` (healthy, `127.0.0.1:5433`). Compose was already up; no restart.

Query window: `transactions` where `city = 'belo_horizonte'`.

### Totals

| Metric | Value |
|--------|------:|
| Total transactions (all cities) | 507,706 |
| Cities present | `belo_horizonte` only |
| `COUNT(DISTINCT (street, street_number))` | **93,103** |
| Missing `street` | 0 |
| Missing / empty `street_number` | 6,986 rows |
| Distinct addresses with a street number | 90,933 |

The 93,103 figure includes one synthetic key for `(street, NULL)` pairs: 6,986 rows without a number collapse into **2,170** distinct streets-without-number (93,103 − 90,933). For QuintoAndar path `{cidade}/{rua}/{numero}` only numbered addresses are usable.

### Quitacoes per address (all 93,103 keys)

| Stat | Value |
|------|------:|
| min | 1 |
| p25 | 1 |
| median | 1 |
| p75 | 4 |
| p90 | 11 |
| p95 | 19 |
| p99 | 66 |
| max | 1,320 |
| mean | 5.45 |

### Bucket distribution (all addresses)

| Bucket | Addresses | Quitacoes | % addresses | % quitacoes |
|--------|----------:|----------:|------------:|------------:|
| 1 | 48,192 | 48,192 | 51.76 | 9.49 |
| 2–4 | 24,739 | 62,049 | 26.57 | 12.22 |
| 5–9 | 9,494 | 63,341 | 10.20 | 12.48 |
| 10–19 | 6,185 | 82,394 | 6.64 | 16.23 |
| 20–49 | 3,121 | 92,207 | 3.35 | 18.16 |
| 50–99 | 865 | 59,126 | 0.93 | 11.65 |
| 100–199 | 351 | 48,860 | 0.38 | 9.62 |
| 200+ | 156 | 51,537 | 0.17 | 10.15 |

Half of addresses are one-off quitacoes (~52%). Density lives in the tail: **≥10 quitacoes = 10,678 addresses (11.47%) holding 65.81% of all ITBI rows**. Numbered-only buckets are almost identical (90,933 keys; 200+ still 156).

### Notes for later fires

- Step 2 should sample from numbered, dense addresses in Savassi / Lourdes / Belvedere / Funcionários / Santo Agostinho (likely the 10+ or 20+ buckets).
- No lat/lon on ITBI. Step 3 probes empty lat/lon first.
- Do not publish QA deals on public SEO pages. Yield unit + ToS still undecided.

## Step 2 — sample ~50 dense BH addresses (2026-08-13 23:24 -03)

Persisted: `docs/quintoandar-spike-sample-addresses.json`

Source: same local Postgres, numbered addresses only (`street_number` not null/empty).

Pool in the five named neighborhoods (numbered):

| Neighborhood | Numbered addrs | ≥10 quitacoes | ≥20 | median q | max q |
|--------------|---------------:|--------------:|----:|---------:|------:|
| LOURDES | 852 | 292 | 169 | 4 | 284 |
| SAVASSI | 822 | 282 | 185 | 3 | 298 |
| SANTO AGOSTINHO | 474 | 162 | 106 | 4 | 527 |
| FUNCIONARIOS | 421 | 146 | 92 | 5 | 254 |
| BELVEDERE | 606 | 86 | 65 | 1 | 538 |

Selection: addresses with **≥10 quitacoes**, **one densest address per street**, then **top 10 streets per neighborhood** (50 total). Diversified so step 3 does not hammer a single mega-building.

| Metric | Value |
|--------|------:|
| Sample size | 50 |
| Per neighborhood | 10 / 10 / 10 / 10 / 10 |
| Quitacoes in sample | min 52, max 538, sum 8,744 |
| All have `postal_code` | yes (every row `distinct_ceps` = 1) |
| Lat/lon | none (ITBI has none) |

Every row carries `qa_city_slug` (`Belo Horizonte`) and `qa_street_slug` (title-case, small words de/da/do kept lower) for the `{cidade}/{rua}/{numero}` path. Street text is ITBI as stored (uppercase, no accents: `FUNCIONARIOS`, `GONCALVES`, `AVE DO CONTORNO`).

### Sample (street + number + quitacoes)

**BELVEDERE:** Desembargador Jorge Fontana 80 (538), Sebastiao Fabiano Dias 210 (209), Stael Mary Bicalho Motta Magalhaes 345 (155), Juvenal Melo Senra 395 (109), Jornalista Djalma Andrade 46 (89), Luiz Paulo Franco 500 (86), Elza Brandao Rodarte 393 (69), Engenheiro Walter Kurrle 51 (69), Rodrigo Otavio Coutinho 230 (62), Maestro Arthur Bosmans 55 (52).

**FUNCIONARIOS:** Bernardo Guimaraes 166 (254), Santa Rita Durao 20 (209), Afonso Pena 3111 (194), Contorno 4480 (154), Piaui 1571 (142), Claudio Manoel 197 (123), Brasil 1438 (121), Pernambuco 353 (121), Timbiras 802 (76), Pça Coronel Benjamin Guimaraes 65 (75).

**LOURDES:** Bias Fortes 783 (284), Aimores 2001 (274), Timbiras 2072 (236), Alvares Cabral 551 (146), Guajajaras 885 (133), Rio de Janeiro 2121 (130), Curitiba 1544 (117), Antonio Aleixo 353 (113), Bahia 2696 (101), Sao Paulo 1628 (101).

**SANTO AGOSTINHO:** Timbiras 2500 (527), Guajajaras 1268 (309), Alvares Cabral 1777 (257), Felipe dos Santos 760 (232), Paracatu 1154 (179), Contorno 8000 (163), Olegario Maciel 1748 (153), Mato Grosso 755 (149), Goncalves Dias 2525 (143), Aimores 2414 (117).

**SAVASSI:** Rio Grande do Norte 784 (298), Antonio de Albuquerque 54 (251), Professor Moraes 600 (236), Getulio Vargas 1300 (197), Goncalves Dias 720 (191), Contorno 6170 (185), Alagoas 1314 (176), Tome de Souza 950 (163), Fernandes Tourinho 470 (139), Paraiba 1279 (137).

## Step 3 — empty lat/lon kill-test (2026-08-13 23:56–23:58 -03)

Live notes: `docs/quintoandar-spike-raw.md`. Machine-readable: `docs/quintoandar-spike-step3-results.json`.

Endpoint: `GET .../condo/negotiations/Belo%20Horizonte/{title-cased ITBI street}/{numero}` with empty `houseType`, `latitude`, `longitude`, `condominiumPerMonth`, `minArea`, `maxArea`, `minBedroom`, `maxBedroom`, `minBathroom`, `maxBathroom`. Headers: accept JSON + origin/referer quintoandar. **No cookie.** Sequential, 2.0s pause.

| Metric | Value |
|--------|------:|
| Attempted | 50/50 (did not stop — no 429/403) |
| HTTP 200 | **0%** (0/50) |
| ≥1 item | **0%** (0/50) |
| Status | **400 × 50** |
| sale.sameCondo / sale.neighborhood / rent.sameCondo / rent.neighborhood | 0 / 0 / 0 / 0 |
| rentPrice fill | n/a (0 rent items) |
| rent.sameCondo hist | 50 addresses at 0 |
| negotiatedAt lag | n/a (0 items) |

400 body (generic, no field errors): `{"status":400,"error":"Bad Request","path":"/v1/condo/negotiations/Belo%20Horizonte/Rua%20Desembargador%20Jorge%20Fontana/80",...}`.

**Verdict: empty lat/lon (with the other query keys also empty strings) does not work.** Gateway-style 400, not a ToS/WAF block.

### CEP-geocode retry (prescribed one small set)

BrasilAPI `GET /api/cep/v2/{cep}` on 5 Belvedere addresses. All 5 returned coordinates. 4/5 collapsed to city centroid `-19.92083,-43.93778`; 1/5 (`30320-540`) looked local (`-19.97132,-43.94452`). Retried negotiations with lat/lon filled, **other keys still empty strings**: **5/5 HTTP 400, lift = 0**.

This retry does not isolate "coords required" vs "empty-string typed params rejected". Next deepening (after report, leftover fires): omit empty keys; send `houseType=Apartamento`; use BrasilAPI accented street names.

Documented seeds for step 4 (CEP coords exist even though negotiations 400'd).

## Step 4 — daysOnMarket / similar-houses (2026-08-14 00:24–00:25 -03)

`.env` has empty `QUINTOANDAR_PRICE_SUGGESTION_COOKIE`. Did **not** invent a cookie. Probed anyway (instruction: if cookie missing, probe once and skip if auth-blocked). Endpoint answered **without** 5AJWT, so used the remaining 4-call budget on the other step-3 CEP seeds.

| Metric | Value |
|--------|------:|
| Calls | 5/5 |
| HTTP 200 | **5/5** (no 401/403/429) |
| `summary.daysOnMarketUntilDealAverage` present | **5/5** (130 on rooftop seed; 118 on 4 city-centroid seeds) |
| `available[].daysOnMarket` | filled (10/10 on calls 2–5) |
| `unavailable[].lastTimeOnMarket` | filled (10/10) |
| `unavailable[].daysOnMarket` | empty (0/10 on calls 2–5) |

Cookie is **not** required for this endpoint (at least from `proprietario.quintoandar.com.br` origin). Listings were not persisted.

## Step 5 — spike report (2026-08-14 00:54 -03)

Wrote `docs/quintoandar-condo-negotiations-spike.md` and wake-up `docs/quintoandar-overnight-resumo.md`.

**Go/no-go: no-go** for production `/condo/negotiations` from ITBI-only empty-param GETs (0% 200, 0 items). No schema sketch. `similar-houses` is a separate finding (5/5 200, `daysOnMarketUntilDealAverage` returns, no cookie).

## Deepening 6 — isolate 400 (2026-08-14 01:24 -03)

8 GETs (2 addresses × 4 shapes) + 2 fill-measurement repeats of the working URLs. No 429/403.

| Shape | Result |
|-------|--------|
| path only / houseType only / houseType+lat/lon | **400 / 0 items** on both addresses |
| full typed (houseType + lat/lon + condo + area + beds/baths) | **200** — control 52 items, ITBI Djalma 60 items |

sameCondo stayed 0/0. Neighborhood only. rentPrice 100% on rent items. negotiatedAt p50 ~138d (control) / ~173d (Djalma). Endpoint is alive; empty/partial query is the 400. ITBI still cannot supply the required filters without inventing them.

JSON: `docs/quintoandar-spike-step6-400-isolate.json`. Report + resumo refreshed. **Still no-go** for ITBI-only ingestion.

## Deepening 7 — sameCondo on 10 ITBI addresses (2026-08-14 01:53–01:56 -03)

10 sample addresses, 2 per neighborhood, full_typed + BrasilAPI CEP. **10/10 HTTP 200**. 9/10 CEP = city centroid → identical 57-item neighborhood pack, sameCondo 0. **1/10 local CEP** (Guajajaras 1268, `-19.9238,-43.9461`) → **sale.sameCondo=3**, all at number 1268. rentPrice 200/200. No 429/403.

JSON: `docs/quintoandar-spike-step7-samecondo.json`. Report + resumo refreshed. **Still no-go** for ITBI-only ingestion; sameCondo needs non-centroid coords + typed filters.

## Deepening 8 — remaining CEPs, QA only local (2026-08-14 02:23–02:27 -03)

36 leftover sample CEPs: 36/36 BrasilAPI ok, **27 centroid / 9 local**. QA on the 9 local: **9/9 HTTP 200**, sameCondo on **1/9** (Curitiba 1544 Lourdes, rent.sameCondo=1 at number 1544, rentPrice 5610). rentPrice 180/180. No 429/403.

Full 50-sample CEP map: **11 local / 39 centroid**. Local-CEP QA cumulative: **2/11** sameCondo (Guajajaras sale×3, Curitiba rent×1).

JSON: `docs/quintoandar-spike-step8-local-cep.json`. Report + resumo refreshed. **Still no-go** for ITBI-only.

## Deepening 9 — Nominatim rooftop vs centroid (2026-08-14 02:53–02:55 -03)

5 dense centroid-CEP buildings. Nominatim 5/5 local (1 `place/house` at Rio Grande do Norte 784). Full_typed QA **5/5 HTTP 200**, **sameCondo lift 0** (still 0/0). rentPrice 100% on neighborhood rents. No 429/403.

JSON: `docs/quintoandar-spike-step9-rooftop.json`. Report + resumo refreshed. **Still no-go.** Better geocode does not unlock sameCondo.

## Deepening 10 — ITBI type vs sameCondo (2026-08-14 03:24 -03)

No live QA. Sample 50: **23 AP+RES / 26 NÃO RESIDENCIAL**. sameCondo only on AP+RES: **2/6** with local/rooftop coords (Guajajaras, Curitiba). 0/10 on AC/SL/VC/LJ. Timbiras 2500 is AP+RES and still 0. auction-monitor only calls this API when `condominium_hash_id` already exists.

JSON: `docs/quintoandar-spike-step10-itbi-type.json`. Report + resumo refreshed. **Still no-go.**

## Deepening 11 — dense AP+RES share (2026-08-14 03:54 -03)

SQL only. Numbered `(street, street_number)` ≥10 quitacoes: **10,566** addresses, of which **9,400 (89.0%)** are mode AP+RESIDENCIAL (272,569 quitacoes, 82.1%). All numbered: 27,147/90,933 (29.9%) AP+RES.

The 50-sample overweighted commercial towers (23/50 AP+RES). Citywide dense tail is apartments. Still no-go; do not geocode the 9,400.

JSON: `docs/quintoandar-spike-step11-dense-ap-res.json`. Report + resumo refreshed.

## Deepening 12 — more AP+RES addresses, other bairros (2026-08-14 04:26–04:27 -03)

10 new dense AP+RES numbered addresses **outside** the original 5 bairros (2 densest streets each: Buritis, Castelo, Sagrada Família, Santo Antônio, Sion). BrasilAPI CEP only; QA only if non-centroid. Did **not** geocode the 9,400.

| Metric | Value |
|--------|------:|
| CEPs | 10/10 BrasilAPI 200 |
| City centroid `-19.92083,-43.93778` | **10/10** |
| Local | **0/10** |
| QA called | 0 (centroid skip) |
| 429/403 | none |

Cumulative BrasilAPI on ITBI CEPs: original sample 11 local / 39 centroid; plus these 10 = **11 local / 49 centroid (18.3% local)**. Type-correct + other bairros did not improve CEP quality. Filters were staged (`houseType=Apartamento`, condo 1100, area 40–180, beds 1–4, baths 1–3) but unused.

JSON: `docs/quintoandar-spike-step12-apres-more.json`. Report + resumo refreshed. **Still no-go.**

## Deepening 13 — Nominatim on the 10 AP+RES (2026-08-14 04:54–04:56 -03)

Structured Nominatim (1 req / 2.1s, identifying UA) + full_typed QA if non-centroid. Same invented filters as step 12. Did **not** geocode the 9,400.

| Metric | Value |
|--------|------:|
| Nominatim ok | **7/10** (0 centroid, 0 `place/house`) |
| Nominatim fail | 3 (Cici Santos 17, Patagônia 1023, Groenlândia 401) |
| QA | **7/7 HTTP 200**, no 429/403 |
| sameCondo > 0 | **4/7** |
| sale.same / sale.nbh / rent.same / rent.nbh | **15 / 268 / 35 / 131** |
| rentPrice fill | **166/166 (100%)** |

Hits (all sameCondo `addressNumber` = ITBI number): Eli Seabra Filho 100 (sale 5 + rent 19), Miguel Perrela 975 (sale 6 + rent 16), São Domingos do Prata 570 (sale 2), Luiza Carvalho Torres 60 (sale 2). Misses: Rubens Caporali 839, Genoveva 879, Lafaiete 766.

Contrast deepening 9: Nominatim on commercial-heavy towers = **0/5**. AP+RES + street-level Nominatim **does** lift sameCondo. Combined AP+RES + non-centroid: **6/13** (~46%). Still invented filters.

JSON: `docs/quintoandar-spike-step13-apres-nominatim.json`. Report + resumo refreshed. **Still no-go** (ITBI-only empty params).

## Deepening 14 — similar-houses negotiatedInTheSameCondo (2026-08-14 05:24–05:25 -03)

POST `/brand-calculator/similar-houses`, no cookie, origin `proprietario.quintoandar.com.br`. 3 negotiations hits + 2 misses. Same invented apartment body as step 4 (98 m² / 3/2 / condo 1100 / 800k–1.4M). Sequential, 2s pause.

| Seed | negotiations sameCondo | HTTP | DOM | nic n | nic street match |
|------|-----------------------:|-----:|----:|------:|------------------|
| Eli Seabra Filho 100 | 24 | 200 | **74** | **2** | street yes, no house# |
| Guajajaras 1268 | 3 | 200 | 113 | 0 | — |
| Miguel Perrela 975 | 22 | 200 | 127 | 0 | — |
| Timbiras 2500 (miss) | 0 | 200 | 147 | 0 | — |
| Genoveva 879 (miss) | 0 | 200 | 254 | 0 | — |

**5/5 HTTP 200**, no 429/403. Presence agreement **3/5**. Two large negotiations hits had empty nic. Items have no `addressNumber`/`houseId`; `daysOnMarket` empty; `lastTimeOnMarket` filled (unavailable-like). DOM now varies by place (not the centroid-118 pack). **nic is not a substitute** for `/condo/negotiations` sameCondo.

JSON: `docs/quintoandar-spike-step14-similar-samecondo.json`. Report + resumo refreshed. **Still no-go.**

## Deepening 15 — more AP+RES Nominatim (2026-08-14 05:54–05:56 -03)

8 new dense AP+RES (2 streets each: Gutierrez, Ouro Preto, Prado, Serra). Nominatim + full_typed QA. Did **not** geocode the 9,400.

| Metric | Value |
|--------|------:|
| Nominatim ok | **8/8** (0 centroid; 1 house# = amenity/fast_food) |
| QA | **8/8 HTTP 200**, no 429/403 |
| sameCondo > 0 | **6/8** |
| sale.same / sale.nbh / rent.same / rent.nbh | **19 / 289 / 9 / 158** |
| rentPrice fill | **167/167 (100%)** |
| addressNumber match | **28/28** |

Hits: Marechal Bitencourt 325 (3), José Ribeiro Filho 35 (2), Pampas 990 (8), Esparta 101 (7), Rádio 20 (4), Herval 515 (4). Misses: Estácio de Sá 900, Zilah Corrêa 461.

Combined AP+RES + non-centroid: **12/21 (~57%)** (was 6/13). Still invented filters.

JSON: `docs/quintoandar-spike-step15-apres-nominatim-more.json`. Report + resumo refreshed. **Still no-go.**

## Deepening 16 — ITBI median area as min/max (2026-08-14 06:24–06:25 -03)

5 already-geocoded AP+RES. Replaced invented `40–180` with `round(med_area−30)` / `round(med_area+10)`. Same condo/beds/baths. No new geocode.

| Seed | med m² | band | prior same | new same | delta |
|------|-------:|------|-----------:|---------:|------:|
| Estácio de Sá 900 (miss) | 278 | 248–288 | 0 | **0** | 0 |
| Eli Seabra 100 | 83 | 53–93 | 24 | **24** | 0 |
| Pampas 990 | 116 | 86–126 | 8 | **6** | −2 |
| Zilah 461 (miss) | 88 | 58–98 | 0 | **0** | 0 |
| São Domingos 570 | 304 | 274–314 | 2 | **0** | −2 |

**5/5 HTTP 200.** Miss→hit **0**. ITBI area did **not** unlock Estácio. Wide 40–180 had found São Domingos deals that sit outside the ITBI-median band (those units are smaller than the 304 m² median). ITBI `built_area_acquired` is **not** a safe substitute for invented area filters.

JSON: `docs/quintoandar-spike-step16-itbi-area.json`. Report + resumo refreshed. **Still no-go.**

## Deepening 17 — citywide ITBI area vs invented 40–180 (2026-08-14 06:54 -03)

SQL only on the 9,400 numbered dense AP+RES. No geocode, no QA.

| | addrs | quitacoes | share of units inside 40–180 |
|--|------:|----------:|-----------------------------:|
| med 40–180 | **7,943 (84.5%)** | 238,612 | 91.6% |
| med >180 | **1,414 (15.0%)** | 31,644 | **5.0%** (only 417 have any 40–180 unit) |
| med <40 | 43 | 2,313 | 28.3% |

Address-median area: p10 55 / p50 **110** / p90 211 m². 1,740 addrs have ≥1 unit <20 m² (mean share 2.2%). Invented 40–180 fits most of the pool; the São Domingos/Estácio tail is the 15% large-median stock. Do **not** geocode the 9,400.

JSON: `docs/quintoandar-spike-step17-itbi-area-dist.json`. Report + resumo refreshed. **Still no-go.**

## Deepening 18 — more AP+RES Nominatim (2026-08-14 07:24–07:26 -03)

8 new dense AP+RES (Anchieta, Nova Suíssa, Santa Amélia, Santa Efigênia). Nominatim + full_typed. Did **not** geocode the 9,400.

| Metric | Value |
|--------|------:|
| Nominatim ok | **8/8** (0 centroid; 2 house#: building/apartments + place/house) |
| QA | **8/8 HTTP 200**, no 429/403 |
| sameCondo > 0 | **7/8** |
| sale.same / sale.nbh / rent.same / rent.nbh | **48 / 268 / 41 / 153** |
| rentPrice fill | **194/194 (100%)** |
| addressNumber match | **89/89** |

Hits: Deslandes 780 (2), Açucenas 630 (5), André Fernandes 153 (7), Teixeira da Costa 342 (21), Sinfonia 425 (**35**), Mem de Sá 160 (5), Otoni 310 (14). Miss: Muzambinho 105.

Combined AP+RES + non-centroid: **19/29 (~66%)**. Still invented filters.

JSON: `docs/quintoandar-spike-step18-apres-nominatim-more.json`. Report + resumo refreshed. **Still no-go.**

## Deepening 19 — QA sale prices vs ITBI declared_value (2026-08-14 07:54 -03)

5 hit buildings, persisted sameCondo SALE vs SQL ITBI at same street+number. No new QA/geocode.

| Building | QA n / p50 | ITBI AP+RES 2024+ n / p50 | QA vs ITBI |
|----------|-----------:|--------------------------:|-----------:|
| Sinfonia 425 | 17 / 290k | 39 / 325k | **−11%** |
| Otoni 310 | 14 / 1.30M | 19 / 1.18M | **+10%** |
| Teixeira 342 | 9 / 231k | 48 / 223k | **+4%** |
| Perrela 975 | 6 / 390k | 88 / 360k | **+8%** |
| Eli Seabra 100 | 5 / 675k | 55 / 608k | **+11%** |

All-time ITBI medians are much lower (e.g. Eli 334k). QA p50 sits **~4–11%** of recent ITBI — same ballpark, not a disjoint market. Still not escrituras.

JSON: `docs/quintoandar-spike-step19-price-vs-itbi.json`. Report + resumo refreshed. **Still no-go.**

## Deepening 20 — CA+RES Nominatim / houseType=Casa (2026-08-14 08:24–08:26 -03)

6 densest numbered **CA + RESIDENCIAL** (212 such addresses citywide). Nominatim + full_typed `houseType=Casa`. Did **not** geocode the 9,400 AP+RES.

| Metric | Value |
|--------|------:|
| Nominatim | **5/6** (fail: Warley Martins 566) |
| QA | **5/5 HTTP 200**, no 429/403 |
| sameCondo > 0 | **2/5 (40%)** |
| sale.same / sale.nbh / rent.same / rent.nbh | **18 / 136 / 0 / 76** |
| rentPrice fill | **76/76** |
| addressNumber match | **18/18** |

Hits: Perimetral 2370 (sale 4), Miguel Perrela **803** (sale 14). Misses: José Silveira 63, Nilo Pinheiro 660, Istambul 20. `Casa` is a valid typed houseType (not 400). Rate below AP+RES **19/29 (~66%)**. rent.sameCondo stayed 0.

JSON: `docs/quintoandar-spike-step20-ca-res-nominatim.json`. Report + resumo refreshed. **Still no-go.**

## Deepening 21 — negotiatedAt vs ITBI dates (2026-08-14 08:54 -03)

19 hit buildings with persisted sameCondo dates (185 deals). SQL on those addresses. No new HTTP.

| | QA sameCondo | ITBI same 19 addrs |
|--|-------------:|-------------------:|
| n | 185 | 4,993 |
| span | 2023-08-29 … 2026-07-21 | 2008-01-08 … 2026-06-30 |
| 2024+ | **96.2%** | **9.2%** |
| 2025–26 | **78.4%** (71+74) | 263+92 quitacoes |

QA is a recent listing window; ITBI is a long escritura history. Complementary, not a substitute.

JSON: `docs/quintoandar-spike-step21-negotiatedat-vs-itbi.json`. Report + resumo refreshed. **Still no-go.**

## CUTOFF (2026-08-14 09:23 America/Sao_Paulo)

Clock ≥ 09:00 -03. No new HTTP / SQL / geocode this fire. Refreshed `docs/quintoandar-overnight-resumo.md`. Deleting scheduler `019ffdde1831`.

**Still no-go.** Do **not** geocode the 9,400.
