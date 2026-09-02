# QuintoAndar spike — live probe notes

Fire: step 3 empty-lat/lon kill-test. Local: 2026-08-13T23:56:01-03:00.
Headers: accept application/json, origin/referer https://www.quintoandar.com.br. No cookie.
Query: houseType/lat/lon/condo/area/beds/baths all empty strings.
Sequential, 2.0s pause. Stop on HTTP 403/429.

## Summary

- attempted: 50/50
- stopped: completed sample
- HTTP 200: 0/50 (0.0%)
- ≥1 item: 0/50
- status counts: {400: 50}
- bucket totals: {'sale.sameCondo': 0, 'sale.neighborhood': 0, 'rent.sameCondo': 0, 'rent.neighborhood': 0}
- rentPrice fill: n/a (0 rent items)
- rent.sameCondo hist: {'0': 50, '1-3': 0, '4-10': 0, '11+': 0}
- negotiatedAt lag days (from sampled items): n=0 min=None p50=None p90=None max=None
- empty lat/lon verdict: **FAIL — 50/50 HTTP 400, 0 items. Not 429/403.**
- geocode: empty lat/lon failed; BrasilAPI CEP v2 retry on 5 Belvedere addresses. All 5 geocoded; all 5 retries still HTTP 400 (lift = 0). Four CEPs resolved to the same city-level point `-19.92083,-43.93778`; only `30320-540` looked rooftop-ish (`-19.97132,-43.94452`). Retry still sent empty `houseType`/condo/beds/baths — so this does **not** prove lat/lon is useless, only that filling coords while leaving other query keys as empty strings still 400s.

## 400 body (same shape on every call)

One follow-up GET after the 50-call pass, same URL as address #1, to persist the payload (the loop only kept keys):

```json
{"timestamp":"2026-08-14T02:58:49.634+00:00","status":400,"error":"Bad Request","path":"/v1/condo/negotiations/Belo%20Horizonte/Rua%20Desembargador%20Jorge%20Fontana/80"}
```

No field-level validation message. Bytes ~166–170. Looks like a Spring/gateway generic 400 (empty strings on typed query params is the leading hypothesis).

## Per-address (empty lat/lon)

| # | HTTP | items | sale.same | sale.nbh | rent.same | rent.nbh | neighborhood | street | n |
|--:|-----:|------:|----------:|---------:|----------:|---------:|--------------|--------|--:|
| 1 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Rua Desembargador Jorge Fontana | 80 |
| 2 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Rua Sebastiao Fabiano Dias | 210 |
| 3 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Rod Stael Mary Bicalho Motta Magalhaes | 345 |
| 4 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Rua Juvenal Melo Senra | 395 |
| 5 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Rua Jornalista Djalma Andrade | 46 |
| 6 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Ave Luiz Paulo Franco | 500 |
| 7 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Rua Elza Brandao Rodarte | 393 |
| 8 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Rua Engenheiro Walter Kurrle | 51 |
| 9 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Rua Rodrigo Otavio Coutinho | 230 |
| 10 | 400 | 0 | 0 | 0 | 0 | 0 | BELVEDERE | Rua Maestro Arthur Bosmans | 55 |
| 11 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Rua Bernardo Guimaraes | 166 |
| 12 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Rua Santa Rita Durao | 20 |
| 13 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Ave Afonso Pena | 3111 |
| 14 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Ave Do Contorno | 4480 |
| 15 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Rua Piaui | 1571 |
| 16 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Rua Claudio Manoel | 197 |
| 17 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Ave Brasil | 1438 |
| 18 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Rua Pernambuco | 353 |
| 19 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Rua Dos Timbiras | 802 |
| 20 | 400 | 0 | 0 | 0 | 0 | 0 | FUNCIONARIOS | Pca Coronel Benjamin Guimaraes | 65 |
| 21 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Ave Bias Fortes | 783 |
| 22 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Rua Dos Aimores | 2001 |
| 23 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Rua Dos Timbiras | 2072 |
| 24 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Ave Alvares Cabral | 551 |
| 25 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Rua Dos Guajajaras | 885 |
| 26 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Rua Rio De Janeiro | 2121 |
| 27 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Rua Curitiba | 1544 |
| 28 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Rua Antonio Aleixo | 353 |
| 29 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Rua Da Bahia | 2696 |
| 30 | 400 | 0 | 0 | 0 | 0 | 0 | LOURDES | Rua Sao Paulo | 1628 |
| 31 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Rua Dos Timbiras | 2500 |
| 32 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Rua Dos Guajajaras | 1268 |
| 33 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Ave Alvares Cabral | 1777 |
| 34 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Rua Felipe Dos Santos | 760 |
| 35 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Rua Paracatu | 1154 |
| 36 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Ave Do Contorno | 8000 |
| 37 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Ave Olegario Maciel | 1748 |
| 38 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Rua Mato Grosso | 755 |
| 39 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Rua Goncalves Dias | 2525 |
| 40 | 400 | 0 | 0 | 0 | 0 | 0 | SANTO AGOSTINHO | Rua Dos Aimores | 2414 |
| 41 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Rua Rio Grande Do Norte | 784 |
| 42 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Rua Antonio De Albuquerque | 54 |
| 43 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Rua Professor Moraes | 600 |
| 44 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Ave Getulio Vargas | 1300 |
| 45 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Rua Goncalves Dias | 720 |
| 46 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Ave Do Contorno | 6170 |
| 47 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Rua Alagoas | 1314 |
| 48 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Rua Tome De Souza | 950 |
| 49 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Rua Fernandes Tourinho | 470 |
| 50 | 400 | 0 | 0 | 0 | 0 | 0 | SAVASSI | Rua Paraiba | 1279 |

