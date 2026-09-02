# QuintoAndar condo negotiations — overnight spike

Date: 2026-08-13 night → 2026-08-14 08:55 America/Sao_Paulo  
Branch: `feat/design-escritura`  
Constraint: evidence only. No production ingestion, schema migration, or UI.

ImovelRadar promise stays **ITBI quitado BH / escrituras**, not listings. QA, if ever shown, is a **separate section**. Yield unit and ToS remain owner decisions. Do **not** publish QA deals on SEO pages.

## Question

Can we attach QuintoAndar **closed** condo negotiations to an ITBI address using only what we have (`street`, `street_number`, `postal_code`, `neighborhood` — **no lat/lon**), via:

`GET /customer-facing-bff-api/v1/condo/negotiations/{cidade}/{rua}/{numero}`  
with empty `houseType` / `latitude` / `longitude` / condo / beds / baths?

Secondary: does `daysOnMarketUntilDealAverage` live on a different endpoint, and does that endpoint answer without a 5AJWT cookie?

## Volume (ITBI BH)

Source: local `imovel-radar-postgres-1`, `transactions` where `city = 'belo_horizonte'` (the only city loaded).

| Metric | Value |
|--------|------:|
| Rows | 507,706 |
| Distinct `(street, street_number)` | 93,103 |
| Numbered addresses | 90,933 |
| Missing / empty `street_number` | 6,986 rows → 2,170 streets-without-number |
| Median quitacoes / address | 1 |
| Mean | 5.45 |
| p90 | 11 |
| Max | 1,320 |
| ≥10 quitacoes | 10,678 addresses (**11.47%**) holding **65.81%** of rows |

QA path `{cidade}/{rua}/{numero}` can only use numbered addresses. Half the base is a one-off quitacao. Density is in the tail.

## Sample

50 numbered addresses, 10 each from Savassi / Lourdes / Belvedere / Funcionários / Santo Agostinho.

Rule: ≥10 quitacoes, one densest address per street, top 10 streets per neighborhood (so the kill-test is not one mega-building). Sample quitacoes min 52 / max 538 / sum 8,744. Every row has a single CEP. No lat/lon.

List: `docs/quintoandar-spike-sample-addresses.json`.

## Empty lat/lon kill-test

50 sequential GETs, 2.0s pause, headers `accept: application/json` + origin/referer `https://www.quintoandar.com.br`. **No cookie.** Query keys all sent as empty strings (`houseType`, `latitude`, `longitude`, `condominiumPerMonth`, `minArea`, `maxArea`, `minBedroom`, `maxBedroom`, `minBathroom`, `maxBathroom`). Street = title-case of ITBI text.

Did **not** hit 429/403.

| Metric | Value |
|--------|------:|
| Attempted | 50/50 |
| HTTP 200 | **0%** (0/50) |
| Coverage (≥1 item) | **0%** (0/50) |
| Status | **400 × 50** |
| sale.sameCondo | 0 |
| sale.neighborhood | 0 |
| rent.sameCondo | 0 |
| rent.neighborhood | 0 |
| rentPrice fill | n/a (0 rent items) |
| rent.sameCondo distribution | 50 addresses at 0 |
| negotiatedAt lag | n/a (0 items) |

400 body (same shape on every call, no field errors):

```json
{"timestamp":"2026-08-14T02:58:49.634+00:00","status":400,"error":"Bad Request","path":"/v1/condo/negotiations/Belo%20Horizonte/Rua%20Desembargador%20Jorge%20Fontana/80"}
```

**Empty-lat/lon verdict: FAIL.** Gateway-style 400, not a WAF/ToS block. Empty strings on typed query params is the leading hypothesis; this pass does not prove the path is dead if params are omitted or typed.

Raw: `docs/quintoandar-spike-raw.md`, `docs/quintoandar-spike-step3-results.json`.

### Prescribed CEP-geocode retry

