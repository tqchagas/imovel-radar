# Simulador de flip: viabilidade e pipeline de estudos

Data: 2026-09-11

## Problema

Não existe no ImovelRadar nenhuma ferramenta que responda "compro este
imóvel por quanto, reformo por quanto, vendo por quanto, e sobra
quanto". Hoje a decisão de flip é feita fora do sistema, em planilha, e
o teto de compra sai de cabeça. As duas telas desenhadas pedem um motor
de custo de obra paramétrico, um DRE, um teto máximo de compra (MAO) e
um pipeline dos estudos já feitos.

## Decisões tomadas

1. Estudos são **salvos no banco**, tabela nova.
2. O valor de saída (ARV) é **sempre digitado à mão**. A mediana do
   bairro aparece ao lado como referência passiva; não preenche campo.
3. As premissas de custo vivem num **JSON versionado no repositório**
   (JSON e não YAML porque o projeto não depende de PyYAML, e a
   biblioteca padrão já lê JSON).
   Mudar preço de insumo é commit, com histórico no git. Não há tela de
   edição de premissas.
4. Cada estudo salvo **congela um snapshot** das premissas usadas.
   Reajustar o preço do granito não muda o lucro de um estudo antigo.
5. O cálculo mora inteiro no backend, exposto por um endpoint de
   preview stateless. O front não faz conta nenhuma — só formata.
6. O visual é **adaptado ao design system atual** (styles.css, fonte
   Archivo), com o layout e a hierarquia do mockup. Sem Tailwind CDN,
   sem Geist, sem Material Symbols.

## Domínio

### `app/config/flip_premissas.json`

Os itens de custo, cada um com `chave`, `rotulo`, `unidade`
(`m2` | `un` | `pct` | `meses` | `mensal` | `fator`) e `valor`. Carregado uma vez e
validado na subida: chave faltando levanta erro nomeando a chave, não
`KeyError` cru no meio do cálculo.

Valores iniciais (fornecidos pelo dono):

| Item | Unidade | Valor |
|---|---|---|
| Taco de madeira (raspagem + calafetação + resina) | m² | 75,00 |
| Pintura de paredes e tetos secos (por m² de piso seco) | m² | 60,00 |
| Banheiro — troca de piso cerâmico/porcelanato | un | 450,00 |
| Banheiro — azulejo novo na área do box | un | 850,00 |
| Banheiro — massa acrílica fora do box + pintura | un | 550,00 |
| Banheiro — bancada de granito + cuba + torneira | un | 950,00 |
| Banheiro — vaso com caixa acoplada + assento + ducha | un | 700,00 |
| Banheiro — box blindex padrão + espelho | un | 1.000,00 |
| Banheiro — mão de obra hidráulica e instalação | un | 800,00 |
| Banheiro — marcenaria sob a pia (gabinete MDF) | un | 800,00 |
| Cozinha — troca de piso cerâmico/porcelanato | un | 1.200,00 |
| Cozinha — azulejo novo na área molhada/bancada até 2m | un | 750,00 |
| Cozinha — massa acrílica no restante das paredes + pintura | un | 850,00 |
| Cozinha — bancada de granito com cuba inox + torneira | un | 1.800,00 |
| Cozinha — mão de obra hidráulica e instalações | un | 1.100,00 |
| Cozinha — marcenaria sob a pia (balcão/gabinete MDF) | un | 3.000,00 |
| Elétrica e iluminação LED (fixo base) | un | 2.500,00 |
| Portas e ferragens (lixamento + esmalte + maçaneta) | un | 200,00 |
| Caçamba e limpeza pós-obra | un | 1.200,00 |
| Elétrica completa — novo QDC + fiação e circuitos | un | 5.000,00 |
| Hidráulica completa — banheiro (ramais e registros) | un | 2.500,00 |
| Hidráulica completa — cozinha (ramais e registros) | un | 2.000,00 |
| Contingência para imprevistos | pct | 0,15 |
| Proporção de área seca com taco | pct | 0,70 |
| ITBI BH | pct | 0,03 |
| Escritura e registro | pct | 0,015 |
| Corretagem de venda | pct | 0,05 |
| IR sobre ganho de capital | pct | 0,15 |
| Meses de carrego padrão | meses | 7 |
| Condomínio mensal estimado | mensal | 550 |
| IPTU mensal estimado | mensal | 120 |
| Contas de consumo mínimas (luz/água) | mensal | 80 |
| Fator de saída padrão vs mediana do bairro | fator | 0,85 |
| ROI líquido alvo para cálculo de MAO | pct | 0,18 |