## CEP-geocode retry (max 5)

- BELVEDERE RUA DESEMBARGADOR JORGE FONTANA 80 cep=30320-670: geocode_ok=True lat=-19.92083 lon=-43.93778 err=None retry={'status': 400, 'item_total': 0, 'has_item': False, 'counts': {'sale.sameCondo': 0, 'sale.neighborhood': 0, 'rent.sameCondo': 0, 'rent.neighborhood': 0}, 'error': 'HTTPError 400'}
- BELVEDERE RUA SEBASTIAO FABIANO DIAS 210 cep=30320-690: geocode_ok=True lat=-19.92083 lon=-43.93778 err=None retry={'status': 400, 'item_total': 0, 'has_item': False, 'counts': {'sale.sameCondo': 0, 'sale.neighborhood': 0, 'rent.sameCondo': 0, 'rent.neighborhood': 0}, 'error': 'HTTPError 400'}
- BELVEDERE ROD STAEL MARY BICALHO MOTTA MAGALHAES 345 cep=30320-760: geocode_ok=True lat=-19.92083 lon=-43.93778 err=None retry={'status': 400, 'item_total': 0, 'has_item': False, 'counts': {'sale.sameCondo': 0, 'sale.neighborhood': 0, 'rent.sameCondo': 0, 'rent.neighborhood': 0}, 'error': 'HTTPError 400'}
- BELVEDERE RUA JUVENAL MELO SENRA 395 cep=30320-660: geocode_ok=True lat=-19.92083 lon=-43.93778 err=None retry={'status': 400, 'item_total': 0, 'has_item': False, 'counts': {'sale.sameCondo': 0, 'sale.neighborhood': 0, 'rent.sameCondo': 0, 'rent.neighborhood': 0}, 'error': 'HTTPError 400'}
- BELVEDERE RUA JORNALISTA DJALMA ANDRADE 46 cep=30320-540: geocode_ok=True lat=-19.9713232 lon=-43.9445239 err=None retry={'status': 400, 'item_total': 0, 'has_item': False, 'counts': {'sale.sameCondo': 0, 'sale.neighborhood': 0, 'rent.sameCondo': 0, 'rent.neighborhood': 0}, 'error': 'HTTPError 400'}

## Errors / first payload keys

- #1 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]
- #2 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]
- #3 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]
- #4 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]
- #5 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]
- #6 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]
- #7 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]
- #8 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]
- #9 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]
- #10 HTTP 400 keys=['error', 'path', 'status', 'timestamp'] err=HTTPError 400 sample=[]

