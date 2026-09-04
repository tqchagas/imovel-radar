# Avaliação de imóvel de leilão

**Data:** 2026-09-04
**Estado:** especificação, com o contrato das fontes verificado ao vivo.

## O problema

Editais de leilão trazem endereço, área e uma avaliação judicial que costuma
estar desatualizada. Falta saber por quanto o imóvel se revende hoje — e essa é
a entrada da calculadora de lance máximo, que já existe fora deste projeto.

O produto atual não responde isso: ele parte de anúncio coletado, e imóvel de
leilão não está anunciado.

## O que foi verificado

Sondagem ao vivo em 2026-09-04. Todos os testes com `curl`, **sem cookie, sem
sessão e sem navegador**.

### 1. O qpreço do anúncio não serve

`POST customer-facing-bff-api/pricing-reports/v1/price-suggestion` lê **apenas**
`id` e ignora o resto do corpo:

| entrada | resposta |
| --- | --- |
| `{"id":"894942131"}` | 200, com faixa e percentis |
| coordenada + atributos, sem `id` | **404** `"House null was not found"` |
| `{"id":"999999999"}` | 404 |

Imóvel de leilão nunca tem `id`. Este endpoint está fora.

### 2. A Calculadora QPreço precifica endereço arbitrário

O produto "quanto vale meu imóvel", em
`proprietario.quintoandar.com.br/novo-imovel/calculadora-de-venda`, roda o mesmo
modelo sobre atributos em vez de sobre um anúncio. São dois endpoints públicos.

**`POST customer-facing-bff-api/v1/brand-calculator/estimate`**

```json
{"bathroomCount":3,"bedroomCount":4,"condominiumPerMonth":1500,"iptuPerYear":4800,
 "suitesCount":2,"parkingSlots":2,"address":"Rua Gonçalves Dias","neighborhood":"Funcionários",
 "city":"Belo Horizonte","state":"MG","country":"Brasil",
 "latitude":-19.932468,"longitude":-43.933033,
 "businessContext":"SALE","houseType":"APARTMENT","floor":8,"totalArea":295,"addressNumber":865}
```

```json
{"suggestedPrice":4513000,
 "suggestedLowerBoundPrice":3817000,"suggestedUpperBoundPrice":5112000,
 "lowerBoundLimit":2903000,"upperBoundLimit":6046500,
 "percentiles":{"10":2903000,"30":3817000,"50":4513000,"70":5112000,"90":6046500},
 "predictionCertainty":"low","suggestionCertainty":"low",
 "dealObjectiveRanges":{"FASTER":{...}}}
```

`totalArea` é **área útil** — é o que o formulário pede na tela.

**`POST customer-facing-bff-api/v1/brand-calculator/similar-houses`**

```json
{"percentile10":2903000,"percentile90":6046500,
 "latitude":-19.932468,"longitude":-43.933033,"condominiumPerMonth":1500,
 "bathroomCount":3,"bedroomCount":4,"totalArea":295,"houseType":"APARTMENT",
 "city":"Belo Horizonte","address":"Rua Gonçalves Dias","number":865,"businessContext":"SALE"}
```

Devolve quatro blocos: `summary`, `unavailableSimilarHouses` (10 **vendidos**),
`availableSimilarHouses` (10 à venda) e `negotiatedInTheSameCondo`. Cada
comparável:

```json
{"houseId":895356778,"price":3100000,"priceM2":10333,"totalArea":300,
 "distance":0.4837,"lastTimeOnMarket":"2026-04-17T11:03:09","bedroomCount":4,
 "address":"Rua Gonçalves Dias","neighborhood":"Funcionários","city":"Belo Horizonte",
 "sameCondo":false,"isFromQuintoAndarSource":true,"houseType":"APARTMENT","parkingSlots":2}
```

### 3. Nenhum lead é criado

A tela dispara um terceiro POST, `v2/brand-calculator/save-lead`, que registra um
`interestId` no funil deles. **Ele é separado e pulável**: `estimate` e
`similar-houses` respondem 200 sem ele e sem sessão. Não chamá-lo é o desenho.

