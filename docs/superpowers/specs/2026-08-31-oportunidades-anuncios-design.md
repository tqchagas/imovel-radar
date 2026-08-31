# Oportunidades de anúncios imobiliários

**Status:** aprovado pelo usuário em 2026-08-31

## Objetivo

Cruzar anúncios ativos de venda do QuintoAndar e VivaReal com o histórico recente de transações ITBI do ImovelRadar para identificar anúncios abaixo do preço de mercado e destacar oportunidades com desconto relevante.

O escopo inicial é Belo Horizonte, a única cidade com dados ITBI carregados. ITBI continua sendo a referência principal de preço real. Negociações fechadas do QuintoAndar não serão misturadas à linha do tempo de escrituras nem usadas como substituto automático dos dados ITBI.

## Abordagem

Usar um cruzamento híbrido:

1. correspondência exata por rua e número quando houver dados confiáveis;
2. fallback por bairro, tipo de imóvel e faixa de área quando a amostra exata for insuficiente;
3. exibição da origem, método, tamanho da amostra e data da referência em toda oportunidade.

Os coletores existentes do `auction-monitor` serão adaptados para um módulo próprio do ImovelRadar. Não haverá dependência de runtime entre os projetos.

## Fluxo

```text
coleta de anúncios
  -> normalização e upsert de comparáveis
  -> desativação segura de anúncios ausentes
  -> cálculo de referência ITBI
  -> classificação e ranking
  -> API e tela
  -> e-mail deduplicado
```

Cada coleta será explícita por cidade/bairro e paginada por fonte. QuintoAndar e VivaReal são fontes de anúncios, não de transações ITBI.

## Modelo de dados

Expandir `market_comparables` para armazenar, além dos dados atuais:

- URL, fonte e identificador da listagem;
- cidade, bairro, rua e número normalizados;
- latitude, longitude e origem da coordenada;
- tipo, quartos, banheiros, área e preço;
- status ativo;
- `first_seen_at` e `last_seen_at`.

A identidade de anúncio será `(source, listing_id)`. O upsert atualiza o snapshot sem alterar `first_seen_at`. Cada execução registra o escopo exato da coleta (fonte, UF, cidade, bairros e filtros). Anúncios só serão desativados dentro desse mesmo escopo quando a coleta terminar com sucesso; uma coleta de um bairro nunca inativa anúncios de outro bairro.

Na primeira versão haverá uma configuração global de alertas, com cidade/bairros, desconto mínimo, confiança mínima, destinatários e periodicidade. Lista de bairros vazia significa todos os bairros suportados pela coleta configurada. A periodicidade usa o fuso `America/Sao_Paulo`; configuração ausente ou inválida impede o job e gera erro operacional, sem coleta destrutiva. O desenho pode evoluir para configurações por usuário depois, mas isso não faz parte deste escopo. Criar também registro de notificações enviadas por anúncio e regra para deduplicação.

## Cálculo

Configuração padrão:

- janela ITBI: últimos 24 meses em relação à maior `settlement_date` disponível para a cidade;
- desconto mínimo: 15%;
- confiança mínima para e-mail: média;
- cidade inicial: Belo Horizonte.

Para cada anúncio:

```text
desconto_pct = (preco_estimado - preco_anunciado) / preco_estimado
```

Usar mediana, nunca média, para reduzir o efeito de outliers. A referência será calculada em preço por m²: para cada ITBI válido, `valor_m2 = declared_value / built_area_acquired`; `preco_estimado = mediana(valor_m2) * area_do_anuncio`. Assim, áreas diferentes continuam comparáveis. O resultado não será calculado em preço total mediano.

### Ordem de seleção da referência

1. Tentar endereço exato, usando ITBIs residenciais do mesmo tipo, na janela de 24 meses e com área na faixa de +/-30% da área do anúncio. Se houver pelo menos 5 transações, selecionar essa referência.
2. Se a primeira opção não atingir 5 transações, usar bairro + tipo + faixa de área de +/-30%. Se houver pelo menos 15 transações, selecionar essa referência.
3. Se ainda não houver amostra suficiente, usar o fallback mais amplo do bairro ou tipo somente para exibição, classificado como baixa confiança, com `tipo_referencia = bairro_amplo`, e inelegível para e-mail.

### Confiança alta

Pelo menos 5 ITBIs do mesmo endereço nos últimos 24 meses, compatíveis com tipo residencial e faixa de área.