O fator de saída padrão fica no JSON como referência exibida na tela,
já que o ARV é digitado; não entra na conta automaticamente.

### `app/domain/flip.py`

Módulo puro, sem sessão de banco e sem I/O.

**Entradas**: `area_seca_m2`, `banheiros`, `cozinhas` (padrão 1),
`portas`, `preco_compra`, `arv_total`, `meses_carrego`, e os toggles
`eletrica_completa`, `hidraulica_completa_banheiro`,
`hidraulica_completa_cozinha`.

`area_seca_m2` é campo próprio, digitado, com padrão igual à área útil.
Banheiro e cozinha são orçados por unidade, então não há como derivar a
área seca da área útil sem inventar uma premissa fora da tabela.

**Orçamento por grupo**:

- Áreas secas: taco = `area_seca × 0,70 × 75`; pintura = `area_seca × 60`
- Banheiros: R$ 6.100 por unidade (450 + 850 + 550 + 950 + 700 + 1.000
  + 800 + 800), multiplicado pelo número de banheiros
- Cozinha: R$ 8.700 por unidade (1.200 + 750 + 850 + 1.800 + 1.100 +
  3.000)
- Geral: elétrica/LED 2.500 + portas `200 × n` + caçamba 1.200
- Retrofit: elétrica completa +5.000; hidráulica de banheiro
  `2.500 × banheiros`; hidráulica de cozinha `2.000 × cozinhas`
- Contingência: 15% sobre a soma dos grupos acima, sem incidir sobre si
  mesma

**DRE**:

- Aquisição = compra + ITBI 3% + escritura/registro 1,5%
- Obra = total do orçamento, contingência inclusa
- Carrego = (550 + 120 + 80) × meses
- Corretagem = 5% sobre o preço de venda
- Ganho de capital = `venda − corretagem − (compra + ITBI + registro +
  obra)`; a benfeitoria comprovada entra no custo. IR = 15% sobre o
  ganho, zerado quando o ganho é negativo ou nulo
- Lucro líquido = venda − corretagem − IR − compra − ITBI − registro −
  obra − carrego

**Indicadores**:

- Capital empatado = compra + ITBI + registro + obra + carrego
- ROI = lucro ÷ capital empatado
- TIR anualizada = `(1 + ROI) ^ (12 / meses) − 1`

**MAO**: bisseção sobre o preço de compra até o ROI líquido bater 18%.
O ROI cai monotonicamente conforme o preço sobe, então a bisseção
converge sempre. Não há fórmula fechada porque o `max(ganho, 0)` do IR
quebra a linearidade.

**Matriz de sensibilidade 3×3**: o DRE inteiro recalculado em nove
cenários — venda a −5%, base e +5%, cruzada com 5, 7 e 10 meses de
carrego.

## Persistência

### `app/models/flip_study.py` → tabela `flip_studies`

Migration `0024_flip_studies.py`.

- Identidade: `apelido`, `endereco`, `bairro`, `cidade`
- Imóvel: `area_util_m2`, `area_seca_m2`, `quartos`, `banheiros`,
  `cozinhas`, `portas`
- Negócio: `preco_compra`, `arv_total`, `meses_carrego`, os três
  toggles de retrofit
- Pipeline: `status` — `oportunidade` | `em_analise` | `descartado`,
  com `CheckConstraint`, como nos demais modelos do projeto
- Origem: `origem` — `manual` | `oportunidade` | `leilao` — mais
  `origem_id` nullable. Sem chave estrangeira: o anúncio pode sair do
  radar e o estudo não deve sair junto
- `premissas_json`: snapshot congelado dos valores usados
- `created_at`, `updated_at`

**Sem colunas derivadas.** Lucro, ROI, TIR e MAO não vão para o banco:
o snapshot mais as entradas reproduzem o número exato, e coluna
derivada envelhece torta assim que a fórmula muda. A listagem do
pipeline recalcula na hora — é aritmética pura sobre poucas dezenas de
estudos.

### API — `app/api/routes/flips.py`