Non-200 bodies (truncated):
- #1 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Desembargador%20Jorge%20Fontana/80?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #2 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Sebastiao%20Fabiano%20Dias/210?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #3 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rod%20Stael%20Mary%20Bicalho%20Motta%20Magalhaes/345?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #4 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Juvenal%20Melo%20Senra/395?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #5 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Jornalista%20Djalma%20Andrade/46?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #6 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Luiz%20Paulo%20Franco/500?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #7 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Elza%20Brandao%20Rodarte/393?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #8 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Engenheiro%20Walter%20Kurrle/51?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #9 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Rodrigo%20Otavio%20Coutinho/230?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #10 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Maestro%20Arthur%20Bosmans/55?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #11 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Bernardo%20Guimaraes/166?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #12 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Santa%20Rita%20Durao/20?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #13 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Afonso%20Pena/3111?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #14 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Do%20Contorno/4480?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #15 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Piaui/1571?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #16 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Claudio%20Manoel/197?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #17 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Brasil/1438?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #18 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Pernambuco/353?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #19 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Dos%20Timbiras/802?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #20 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Pca%20Coronel%20Benjamin%20Guimaraes/65?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #21 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Bias%20Fortes/783?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #22 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Dos%20Aimores/2001?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #23 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Dos%20Timbiras/2072?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #24 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Alvares%20Cabral/551?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #25 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Dos%20Guajajaras/885?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #26 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Rio%20De%20Janeiro/2121?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #27 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Curitiba/1544?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #28 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Antonio%20Aleixo/353?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #29 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Da%20Bahia/2696?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #30 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Sao%20Paulo/1628?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #31 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Dos%20Timbiras/2500?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #32 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Dos%20Guajajaras/1268?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #33 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Alvares%20Cabral/1777?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #34 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Felipe%20Dos%20Santos/760?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #35 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Paracatu/1154?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #36 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Do%20Contorno/8000?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #37 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Olegario%20Maciel/1748?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #38 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Mato%20Grosso/755?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #39 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Goncalves%20Dias/2525?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #40 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Dos%20Aimores/2414?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #41 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Rio%20Grande%20Do%20Norte/784?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #42 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Antonio%20De%20Albuquerque/54?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #43 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Professor%20Moraes/600?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #44 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Getulio%20Vargas/1300?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #45 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Goncalves%20Dias/720?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #46 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Ave%20Do%20Contorno/6170?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #47 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Alagoas/1314?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #48 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Tome%20De%20Souza/950?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #49 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Fernandes%20Tourinho/470?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=
- #50 HTTP 400 err=HTTPError 400 url=https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/condo/negotiations/Belo%20Horizonte/Rua%20Paraiba/1279?houseType=&latitude=&longitude=&condominiumPerMonth=&minArea=&maxArea=&minBedroom=&maxBedroom=&minBathroom=&maxBathroom=

Machine-readable: `quintoandar-spike-step3-results.json`.

## Step 4 — similar-houses / daysOnMarket (2026-08-14 00:24–00:25 -03)

`POST https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/brand-calculator/similar-houses`

Headers: accept/content-type JSON, origin/referer `https://proprietario.quintoandar.com.br/` (auction-monitor reference). **No cookie.** `.env` `QUINTOANDAR_PRICE_SUGGESTION_COOKIE` is empty; did not invent 5AJWT.

Seeds: the 5 Belvedere BrasilAPI CEPs from step 3. Body template (not ITBI-true beds/area): `houseType=APARTMENT`, `businessContext=SALE`, `totalArea=98`, 3/2, condo 1100, percentiles 800k–1.4M.

| # | HTTP | daysOnMarketUntilDealAverage | avail n / daysOnMarket fill | unavail n / lastTimeOnMarket / daysOnMarket | address | coords |
|--:|-----:|-----------------------------:|----------------------------:|---------------------------------------------:|---------|--------|
| 1 | 200 | 130 | 10 / key present (sample 721) | 10 / lastTimeOnMarket present (sample 2026-03-18) / daysOnMarket key present | Jornalista Djalma Andrade 46 | -19.97132,-43.94452 |
| 2 | 200 | 118 | 10 / 10 | 10 / 10 / 0 | Desembargador Jorge Fontana 80 | city centroid |
| 3 | 200 | 118 | 10 / 10 | 10 / 10 / 0 | Sebastiao Fabiano Dias 210 | city centroid |
| 4 | 200 | 118 | 10 / 10 | 10 / 10 / 0 | Rodovia Stael Mary Bicalho Motta Magalhaes 345 | city centroid |
| 5 | 200 | 118 | 10 / 10 | 10 / 10 / 0 | Juvenal Melo Senra 395 | city centroid |

Calls 2–5 share the same BrasilAPI city centroid, so the identical 118 is expected (same neighborhood-level similar set).

**Finding:** `summary.daysOnMarketUntilDealAverage` **returns without a cookie** (5/5 HTTP 200). `available[].daysOnMarket` filled. `unavailable[].lastTimeOnMarket` filled; `unavailable[].daysOnMarket` empty (0/10 on calls 2–5) — matches the known split. Extra top-level key seen: `negotiatedInTheSameCondo`.