O formulário oferece `relationship` com quatro valores — `Proprietário`,
`Corretor / Representante`, **`Interessado`** (`BUYER`) e `Outro`. O caso deste
projeto é uma opção prevista pelo portal, não um contorno. E o campo só viaja
no `save-lead`, que não será chamado.

### 4. Coordenada é obrigatória, e a falha é silenciosa

O mesmo endereço, sem `latitude`/`longitude`, devolve *"Estimativa indisponível
— não foi possível calcular o preço porque algumas características do imóvel
podem ser muito diferentes da média ou ele está em uma área que..."*.

Coordenada ausente ou errada é **indistinguível de imóvel atípico**. Pior, uma
coordenada errada por 200 m não falha: devolve um número plausível do quarteirão
vizinho. O spike de agosto já mediu que o CEP da BrasilAPI cai no centróide de
Belo Horizonte em ~82% dos casos, então geocodificação automática por CEP está
descartada.

### 5. Cobertura nacional, com honestidade sobre a própria incerteza

| endereço | estimativa | `predictionCertainty` |
| --- | ---: | --- |
| Funcionários, Belo Horizonte | R$ 4.513.000 | low |
| Vila Madalena, São Paulo | R$ 1.094.500 | medium |
| Centro, Itabirito (MG) | R$ 335.000 | low |

`predictionCertainty` é sinal de primeira classe e vai para a tela.

### 6. O projeto já descarta os comparáveis vendidos

`app/pricing/similar_houses.py` chama **este mesmo endpoint** e
`extract_summary` guarda três campos do `summary`. Os dez vendidos, com preço,
data, área, endereço e distância, são jogados fora a cada consulta — em 28.681
anúncios ativos.

É preço de **transação**, que é o que a escada de ITBI inteira existe para
reconstruir, sem os dois meses de atraso do cartório e fora de Belo Horizonte.
Está fora do escopo desta especificação, mas é a descoberta de maior valor dela
e merece plano próprio.

## Decisões

| # | decisão |
| --- | --- |
| D1 | O produto entrega **valor de mercado**. Lance máximo é conta do dono, em calculadora separada. |
| D2 | Duas leituras lado a lado: `suggestedPrice` e a **mediana dos vendidos filtrados**. A divergência entre elas é o sinal de confiança, na mesma forma do `min(nota_itbi, nota_qpreco)`. |
| D3 | Área: campo único, **área útil**, digitada pelo dono. Sem conversão e sem trava — o edital é lido por humano. |
| D4 | Funciona em **qualquer cidade**. QPreço é a espinha; ITBI e cadastro entram como conferência só em Belo Horizonte, e a ausência deles não quebra nada. |
| D5 | Tela `/leilao`, lista acompanhada, com histórico das consultas por imóvel. |
| D6 | Coordenada colada pelo dono. Em Belo Horizonte, pré-preenchida por `portal_buildings` e `registry_addresses` a partir de rua+número, para o dono confirmar. |
| D7 | Cliente HTTP no molde de `app/pricing/similar_houses.py`: ritmo próprio, circuit breaker em 401/403/429, cache com TTL. **`save-lead` nunca é chamado.** |
| D8 | Sem registro de desfecho. Passada a data do leilão, a linha sai da lista ativa. |

### Regras que decorrem das decisões

- **Mediana dos vendidos** usa os comparáveis com área ±20%, mesmo número de
  quartos e distância ≤ 1 km. Os dez crus ficam guardados, para auditoria.
- **Divergência > 15%** entre as duas leituras marca o imóvel como atípico.
- **TTL de 30 dias**, com reconsulta sob demanda.
- Nenhum dado pessoal viaja para o portal, em nenhuma requisição.

## O que fica de fora

- Lance máximo, custos de arremate, reforma, ocupação e dívidas. São entrada da
  calculadora do dono, não deste produto.
- Estado de conservação. O modelo do portal avalia unidade em estado normal, e
  o desconto por condição é julgamento humano.
- Casas e terrenos ficam possíveis (`houseType` aceita), mas nada foi medido
  fora de `APARTMENT`.
- Aproveitar os vendidos do `similar-houses` no produto de oportunidades — vale
  plano próprio, ver seção 6.