| Rota | Comportamento |
|---|---|
| `POST /flips/preview` | Stateless: entradas viram orçamento por grupo, DRE, MAO e matriz 3×3. É o que o slider chama |
| `GET /flips/premissas` | Devolve a tabela do JSON, para a tela mostrar rótulo e custo unitário de cada linha |
| `GET /flips` | Lista com filtros de bairro, status e faixa de preço; cada item já traz ROI e lucro recalculados |
| `POST /flips` | Grava, congelando as premissas vigentes no snapshot |
| `GET /flips/{id}` | Um estudo |
| `PATCH /flips/{id}` | Edita mantendo o snapshot antigo, salvo quando vier `atualizar_premissas: true` |
| `DELETE /flips/{id}` | Remove |

Schemas em `app/schemas/flips.py`. Serviço fino em
`app/services/flip_studies.py` cuidando de banco e snapshot; a conta
fica toda em `app/domain/flip.py`.

Sem autenticação, como `/leilao` e `/enviar` — anotação particular do
dono, protegida por não estar em lugar nenhum.

## Páginas

Registradas no dicionário `PAGES` de `app/main.py`, como as demais.

- `/flip` — simulador. Aceita `?id=N` para abrir um estudo salvo, e
  `?origem=oportunidade&origem_id=N` ou `?origem=leilao&origem_id=N`
  para pré-preencher
- `/flip/estudos` — pipeline

As duas com `noindex, nofollow`, fora do `sitemap.py` e fora do nav de
`common.js`, seguindo a regra de `/leilao` e `/enviar`. O link entre
elas fica no cabeçalho de cada página.

**Arquivos**: `app/static/flip.html` + `flip.js`,
`app/static/flip-estudos.html` + `flip-estudos.js`. Reusam `common.js`
(`fetchJson`, `formatCurrency`, `formatPct`, `deltaTag`) e
`styles.css`. CSS novo apenas para o que não existe: grid de duas
colunas, faixa de KPI, banner do MAO e heatmap da matriz, usando os
tokens de cor já definidos — sálvia para ROI bom, terracota para risco.

**`/flip`**: qualquer mudança de campo dispara `POST /flips/preview`
com debounce de 200ms, e a resposta repinta o lado direito inteiro —
KPIs, MAO, caderno de encargos item a item, DRE e matriz. Ao lado do
campo de ARV, a mediana de R$/m² do bairro vinda de
`GET /stats/neighborhoods/{bairro}` aparece como referência passiva.

**Ponte**: botão "simular flip" em `oportunidades.js` e `leilao.js`
navega para `/flip?origem=...&origem_id=...`; o `flip.js` busca o
registro na API de origem e mapeia preço, área, bairro e endereço. O
que não existe na origem — banheiros, portas, área seca — entra com o
padrão, para o dono ajustar.

**`/flip/estudos`**: filtros de bairro, status e faixa de preço; tabela
com preço, obra, capital, lucro, ROI, TIR, MAO e status; faixa de KPIs
agregados no topo — estudos ativos, capital comprometido, lucro médio e
TIR média. A linha leva para `/flip?id=N`. Excluir pede confirmação.

**Fora de escopo**, apesar de estar no mockup: aba de premissas
editável, exportar PDF, exportar CSV e o badge de IGP-M do topo.

## Erros

O preview que falha mostra o motivo no lugar dos KPIs e mantém os
últimos valores visíveis, em vez de zerar a tela. Área ou preço zerado
desabilita o cálculo com aviso, sem disparar request.

## Testes

**`tests/test_domain/test_flip.py`** — o grosso da cobertura, domínio
puro:

- Orçamento por grupo com números fechados à mão: 92 m² secos, 2
  banheiros, 1 cozinha, 6 portas; cada grupo confere linha a linha
- Toggles de retrofit somam exatamente 5.000, 2.500 × banheiros e
  2.000 × cozinhas, e nada mais
- Contingência incide sobre o subtotal, não sobre si mesma
- IR zera quando o ganho é negativo
- MAO: comprar exatamente no MAO devolve ROI de 18%, e o ROI cai quando
  o preço sobe
- Matriz 3×3: a célula central é idêntica ao cenário base
- Premissa faltando no JSON levanta erro nomeando a chave

**`tests/test_api/test_flips.py`**: `preview` não grava nada; `POST`
congela o snapshot; editar depois de mudar o JSON mantém o número
antigo até vir `atualizar_premissas: true`; filtros do pipeline; 404 em
id inexistente.

**`tests/test_api/test_pages.py`**: `/flip` e `/flip/estudos` servem
200 e carregam `noindex`.

**`tests/test_models/`**: o `CheckConstraint` de status rejeita valor
inventado.