Did not persist listing arrays. Machine-readable: `quintoandar-spike-step4-similar-houses.json`.

## Deepening 6 — isolate 400 (2026-08-14 01:24 -03)

Two addresses: auction-monitor control `Rua Ministro Ivan Lins 245` and ITBI `Rua Jornalista Djalma Andrade 46`. Four shapes each, 2s pause, no cookie. Stop rule 403/429 not hit.

| address | path_only | houseType | houseType+lat/lon | full_typed |
|---------|----------:|----------:|------------------:|-----------:|
| Ivan Lins 245 | 400 | 400 | 400 | **200 / 52** (sale.nbh 32, rent.nbh 20, sameCondo 0) |
| Djalma 46 | 400 | 400 | 400 | **200 / 60** (sale.nbh 40, rent.nbh 20, sameCondo 0) |

Fill on full_typed (repeat GET): rentPrice 20/20 both; sale price 100%; negotiatedAt n=52/60; lag days control min 27 p50 138 max 1010; Djalma min 24 p50 173 max 1033.

**400 cause:** missing full typed filter set. Not empty-string-only (omitted keys also 400). Lat/lon insufficient.

Machine-readable: `quintoandar-spike-step6-400-isolate.json`.

## Deepening 7 — sameCondo hunt (2026-08-14 01:53 -03)

10 ITBI addresses, full_typed + BrasilAPI CEP. 10/10 HTTP 200. 9/10 centroid `-19.92083,-43.93778` → 37+20+0+0 items (identical pack). 1/10 local: Guajajaras 1268 `-19.9238084,-43.9461045` → sale.sameCondo=3 (all addressNumber 1268, 316k/430k/450k, Nov 2025). rent.sameCondo=0. rentPrice 200/200. Timbiras 2500 path doubled number (`Rua dos Timbiras 2500/2500`) still 200.

Machine-readable: `quintoandar-spike-step7-samecondo.json`.

## Deepening 8 — remaining CEPs / local-only QA (2026-08-14 02:23 -03)

36 leftover sample CEPs geocoded. 27 centroid, 9 local. QA only local: 9/9 HTTP 200. sameCondo 1/9 — Rua Curitiba 1544 Lourdes rent.sameCondo=1 (houseId 895120025, rentPrice 5610, negotiatedAt 2026-02-06, addressNumber 1544). sale.sameCondo 0. rentPrice 180/180. Sample-wide: 11 local / 39 centroid. Cumulative local QA sameCondo: 2/11.

Machine-readable: `quintoandar-spike-step8-local-cep.json`.

## Deepening 9 — Nominatim rooftop (2026-08-14 02:53 -03)

5 dense centroid buildings. Nominatim all non-centroid. Rio Grande do Norte 784 = place/house house_number=784. QA 5/5 HTTP 200, sameCondo 0/5 (lift 0 vs centroid). Items 60/60/60/60/59.

| addr | lat,lon | class |
|------|---------|-------|
| Jorge Fontana 80 | -19.97723,-43.94532 | highway/residential |
| Timbiras 2500 | -19.93027,-43.92513 | highway/residential |
| Rio Grande do Norte 784 | -19.93237,-43.93135 | place/house |
| Bias Fortes 783 | -19.92504,-43.94380 | highway/secondary |
| Bernardo Guimarães 166 | -19.92902,-43.94109 | highway/residential |

Machine-readable: `quintoandar-spike-step9-rooftop.json`.

## Deepening 10 — ITBI type (2026-08-14 03:24 -03)

No new HTTP. Sample 50 mode: 23 AP+RES, 26 NÃO RESIDENCIAL. Hits both AP+RES (Guajajaras 300/309 AP, Curitiba 99/117 AP). Misses include VC vagas (Djalma 7.8 m², Bernardo 12 m²), SL (Jorge Fontana 80), AC (Rio Grande 784, Bias Fortes 783), LJ (Contorno 6170). AP+RES with coords still miss: Antonio Aleixo 353, Mato Grosso 755, Paraíba 1279, Timbiras 2500.

Machine-readable: `quintoandar-spike-step10-itbi-type.json`.

## Deepening 11 — citywide dense AP+RES (2026-08-14 03:54 -03)

SQL only. Numbered keys ≥10 quitacoes: 10,566 addrs, **9,400 AP+RES (89.0%)**. All numbered: 27,147/90,933 (29.9%) AP+RES, 70.1% of numbered quitacoes. Sample-50 AP+RES 23/50 was biased toward commercial mega-buildings.