### Confiança média

Sem amostra suficiente no endereço, pelo menos 15 ITBIs do mesmo bairro e tipo, dentro de aproximadamente +/-30% da área do anúncio.

### Confiança baixa

Fallback mais amplo por bairro ou tipo. Pode aparecer na tela, mas não dispara e-mail por padrão.

Excluir ITBIs sem valor ou área válida, separar residencial de comercial e evitar vagas, frações e áreas claramente divergentes.

Cada resultado terá:

- preço anunciado;
- preço estimado;
- desconto percentual e em reais;
- tipo de referência (`endereco_exato`, `bairro_area` ou `bairro_amplo`);
- quantidade de transações;
- data da referência;
- nível de confiança;
- motivos legíveis do cálculo.

## Interface

Adicionar uma tela de oportunidades com:

- filtros por cidade, bairro, fonte, tipo, confiança e desconto;
- resumo da quantidade de oportunidades, maior desconto e horário da última coleta;
- ranking por desconto percentual, com preço anunciado, estimado, confiança e amostra;
- detalhe com transações usadas, período da referência, link original e limitações;
- ações para marcar como vista, silenciar anúncio e abrir no portal.

A oportunidade deve ser visualmente separada do histórico ITBI/escritura. Não publicar anúncios ou resultados desse cálculo em páginas SEO públicas.

## E-mail e operação

Um job periódico coleta, calcula e envia alertas. Cada execução válida calcula uma impressão digital dos valores do anúncio e da referência. Enviar na primeira elegibilidade e reenviar somente se, comparado ao último envio bem-sucedido do mesmo anúncio e regra, o preço anunciado variar pelo menos 3% (`abs(novo-antigo)/antigo`), o desconto variar pelo menos 5 pontos percentuais ou o preço estimado variar pelo menos 5% (`abs(novo-antigo)/antigo`). Nunca enviar mais de uma vez para o mesmo anúncio dentro de 24 horas. O registro guarda estado `pending`, `sent` ou `failed`; somente `sent` serve como linha de base, e o job usa uma chave única por anúncio, regra e fingerprint para evitar concorrência. Um e-mail pode ter múltiplos destinatários, registrados em um único evento de envio.

Falha no QuintoAndar não bloqueia VivaReal, e vice-versa. A paginação termina na primeira página vazia, no total informado pela fonte ou no limite configurado de páginas, com limite padrão de 100; IDs repetidos são ignorados. Uma coleta paginada só será considerada bem-sucedida quando todas as páginas até esse fim retornarem HTTP 2xx, payload válido e puderem ser normalizadas sem erro fatal. HTTP não-2xx, JSON inválido ou payload estruturalmente inválido são erros fatais. Se qualquer página falhar, o resultado é parcial, a fonte fica degradada e anúncios dessa fonte não serão desativados. Resultado vazio só desativa anúncios quando a paginação terminou com sucesso. Resultados sem amostra mínima não serão enviados por e-mail.

Anúncio ausente em uma coleta bem-sucedida dentro do escopo correspondente fica inativo e desaparece da tela padrão e do ranking. Seu histórico e notificações permanecem armazenados, mas ele não gera novos e-mails. Se voltar em coleta posterior, torna-se ativo novamente sem apagar `first_seen_at` e gera um novo alerta se continuar elegível, pois o retorno após inatividade é um novo evento de oportunidade.

## Testes e critérios de aceitação

- normalização consistente de fontes, endereços e números;
- adaptação de payloads fixos do QuintoAndar e VivaReal;
- mediana, desconto, janela de 24 meses, faixa de área e confiança;
- upsert idempotente e desativação apenas após coleta bem-sucedida;
- isolamento de falha entre fontes;
- deduplicação e reenvio correto de notificações;
- API com filtros e ordenação;
- renderização responsiva da tela e detalhe;
- fluxo integrado com banco de teste.

Uma oportunidade só deve ser classificada como alerta quando tiver desconto de pelo menos 15%, referência dentro da janela e confiança média ou alta. A tela pode listar baixa confiança com aviso explícito.

## Fora do escopo

- ingestão produtiva de `/condo/negotiations` do QuintoAndar baseada apenas em ITBI;
- mistura de negociações fechadas com escrituras;
- publicação em páginas SEO;
- geocodificação em massa dos endereços ITBI;
- expansão para cidades sem base ITBI antes de definir uma referência equivalente.
