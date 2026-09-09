# Correção monetária: ler um ITBI de 2008 em dinheiro de hoje

**Data:** 2026-09-09
**Estado:** desenhada, não implementada.

## O problema, em uma frase

A base vai de 2008 a 2026 e todo valor aparece na tela em reais do dia da
quitação — R$ 300.000 de 2008 e R$ 300.000 de 2025 são impressos iguais, e não
são: o primeiro vale **2,7x** o segundo.

## O que foi medido

Série 433 do SGS/BCB (IPCA, variação % mensal), baixada em 2026-09-09. Último
mês publicado: **07/2026** (o IPCA sai por volta do dia 10 do mês seguinte, então
o mês corrente quase sempre falta). Base: 507.706 quitações de BH, de
2008-01-02 a 2026-06-30.

Fator de correção até jul/2026, e o que ele faz com uma quitação de R$ 300.000:

| quitação | fator | R$ 300.000 viram |
| --- | ---: | ---: |
| jun/2008 | 2,705 | R$ 811.446 |
| jun/2012 | 2,199 | R$ 659.633 |
| jun/2016 | 1,632 | R$ 489.664 |
| jun/2019 | 1,469 | R$ 440.581 |
| jun/2021 | 1,327 | R$ 398.150 |
| jun/2023 | 1,150 | R$ 344.945 |
| jun/2025 | 1,047 | R$ 314.144 |

Quanto da base o nominal distorce, por tamanho da correção:

| correção | linhas | % da base |
| --- | ---: | ---: |
| < 10% | 55.200 | 10,9% |
| 10–25% | 65.485 | 12,9% |
| 25–50% | 80.234 | 15,8% |
| **> 50%** | **306.787** | **60,4%** |
| sem índice | 0 | 0,0% |

Seis em cada dez linhas da base estão subestimadas em mais de 50% quando lidas
nominalmente. Não é um detalhe de apresentação — é a maior parte do acervo.

## O que este documento **não** promete

IPCA responde *"quanto aquele dinheiro valeria hoje"*, não *"quanto o imóvel
vale hoje"*. Imóvel em BH não anda colado na inflação, e o próprio README já
mede que anúncio pede 1,74x a mediana do R$/m² declarado. O rótulo na tela é
sempre **"corrigido pelo IPCA"**, nunca "valor de mercado". Um índice
imobiliário de verdade — a variação da mediana R$/m² do próprio bairro — foi
considerado e ficou de fora: é ruidoso onde a amostra é fina e vira circular na
tela de oportunidade, que compara anúncio contra essa mesma mediana.

## Recorte: exibição, não cálculo

O valor nominal continua sendo a única verdade gravada e a única entrada de
`referência`, `fator de calibração` e `nota de oportunidade`. O corrigido é
**saída**, calculado na serialização.

Isso é deliberado: o fator de calibração foi medido contra medianas nominais
(`scripts/validar_referencia.py`), e trocar a entrada por baixo invalidaria a
medição sem que nada na suíte reclamasse. Em `/rua` e `/bairro` a mediana
corrigida entra como campo **adicional** ao lado da nominal, não no lugar dela.

`/leilao` e `/oportunidades` ficam de fora nesta rodada: lá o número entra em
decisão de compra e conversa direto com o fator de calibração.

## Arquitetura

Quatro camadas, cada uma testável sozinha.

```
BCB/SGS 433  ->  monetary_index (tabela)  ->  Deflator (domínio)  ->  schemas/telas
   ingestão          sincronização             fator(mês)            valor corrigido
```

### 1. Ingestão — `app/ingestion/bcb_sgs.py`

`fetch_series(codigo: int, desde: date) -> list[IndexPoint]`, onde
`IndexPoint(competencia: date, variacao_pct: float)`.

- Endpoint: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial=dd/mm/aaaa`
- Resposta: `[{"data":"01/01/2024","valor":"0.42"}, ...]` — dia sempre `01`,
  valor é **variação percentual do mês**, com ponto decimal e sinal (agosto de
  2024 veio `-0.02`).
- Passa pelo `app.core.http_client` (retry, backoff e pace já resolvidos lá).
- Guarda a **variação crua**, não o acumulado: o acumulado é derivado e depende
  da referência escolhida, então guardá-lo congelaria uma decisão de leitura
  dentro do dado. A série de origem fica auditável linha a linha.

### 2. Persistência — `app/models/monetary_index.py`

```
monetary_index
  id            int, pk
  series        str(20)    -- "ipca"; a coluna existe para o dia que entrar IGP-M
  competencia   date       -- sempre dia 1
  variacao_pct  Numeric(8,4)
  unique (series, competencia)