BrasilAPI `GET /api/cep/v2/{cep}` on 5 Belvedere addresses. 5/5 returned coordinates. 4/5 collapsed to city centroid `-19.92083,-43.93778`; 1/5 (`30320-540`, Jornalista Djalma Andrade 46) looked local (`-19.97132,-43.94452`).

Retried negotiations with lat/lon filled, **other keys still empty strings**: **5/5 HTTP 400, lift = 0**.

This does **not** isolate “coords required” vs “empty-string typed params rejected”.

## Coverage cutoff

With **0% HTTP 200** there is no empirical coverage curve. A shipping cutoff is academic until a request shape returns items.

Suggested later (not applied): do not ingest until ≥30% of a dense-address sample returns ≥1 `sale.sameCondo` item, measured on a request shape that is actually 200. Do not geocode the whole 90,933 numbered base to find that shape.

## daysOnMarket endpoint

`daysOnMarket` is **not** on `/condo/negotiations` (that payload, when it works, has `negotiatedAt` only). It lives on:

`POST /customer-facing-bff-api/v1/brand-calculator/similar-houses`

`.env` `QUINTOANDAR_PRICE_SUGGESTION_COOKIE` is empty. Cookie was **not** invented. Auction-monitor sends this call from `origin/referer https://proprietario.quintoandar.com.br` and only attaches 5AJWT if present.

5/5 HTTP **200 without a cookie**, using the 5 BrasilAPI CEP seeds. Body used plausible apartment defaults (98 m², 3/2, condo 1100, percentiles 800k–1.4M) — not ITBI-true unit attributes (`built_area_acquired` on the rooftop seed is a fraction, median 7.79 m²).

| Call | Seed | `daysOnMarketUntilDealAverage` | available `daysOnMarket` | unavailable `lastTimeOnMarket` | unavailable `daysOnMarket` |
|-----:|------|-------------------------------:|-------------------------:|-------------------------------:|---------------------------:|
| 1 | Djalma Andrade 46 (local coords) | **130** | present (sample 721) | present | key present |
| 2–5 | 4 addresses, same city centroid | **118** | 10/10 filled | 10/10 filled | **0/10** |

Calls 2–5 sharing one centroid explains the identical 118.

Confirmed split:

- `summary.daysOnMarketUntilDealAverage` = days until deal (returns)
- `available[].daysOnMarket` = active listing age (filled)
- `unavailable[].lastTimeOnMarket` = exit time; **no duration** (0/10 filled)

Extra top-level key seen: `negotiatedInTheSameCondo`. Listing arrays were not persisted.

`docs/quintoandar-spike-step4-similar-houses.json`.

## Deepening — isolate the 400 (2026-08-14 01:24 -03)

8 sequential GETs, 2s pause, no cookie. Two addresses × four request shapes. Empty-string query is **not** required to fail — **omitting** keys also 400s until the full typed filter set is present.

Addresses:

- control: `Rua Ministro Ivan Lins / 245` (auction-monitor unit-test seed, Dona Clara)
- ITBI: `Rua Jornalista Djalma Andrade / 46` (dense Belvedere + BrasilAPI local coords)

| Variant | Query | Control | ITBI Djalma |
|---------|-------|---------|-------------|
| path_only | none | 400 / 0 | 400 / 0 |
| houseType_only | `houseType=Apartamento` | 400 / 0 | 400 / 0 |
| houseType_lat_lon | + numeric lat/lon | 400 / 0 | 400 / 0 |
| **full_typed** | houseType + lat/lon + condo + min/max area + min/max beds/baths | **200 / 52** | **200 / 60** |

Full_typed bucket counts (sameCondo stayed **0** on both):

| Address | sale.same | sale.nbh | rent.same | rent.nbh | rentPrice fill | negotiatedAt lag days |
|---------|----------:|---------:|----------:|---------:|---------------:|----------------------|
| Ivan Lins 245 | 0 | 32 | 0 | 20 | 20/20 (100%) | min 27 / p50 138 / max 1010 |
| Djalma 46 | 0 | 40 | 0 | 20 | 20/20 (100%) | min 24 / p50 173 / max 1033 |