Machine-readable: `quintoandar-spike-step11-dense-ap-res.json`.

## Deepening 12 — more AP+RES other bairros (2026-08-14 04:26 -03)

10 new dense AP+RES (not the original 50, not the original 5 bairros). BrasilAPI CEP v2. QA only if non-centroid. Filters staged but unused.

| # | nbh | street | n | CEP | kind |
|--:|-----|--------|--:|-----|------|
| 1 | BURITIS | Eli Seabra Filho 100 | 794 | 30575-740 | centroid |
| 2 | BURITIS | Rubens Caporali Ribeiro 839 | 330 | 30575-857 | centroid |
| 3 | CASTELO | Miguel Perrela 975 | 778 | 31330-290 | centroid |
| 4 | CASTELO | Jornalista Cici Santos 17 | 366 | 31330-296 | centroid |
| 5 | SAGRADA FAMILIA | Genoveva de Souza 879 | 181 | 31030-220 | centroid |
| 6 | SAGRADA FAMILIA | Conselheiro Lafaiete 766 | 85 | 31030-010 | centroid |
| 7 | SANTO ANTONIO | São Domingos do Prata 570 | 129 | 30330-110 | centroid |
| 8 | SANTO ANTONIO | Luiza Carvalho Torres 60 | 119 | 30350-280 | centroid |
| 9 | SION | Patagônia 1023 | 214 | 30320-135 | centroid |
| 10 | SION | Groenlândia 401 | 165 | 30320-060 | centroid |

10/10 centroid `-19.92083,-43.93778`. QA called = 0. Cumulative BrasilAPI: 11 local / 49 centroid.

Machine-readable: `quintoandar-spike-step12-apres-more.json`.

## Deepening 13 — Nominatim on 10 AP+RES (2026-08-14 04:54 -03)

Structured Nominatim 1/2.1s. QA full_typed if non-centroid. Filters: Apartamento, condo 1100, area 40–180, beds 1–4, baths 1–3.