```

Migration `0023`. Sincronização em `app/services/monetary_index_sync.py`:
upsert por `(series, competencia)`, porque o BCB **revisa** meses já publicados
e reingerir tem que atualizar, não duplicar nem ignorar. São ~223 linhas para
2008–2026 e uma linha nova por mês.

Entrada pelo `app/ingestion/cli.py` (comando `ipca`), alvo `make ipca`, e um
passo no `scheduler.sh` — diário é mais que suficiente para dado mensal, e
alinha com o ciclo que já existe.

### 3. Domínio — `app/domain/monetary_correction.py`

```python
@dataclass(frozen=True)
class Deflator:
    referencia: date                  # último mês publicado
    def fator(self, competencia: date) -> float | None
    def corrigir(self, valor, competencia) -> float | None
```

- Construído de uma sequência de `(competencia, variacao_pct)`; o acumulado sai
  em memória (223 floats).
- **Convenção da Calculadora do Cidadão:** corrigir de `M` até `R` aplica a
  variação dos meses em `(M, R]` — a variação do próprio mês da quitação **não**
  entra. Sem fixar isso, dois lugares do código dariam números diferentes para o
  mesmo ITBI.
- **Mês sem índice devolve `None`, nunca 1,0.** Mesma regra que o fator de
  calibração já segue: sem medida, não inventa. Vale para quitação anterior ao
  início da série e para quitação em mês ainda não publicado.
- `fator(referencia) == 1.0` — o mês de referência é o próprio presente.

Carga: dependência FastAPI que lê a tabela uma vez e cacheia em memória com TTL
(dado que muda uma vez por mês; o `Deflator` é imutável e pode ser compartilhado
entre requests). Nenhum request toca o BCB.

### 4. Exposição

| tela | campo novo |
| --- | --- |
| `/busca` (`TransactionOut`) | `declared_value_corrected`, `price_per_m2_corrected` |
| `/imovel` (`PropertyOut`) | valor corrigido por ponto da linha do tempo; valorização **real** ao lado da nominal |
| `/rua`, `/bairro` (`market_stats`) | `median_price_per_m2_corrected`, ao lado da nominal |

Todas carregam a referência para a tela imprimir "valores corrigidos pelo IPCA
até jul/2026". Campo nulo (mês sem índice) imprime só o nominal — sem asterisco
mudo.

Para a mediana corrigida, cada venda é corrigida **antes** da mediana: corrigir
a mediana nominal pelo fator do mês central daria outro número, e o errado —
a janela mistura meses com fatores diferentes. `market_stats` recebe o deflator
como parâmetro opcional; sem ele, os campos corrigidos saem nulos e o
comportamento atual não muda em nada.

## Testes

| unidade | o que prova |
| --- | --- |
| `bcb_sgs` | parseia `"0.42"`, `"-0.02"` e data `01/01/2024`; erro de rede sobe, não vira série vazia |
| `monetary_index_sync` | reingerir o mesmo mês atualiza a variação revisada e não duplica |
| `Deflator` | fator conhecido de jun/2019 → jul/2026 = 1,469 (±0,001); mês fora da série → `None`; mês de referência → 1,0; convenção do mês inicial excluído |
| API | `/transactions` traz o corrigido; sem índice, traz nulo e o nominal intacto |
| `market_stats` | mediana corrigida usa venda a venda; sem deflator, saída idêntica à de hoje |

O teste do fator usa valor fixo em fixture, não a rede.

## Riscos

- **BCB fora do ar na sincronização.** A tabela é a fonte para leitura; falha na
  coleta deixa a referência velha, e a tela passa a dizer "até jun/2026". Degrada
  em silêncio para um mês atrás, não para número errado.
- **Revisão de índice muda um valor já exibido.** É o comportamento correto do
  IPCA; o upsert garante que a base acompanha.
- **Alguém confundir corrigido com preço de mercado.** Mitigado no rótulo, e é
  a razão de `/leilao` e `/oportunidades` ficarem de fora.