Sale `price` fill 32/32 and 40/40. Neighborhood names look local (Djalma → Belvedere / Santa Lúcia / Sion / São Bento; Ivan Lins → Castelo / Ouro Preto / Pampulha belt).

**Isolation:** the 400 is **missing typed filters**, not a dead endpoint and not “empty string vs omitted”. Lat/lon alone is not enough. ITBI cannot supply condo/area/beds/baths; those were **invented defaults**. `sale.sameCondo` / `rent.sameCondo` did not fire — we got **neighborhood** closed deals, not building-level.

`docs/quintoandar-spike-step6-400-isolate.json`.

## Deepening 7 — sameCondo hunt (2026-08-14 01:53–01:56 -03)

10 ITBI sample addresses (2 per target neighborhood; skipped Djalma 46). BrasilAPI CEP → full_typed GET (same invented filters as Djalma). Sequential, 2s pause, no cookie. No 429/403.

| Metric | Value |
|--------|------:|
| Geocoded | 10/10 |
| City-centroid CEP (`-19.92083,-43.93778`) | **9/10** |
| HTTP 200 | **10/10** |
| ≥1 item | 10/10 |
| Addresses with `sameCondo` > 0 | **1/10** |
| sale.sameCondo / sale.nbh / rent.sameCondo / rent.nbh | **3 / 373 / 0 / 200** |
| rentPrice fill | **200/200 (100%)** |

The 9 centroid calls returned the **same** pack: 37 sale.neighborhood + 20 rent.neighborhood + 0 sameCondo (57 items). Path street (accented BrasilAPI name vs ITBI title-case) did not matter.

The one local CEP: **Rua dos Guajajaras 1268**, Santo Agostinho, `30180-107`, coords `-19.9238084,-43.9461045`. **sale.sameCondo = 3**, all three at addressNumber **1268**, prices 316k / 430k / 450k, negotiatedAt 2025-11-04..22 (lag ~265–283 days). rent.sameCondo still 0.

Djalma 46 had local coords earlier and still sameCondo 0 — local coords look **necessary but not sufficient**.

Note: BrasilAPI returned `street="Rua dos Timbiras 2500"` for that CEP; the path doubled the number. Still 200 (centroid pack).

`docs/quintoandar-spike-step7-samecondo.json`.

## Deepening 8 — remaining sample CEPs, QA only if local (2026-08-14 02:23–02:27 -03)

36 leftover sample addresses (not probed in 6/7). BrasilAPI first; QA only when coords ≠ BH centroid. No 429/403.

| Metric | Value |
|--------|------:|
| CEPs geocoded this fire | 36/36 ok |
| City centroid | 27 |
| Local coords | **9** |
| QA called | 9/9 (cap 10) |
| HTTP 200 | **9/9** |
| Addresses with sameCondo > 0 | **1/9** |
| sale.same / sale.nbh / rent.same / rent.nbh | **0 / 350 / 1 / 179** |
| rentPrice fill | **180/180 (100%)** |

Hit: **Rua Curitiba 1544**, Lourdes, `30170-122`, `-19.93019,-43.94445`. **rent.sameCondo=1** at addressNumber 1544, rentPrice 5610, negotiatedAt 2026-02-06. sale.sameCondo 0.

Across the 50-address sample (all CEPs now known): **11 local / 39 centroid**. Local-CEP QA so far (incl. Djalma + Guajajaras): **2/11 sameCondo hits** (Guajajaras sale×3, Curitiba rent×1). Local coords ≈ 18% sameCondo, not 100%.

`docs/quintoandar-spike-step8-local-cep.json`.

## Deepening 9 — Nominatim rooftop vs CEP-centroid (2026-08-14 02:53–02:55 -03)

5 densest **centroid-CEP** buildings (quitacoes 538 / 527 / 298 / 284 / 254). Nominatim structured search (1 req / ≥2s, identifying UA). Then full_typed QA with Nominatim coords. No 429/403.