| # | street | nom | class | QA | same |
|--:|--------|-----|-------|---:|-----:|
| 1 | Eli Seabra Filho 100 | -19.97555,-43.97235 | highway/residential | 200 / 77 | **24** (#100) |
| 2 | Rubens Caporali 839 | -19.97670,-43.97674 | highway/tertiary | 200 / 60 | 0 |
| 3 | Miguel Perrela 975 | -19.87529,-43.99394 | highway/secondary | 200 / 69 | **22** (#975) |
| 4 | Cici Santos 17 | fail | — | skip | — |
| 5 | Genoveva de Souza 879 | -19.90673,-43.92209 | highway/residential | 200 / 60 | 0 |
| 6 | Conselheiro Lafaiete 766 | -19.89333,-43.92092 | highway/tertiary | 200 / 59 | 0 |
| 7 | São Domingos do Prata 570 | -19.94531,-43.93651 | highway/residential | 200 / 62 | **2** (#570) |
| 8 | Luiza Carvalho Torres 60 | -19.95046,-43.94418 | highway/residential | 200 / 62 | **2** (#60) |
| 9 | Patagônia 1023 | fail | — | skip | — |
| 10 | Groenlândia 401 | fail | — | skip | — |

Nominatim 7/10, 0 centroid, 0 house#. QA 7/7 200. sameCondo 4/7. rentPrice 166/166. No 429/403. Lift vs deepening 9 (0/5 commercial).

Machine-readable: `quintoandar-spike-step13-apres-nominatim.json`.

## Deepening 14 — similar-houses nic (2026-08-14 05:24 -03)

POST similar-houses, no cookie, proprietario origin. 3 hits + 2 misses. 5/5 HTTP 200.

| seed | neg.same | DOM | nic |
|------|---------:|----:|----:|
| Eli Seabra 100 | 24 | 74 | 2 (street, no #) |
| Guajajaras 1268 | 3 | 113 | 0 |
| Miguel Perrela 975 | 22 | 127 | 0 |
| Timbiras 2500 | 0 | 147 | 0 |
| Genoveva 879 | 0 | 254 | 0 |

nic items: no addressNumber/houseId; lastTimeOnMarket filled; daysOnMarket empty. Presence agree 3/5. nic ≠ negotiations sameCondo.

Machine-readable: `quintoandar-spike-step14-similar-samecondo.json`.

## Deepening 15 — more AP+RES Nominatim (2026-08-14 05:54 -03)

8 new AP+RES, Gutierrez / Ouro Preto / Prado / Serra. Nominatim + full_typed. 8/8 nom ok, 0 centroid. QA 8/8 200. sameCondo 6/8. rentPrice 167/167. # match 28/28.

| street | same |
|--------|-----:|
| Estácio de Sá 900 | 0 |
| Marechal Bitencourt 325 | 3 |
| José Ribeiro Filho 35 | 2 (OSM amenity/fast_food) |
| Zilah Corrêa 461 | 0 |
| Pampas 990 | 8 |
| Esparta 101 | 7 |
| Rádio 20 | 4 |
| Herval 515 | 4 |

Combined AP+RES+coord 12/21. No 429/403.

Machine-readable: `quintoandar-spike-step15-apres-nominatim-more.json`.

## Deepening 16 — ITBI area filter (2026-08-14 06:24 -03)

5 already-geocoded. min/max = med−30 / med+10. 5/5 HTTP 200. miss→hit 0.

| seed | band | prior | now |
|------|------|------:|----:|
| Estácio 900 | 248–288 | 0 | 0 |
| Eli 100 | 53–93 | 24 | 24 |
| Pampas 990 | 86–126 | 8 | 6 |
| Zilah 461 | 58–98 | 0 | 0 |
| São Domingos 570 | 274–314 | 2 | 0 |

ITBI median hid São Domingos (deals smaller than 304 m²). Did not unlock Estácio.

Machine-readable: `quintoandar-spike-step16-itbi-area.json`.

## Deepening 17 — citywide ITBI area (2026-08-14 06:54 -03)

SQL only. 9,400 dense numbered AP+RES. Median area p10/p50/p90 = 55 / 110 / 211. med in 40–180: 7,943 (84.5%). med>180: 1,414 addrs / 31,644 quitacoes / 5% of units in 40–180. No QA.

Machine-readable: `quintoandar-spike-step17-itbi-area-dist.json`.

## Deepening 18 — more AP+RES Nominatim (2026-08-14 07:24 -03)

8 new. Nom 8/8, 0 centroid, 2 house#. QA 8/8 200. sameCondo 7/8. rentPrice 194/194. # match 89/89.

| street | same |
|--------|-----:|
| Deslandes 780 | 2 (building/apartments) |
| Muzambinho 105 | 0 |
| Açucenas 630 | 5 |
| André Fernandes 153 | 7 |
| Teixeira da Costa 342 | 21 |
| Sinfonia 425 | 35 |
| Mem de Sá 160 | 5 |
| Otoni 310 | 14 (place/house) |

Combined 19/29. No 429/403.

Machine-readable: `quintoandar-spike-step18-apres-nominatim-more.json`.

## Deepening 19 — QA vs ITBI prices (2026-08-14 07:54 -03)

No live HTTP. 5 hit buildings, 51 QA sales.

| addr | QA p50 | ITBI 2024+ p50 | Δ |
|------|-------:|---------------:|--:|
| Sinfonia 425 | 290k | 325k | −11% |
| Otoni 310 | 1.30M | 1.18M | +10% |
| Teixeira 342 | 231k | 223k | +4% |
| Perrela 975 | 390k | 360k | +8% |
| Eli 100 | 675k | 608k | +11% |

Machine-readable: `quintoandar-spike-step19-price-vs-itbi.json`.

## Deepening 20 — CA+RES / Casa (2026-08-14 08:24 -03)

6 densest CA+RES. houseType=Casa. Nom 5/6. QA 5/5 200. sameCondo 2/5. rent.same 0. # match 18/18.

| street | same |
|--------|-----:|
| José Silveira 63 | 0 |
| Perimetral 2370 | 4 |
| Miguel Perrela 803 | 14 |
| Warley Martins 566 | skip (nom fail) |
| Nilo Pinheiro 660 | 0 |
| Istambul 20 | 0 |

Machine-readable: `quintoandar-spike-step20-ca-res-nominatim.json`.

## Deepening 21 — negotiatedAt vs ITBI (2026-08-14 08:54 -03)

No live HTTP. 19 hit buildings, 185 QA dates. QA years: 2023=7, 2024=33, 2025=71, 2026=74 (96% 2024+). ITBI same addrs: 4993 quitacoes, 2008–2026, 9.2% 2024+.

Machine-readable: `quintoandar-spike-step21-negotiatedat-vs-itbi.json`.