| Address | Nominatim | class | house# | QA items | sameCondo | vs centroid |
|---------|-----------|-------|--------|---------:|----------:|-------------|
| Jorge Fontana 80 | -19.97723,-43.94532 | highway/residential | — | 60 | **0** | 0 → 0 |
| Timbiras 2500 | -19.93027,-43.92513 | highway/residential | — | 60 | **0** | 0 → 0 |
| Rio Grande do Norte 784 | -19.93237,-43.93135 | **place/house** | 784 | 60 | **0** | 0 → 0 |
| Bias Fortes 783 | -19.92504,-43.94380 | highway/secondary | — | 60 | **0** | 0 → 0 |
| Bernardo Guimarães 166 | -19.92902,-43.94109 | highway/residential | — | 59 | **0** | 0 → 0 |

**Lift = 0.** All five Nominatim points were non-centroid (one true house match). sameCondo still empty. Better street geocode does **not** unlock building deals. QA appears to need the condo in its own graph, not just a nearby lat/lon.

`docs/quintoandar-spike-step9-rooftop.json`.

## Deepening 10 — why those two buildings (2026-08-14 03:24 -03)

No new QA/Nominatim. Local ITBI + auction-monitor read-only.

auction-monitor only hits `/condo/negotiations` for listings that already have `condominium_hash_id` from QA property details. **sameCondo is QA’s condo graph**, not “many ITBI quitacoes at this number.”

The 50-sample is **not** 50 residential condos. Mode construction/occupation:

| | n |
|--|--:|
| AP + RESIDENCIAL | **23** |
| NÃO RESIDENCIAL | **26** |

Hits vs misses (local CEP or Nominatim coords):

| ITBI type | Addresses compared | sameCondo > 0 |
|-----------|-------------------:|--------------:|
| AP + RESIDENCIAL | 6 | **2** (Guajajaras 1268 sale×3; Curitiba 1544 rent×1) |
| AC / SL / VC / LJ (mostly NÃO RESIDENCIAL) | 10 | **0** |

VC rows have tiny `built_area_acquired` (Djalma 7.8 m², Bernardo 12 m², Contorno 8000 10 m²) — garage/vaga, not apartments. Jorge Fontana 80 (538 quitacoes) is **SL / NÃO RESIDENCIAL**. Rio Grande do Norte 784 is **AC / NÃO RESIDENCIAL** even with a Nominatim house hit.

Timbiras 2500 is AP+RESIDENCIAL (527 quitacoes, 501 AP) and still sameCondo 0 — type is **necessary in this sample, not sufficient**. QA never listed that building (or has no closed deals there).

`docs/quintoandar-spike-step10-itbi-type.json`.

## Deepening 11 — citywide AP+RES among dense numbered (2026-08-14 03:54 -03)

SQL only. Key = `(street, street_number)` to match the QA path (step 1’s 10,678 included unnumbered streets).

| Universe | Addresses | AP+RES | % addrs | AP+RES quitacoes |
|----------|----------:|-------:|--------:|-----------------:|
| All numbered | 90,933 | 27,147 | **29.9%** | 350,855 (70.1%) |
| Dense ≥10 quitacoes | **10,566** | **9,400** | **89.0%** | 272,569 (82.1%) |

The 50-address “densest street in five bairros” sample was **23/50 AP+RES** because it overweighted commercial mega-buildings (SL/AC/VC). Citywide, the ≥10 tail is almost all apartments.

Does **not** flip the no-go: those 9,400 still lack lat/lon/beds/condo, and sameCondo still needs QA’s condo graph (Timbiras 2500). Do not geocode this pool.

`docs/quintoandar-spike-step11-dense-ap-res.json`.

## Deepening 12 — more AP+RES, other neighborhoods (2026-08-14 04:27 -03)

The 50-address sample was commercial-biased and only five bairros. New draw: **10** numbered ≥10-quitacao **AP+RES** addresses, two densest streets each from Buritis / Castelo / Sagrada Família / Santo Antônio / Sion. BrasilAPI CEP; QA only if coords ≠ BH centroid. Not a 9,400 geocode.

| Address | quitacoes | med_area m² | CEP | coords |
|---------|----------:|------------:|-----|--------|
| Eli Seabra Filho 100 | 794 | 82.9 | 30575-740 | centroid |
| Rubens Caporali Ribeiro 839 | 330 | 203.5 | 30575-857 | centroid |
| Miguel Perrela 975 | 778 | 60.0 | 31330-290 | centroid |
| Jornalista Cici Santos 17 | 366 | 70.5 | 31330-296 | centroid |
| Genoveva de Souza 879 | 181 | 142.1 | 31030-220 | centroid |
| Conselheiro Lafaiete 766 | 85 | 135.7 | 31030-010 | centroid |
| São Domingos do Prata 570 | 129 | 304.3 | 30330-110 | centroid |
| Luiza Carvalho Torres 60 | 119 | 101.2 | 30350-280 | centroid |
| Patagônia 1023 | 214 | 169.9 | 30320-135 | centroid |
| Groenlândia 401 | 165 | 165.2 | 30320-060 | centroid |

**10/10 city centroid. QA not called.** Cumulative BrasilAPI: **11 local / 49 centroid** (18.3%). Picking the “right” ITBI type in other neighborhoods does not fix CEP geocode.

`docs/quintoandar-spike-step12-apres-more.json`.

## Deepening 13 — Nominatim on those 10 AP+RES (2026-08-14 04:54 -03)

BrasilAPI was 10/10 centroid. Nominatim structured search (identifying UA, 2.1s), then full_typed QA. Not a 9,400 geocode.

| Address | Nominatim | class | QA items | sameCondo |
|---------|-----------|-------|---------:|----------:|
| Eli Seabra Filho 100 | -19.97555,-43.97235 | highway/residential | 77 | **24** (sale 5 + rent 19) all #100 |
| Rubens Caporali Ribeiro 839 | -19.97670,-43.97674 | highway/tertiary | 60 | 0 |
| Miguel Perrela 975 | -19.87529,-43.99394 | highway/secondary | 69 | **22** (sale 6 + rent 16) all #975 |
| Cici Santos 17 | no hit | — | — | — |
| Genoveva de Souza 879 | -19.90673,-43.92209 | highway/residential | 60 | 0 |
| Conselheiro Lafaiete 766 | -19.89333,-43.92092 | highway/tertiary | 59 | 0 |
| São Domingos do Prata 570 | -19.94531,-43.93651 | highway/residential | 62 | **2** (sale) both #570 |
| Luiza Carvalho Torres 60 | -19.95046,-43.94418 | highway/residential | 62 | **2** (sale) both #60 |
| Patagônia 1023 | no hit | — | — | — |
| Groenlândia 401 | no hit | — | — | — |

**Lift vs CEP: 4/7 sameCondo** (0 house-level OSM matches; street coords were enough). rentPrice **166/166**. negotiatedAt p50 ~97–147 days. No 429/403.

Deepening 9 (commercial-heavy) was 0/5. Combined AP+RES + non-centroid coords: **6/13 (~46%)**. Nominatim street + invented filters + apartment type can unlock building deals. Still not ITBI-only.

`docs/quintoandar-spike-step13-apres-nominatim.json`.

## Deepening 14 — similar-houses `negotiatedInTheSameCondo` (2026-08-14 05:25 -03)

Step 4 saw the key but did not measure it. 5 POSTs, no cookie, same invented SALE body as step 4. 3 known `/condo/negotiations` hits + 2 misses.

| Seed | negotiations sameCondo | DOM | nic n |
|------|-----------------------:|----:|------:|
| Eli Seabra Filho 100 | 24 | 74 | **2** (street match, `sameCondo=true`, no house#; lastTimeOnMarket filled, daysOnMarket empty) |
| Guajajaras 1268 | 3 | 113 | **0** |
| Miguel Perrela 975 | 22 | 127 | **0** |
| Timbiras 2500 | 0 | 147 | 0 |
| Genoveva 879 | 0 | 254 | 0 |

**5/5 HTTP 200.** Presence agreement only **3/5**. nic did not fire on two buildings that already had 3 and 22 closed sameCondo deals. Items lack `addressNumber` / `houseId`. DOM is location-sensitive (74–254), unlike the four centroid-118 calls in step 4.

**Finding:** `negotiatedInTheSameCondo` is a sparser comps list, not a replacement for negotiations sameCondo. daysOnMarketUntilDealAverage still returns without a cookie.

`docs/quintoandar-spike-step14-similar-samecondo.json`.

## Deepening 15 — more AP+RES Nominatim (2026-08-14 05:55 -03)

8 new dense AP+RES, two streets each from Gutierrez / Ouro Preto / Prado / Serra. Same Nominatim + full_typed shape as 13. Not a 9,400 geocode.

| Address | Nominatim | class | QA items | sameCondo |
|---------|-----------|-------|---------:|----------:|
| Estácio de Sá 900 | -19.94146,-43.95759 | highway/residential | 60 | 0 |
| Marechal Bitencourt 325 | -19.93698,-43.96322 | highway/residential | 63 | **3** (sale 2 + rent 1) all #325 |
| José Ribeiro Filho 35 | -19.87157,-43.99008 | amenity/fast_food (house#) | 57 | **2** (1+1) all #35 |
| Zilah Corrêa de Araújo 461 | -19.87140,-43.98447 | highway/residential | 60 | 0 |
| Pampas 990 | -19.91943,-43.96438 | highway/residential | 54 | **8** (sale 5 + rent 3) all #990 |
| Esparta 101 | -19.92786,-43.96842 | highway/residential | 62 | **7** (sale 6 + rent 1) all #101 |
| Rádio 20 | -19.93332,-43.91922 | highway/residential | 61 | **4** (2+2) all #20 |
| Herval 515 | -19.93881,-43.91875 | highway/residential | 58 | **4** (sale 3 + rent 1) all #515 |

**6/8 sameCondo.** Nominatim 8/8 non-centroid. rentPrice **167/167**. addressNumber match **28/28**. Combined AP+RES + non-centroid: **12/21 (~57%)**.

`docs/quintoandar-spike-step15-apres-nominatim-more.json`.

## Deepening 16 — ITBI area as filter (2026-08-14 06:25 -03)

Hypothesis: invented `maxArea=180` hid sameCondo on large-median buildings (Estácio 278 m²). 5 already-geocoded addresses, auction-monitor band around ITBI median (`−30 / +10`). Condo/beds still invented. No new geocode.

| Address | band | prior (40–180) | ITBI band |
|---------|------|---------------:|----------:|
| Estácio de Sá 900 | 248–288 | 0 | **0** |
| Eli Seabra Filho 100 | 53–93 | 24 | **24** |
| Pampas 990 | 86–126 | 8 | **6** |
| Zilah Corrêa 461 | 58–98 | 0 | **0** |
| São Domingos do Prata 570 | 274–314 | 2 | **0** |

**Miss→hit = 0.** Estácio is not an area-filter miss. São Domingos’s two deals disappeared — they were **smaller** than the 304 m² ITBI median, so the “honest” ITBI band hid them. Pampas lost 2. Eli held.

ITBI `built_area_acquired` median is **not** a reliable area filter (mix of units / vagas / outliers). Wide invented 40–180 has higher sameCondo recall.

`docs/quintoandar-spike-step16-itbi-area.json`.

## Deepening 17 — citywide area vs 40–180 (2026-08-14 06:54 -03)

SQL on all **9,400** numbered dense AP+RES. No live QA / no geocode.

Address-level median `built_area_acquired`: p10 **55** / p50 **110** / p90 **211** m².

| Median band | Addresses | Quitacoes | Mean share of units in 40–180 |
|-------------|----------:|----------:|------------------------------:|
| 40–180 | **7,943 (84.5%)** | 238,612 | 91.6% |
| >180 | **1,414 (15.0%)** | 31,644 | **5.0%** (417 have any) |
| <40 | 43 | 2,313 | 28.3% |

Invented 40–180 is a decent default for ~85% of the AP+RES tail. The 15% large-median buildings are almost empty of 40–180 stock — same pattern as São Domingos (40–180 found 2 small deals; ITBI-median band found 0). Still invented beds/condo.

`docs/quintoandar-spike-step17-itbi-area-dist.json`.

## Deepening 18 — more AP+RES Nominatim (2026-08-14 07:25 -03)

8 new: Anchieta / Nova Suíssa / Santa Amélia / Santa Efigênia. Same Nominatim + full_typed. Not a 9,400 geocode.

| Address | Nominatim | class | sameCondo |
|---------|-----------|-------|----------:|
| Francisco Deslandes 780 | house | building/apartments | **2** (1+1) all #780 |
| Muzambinho 105 | street | highway/residential | 0 |
| Açucenas 630 | street | highway/residential | **5** all #630 |
| André Fernandes 153 | street | highway/residential | **7** all #153 |
| Teixeira da Costa 342 | street | highway/residential | **21** all #342 |
| Sinfonia 425 | street | highway/tertiary | **35** (17+18) all #425 |
| Mem de Sá 160 | street | highway/tertiary | **5** all #160 |
| Otoni 310 | house | place/house | **14** (sale) all #310 |

**7/8 sameCondo.** First true OSM `building/apartments` rooftop. rentPrice **194/194**. Combined AP+RES + non-centroid: **19/29 (~66%)**.

`docs/quintoandar-spike-step18-apres-nominatim-more.json`.

## Deepening 19 — QA prices vs ITBI (2026-08-14 07:54 -03)

Persisted sameCondo **sale** prices vs `declared_value` at the same numbered address. No new HTTP.

| Address | QA sale n / p50 | ITBI AP+RES 2024+ n / p50 | QA ÷ ITBI |
|---------|----------------:|--------------------------:|----------:|
| Sinfonia 425 | 17 / 290k | 39 / 325k | −11% |
| Otoni 310 | 14 / 1.30M | 19 / 1.18M | +10% |
| Teixeira da Costa 342 | 9 / 231k | 48 / 223k | +4% |
| Miguel Perrela 975 | 6 / 390k | 88 / 360k | +8% |
| Eli Seabra 100 | 5 / 675k | 55 / 608k | +11% |

QA p50 is **within ~4–11%** of recent ITBI medians (51 QA sales). All-time ITBI median is stale (Eli 334k vs 608k). Same building, similar price level — still QA negotiated listings, not quitacoes.

`docs/quintoandar-spike-step19-price-vs-itbi.json`.

## Deepening 20 — casas (CA+RES) (2026-08-14 08:25 -03)

ITBI has 212 dense numbered CA+RES. 6 densest, Nominatim, `houseType=Casa` (auction-monitor mapping). Not the 9,400 AP pool.

| Address | Nominatim | QA items | sameCondo |
|---------|-----------|---------:|----------:|
| José Silveira 63 | street | 55 | 0 |
| Perimetral 2370 | street | 23 | **4** sale all #2370 |
| Miguel Perrela 803 | street | 58 | **14** sale all #803 |
| Warley Martins 566 | fail | — | — |
| Nilo Pinheiro 660 | street | 44 | 0 |
| Istambul 20 | street | 50 | 0 |

**2/5 (40%)** sameCondo. `Casa` returns 200. rent.sameCondo 0. Weaker than AP+RES 19/29. Perrela 803 (CA) hit while 975 (AP) also hit — type at the number matters.

`docs/quintoandar-spike-step20-ca-res-nominatim.json`.

## Deepening 21 — clocks (2026-08-14 08:54 -03)

185 persisted sameCondo `negotiatedAt` vs ITBI `settlement_date` on the same 19 addresses. No new HTTP.

| | QA | ITBI |
|--|---:|-----:|
| n | 185 | 4,993 |
| span | Aug 2023 – Jul 2026 | Jan 2008 – Jun 2026 |
| share 2024+ | **96%** | **9%** |
| share 2025–26 | **78%** | ~7% |

QA closed deals are almost all last ~2 years. ITBI at those buildings is 18 years of quitacoes. Complementary time series; mixing them on one timeline would be misleading (see UI block).

`docs/quintoandar-spike-step21-negotiatedat-vs-itbi.json`.

## Go / no-go

**No-go** for production `/condo/negotiations` ingestion from ITBI-only fields.

Why:

1. The specified empty-param request is 50/50 HTTP 400, **0% coverage**.
2. Omitting keys, `houseType` alone, or `houseType`+lat/lon still 400. The gateway wants the **full typed filter set** (condo + area + beds/baths + coords + houseType).
3. ITBI has no rooftop lat/lon and no reliable beds/baths/condo. Invented filters + city-centroid CEP yield a **repeated neighborhood pack**, not building deals.
4. `sameCondo` only on **AP + RESIDENCIAL** with non-centroid coords: original **2/6**, Nominatim batches **4/7 + 6/8 + 7/8**, combined **19/29 (~66%)**. Commercial towers (deepening 9) stayed 0/5. Misses remain (Muzambinho, Timbiras 2500, Estácio, Zilah).
5. Yield unit and ToS are still undecided.

**Not a no-go on QuintoAndar as a whole.** Endpoint is alive. Street-level Nominatim + typed apartment filters can return building deals. `similar-houses` returns `daysOnMarketUntilDealAverage` without a cookie. That is not “street/number from ITBI, empty query.”

No schema sketch (no-go).

Next leftover: none required. Do not geocode the 9,400.

## UI block

If QA ever ships:

- **Separate block**, never mixed into the ITBI / escritura timeline.
- Do not render QA deals on public SEO neighborhood/street/property pages.
- Label as QuintoAndar closed negotiations (or similar-houses comps), not quitacoes.
- days-on-market, if shown, comes from `similar-houses`, not from negotiations.

## Sources

- Progress: `docs/quintoandar-overnight-progress.md`
- Sample: `docs/quintoandar-spike-sample-addresses.json`
- Live notes: `docs/quintoandar-spike-raw.md`
- Step 3 JSON: `docs/quintoandar-spike-step3-results.json`
- Step 4 JSON: `docs/quintoandar-spike-step4-similar-houses.json`
- Step 6 isolate: `docs/quintoandar-spike-step6-400-isolate.json`
- Step 7 sameCondo: `docs/quintoandar-spike-step7-samecondo.json`
- Step 8 local CEP: `docs/quintoandar-spike-step8-local-cep.json`
- Step 9 rooftop: `docs/quintoandar-spike-step9-rooftop.json`
- Step 10 ITBI type: `docs/quintoandar-spike-step10-itbi-type.json`
- Step 11 dense AP+RES: `docs/quintoandar-spike-step11-dense-ap-res.json`
- Step 12 more AP+RES CEPs: `docs/quintoandar-spike-step12-apres-more.json`
- Step 13 AP+RES Nominatim: `docs/quintoandar-spike-step13-apres-nominatim.json`
- Step 14 similar-houses nic: `docs/quintoandar-spike-step14-similar-samecondo.json`
- Step 15 more AP+RES Nominatim: `docs/quintoandar-spike-step15-apres-nominatim-more.json`
- Step 16 ITBI area filter: `docs/quintoandar-spike-step16-itbi-area.json`
- Step 17 ITBI area distribution: `docs/quintoandar-spike-step17-itbi-area-dist.json`
- Step 18 more AP+RES Nominatim: `docs/quintoandar-spike-step18-apres-nominatim-more.json`
- Step 19 QA vs ITBI prices: `docs/quintoandar-spike-step19-price-vs-itbi.json`
- Step 20 CA+RES Nominatim: `docs/quintoandar-spike-step20-ca-res-nominatim.json`
- Step 21 negotiatedAt vs ITBI: `docs/quintoandar-spike-step21-negotiatedat-vs-itbi.json`
- Reference (read-only): `auction-monitor/crawler/quintoandar_condo_negotiations.py`, `quintoandar_similar_houses.py`
