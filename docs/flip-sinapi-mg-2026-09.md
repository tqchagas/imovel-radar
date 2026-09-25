# SINAPI MG e SUDECAP BH para calibrar o `/flip`

Consulta em 25/09/2026. Este registro separa a disponibilidade das bases de preços de uma cotação comparável ao escopo de reforma de um apartamento. **Foram conferidos exemplos na planilha SUDECAP de julho/2026; nenhum preço unitário do SINAPI MG foi extraído.** Os preços SUDECAP abaixo não devem ser atribuídos ao SINAPI, embora algumas descrições indiquem a composição SINAPI usada como referência.

## O que foi verificado nas fontes oficiais

- A [CAIXA apresenta o SINAPI](https://www.caixa.gov.br/poder-publico/modernizacao-gestao/sinapi/Paginas/default.aspx) como sistema mantido com o IBGE e publica, a partir de 2025, relatórios mensais em ZIP: planilhas XLSX com insumos e composições de todas as UFs e PDFs com relatórios analíticos, custos de composições e preços de insumos. Para um estudo em BH, filtrar **MG**, identificar competência, código, unidade, descrição integral e regime de encargos antes de usar qualquer número.
- A [nota oficial da CAIXA](https://www.caixa.gov.br/Downloads/sinapi-historico-de-encargos-e-notas/Notas_SINAPI.pdf), Nota 12/2025 nº 02, informa que o IBGE enviou em 22/12/2025 os dados de outubro e novembro de 2025 e que a CAIXA **retificou** os relatórios daqueles meses que haviam sido inicialmente publicados com valores zerados. Logo, a Nota 12/2025 nº 01 sobre zeramento histórico não descreve, por si só, a situação das versões retificadas ou de 2026. A nota também menciona correções e republicações posteriores de referências de janeiro/fevereiro de 2026. Cada competência deve ser aberta na versão mais recente e conferida quanto a valores não zerados.
- O [livro de Metodologias e Conceitos do SINAPI](https://www.caixa.gov.br/Downloads/sinapi-metodologia/Livro_SINAPI_Metodologias_Conceitos.pdf) explica que uma composição pode existir sem custo calculado quando contém insumo sem pesquisa de preço. Isso requer cotar o insumo conforme a especificação técnica, e não tratar zero/ausência como serviço gratuito.
- A [SUDECAP/PBH](https://prefeitura.pbh.gov.br/sudecap/tabela-de-precos) publicou em **08/09/2026** sua tabela de competência **julho/2026**, com tabelas de insumos e serviços de construção oneradas e desoneradas. A PBH diz que confronta suas composições com o SINAPI e as adapta ao método construtivo local, às convenções coletivas e a pesquisas no mercado mineiro. A PBH qualifica a tabela como **referência orientativa de preço máximo**, não como cotação vinculante para reforma residencial privada. [Planilha de construção onerada, julho/2026](https://prefeitura.pbh.gov.br/sites/default/files/estrutura-de-governo/sudecap/2026/2026.07-tabela-de-construcao-onerada.xls).

## Exemplos conferidos na tabela SUDECAP de julho/2026

A planilha identifica o regime **onerado, sem BDI**. Valores são preços da linha e unidade indicada; não compõem sozinhos o custo final de um ambiente. O relatório analítico/caderno de encargos deve ser consultado antes de determinar inclusões como materiais, preparo, perdas e transporte.

| Código SUDECAP | Serviço na planilha | Valor |
| --- | --- | ---: |
| 17.04.22 | Pintura acrílica fosca em parede interna, duas demãos, ref. SINAPI 88489 | R$ 16,58/m² pintado |
| 17.04.21 | Pintura acrílica fosca em teto interno, duas demãos, ref. SINAPI 88488 | R$ 18,68/m² pintado |
| 17.04.04 | Emassamento PVA e lixamento em parede interna, duas demãos, ref. SINAPI 88497 | R$ 18,19/m² preparado |
| 02.10.03 | Demolição de piso cerâmico ou ladrilho hidráulico | R$ 16,83/m² demolido |
| 15.17.23 | Assentamento de piso cerâmico em ambiente menor que 5 m², ref. SINAPI 87246 | R$ 57,00/m² assentado |
| 09.08.03 | Impermeabilização com argamassa polimérica, três demãos, ref. SINAPI 98555 | R$ 27,61/m² impermeabilizado |
| 11.15.31 | Quadro de distribuição com barramento 100 A e 16 posições | R$ 547,31/unidade |
| 11.24.05 | Cabo flexível de 2,5 mm², 750 V, não halogenado | R$ 3,94/m |
| 07.08.10 e 07.08.20 | Rasgo e recomposição de alvenaria para eletroduto até 40 mm | R$ 5,97/m + R$ 15,43/m |
| 10.03.02 | Tubo PVC soldável de água, 25 mm, com conexões | R$ 8,68/m |
| 10.22.02 | Registro de gaveta bruto, 3/4 pol. | R$ 79,75/unidade |
| 02.29.01 | Transporte de material em caçamba de 5 m³ | R$ 420,00/viagem |

Exemplo de interpretação: pintar 200 m² de paredes internas com duas demãos a R$ 16,58/m² custaria R$ 3.316 nessa linha. Se os mesmos 200 m² exigirem emassamento integral de duas demãos, acrescentam R$ 3.638; o total parcial passa a R$ 6.954, **antes** de teto, selador, reparos, BDI ou contingência. O exemplo é uma conta de quantidades hipotéticas, não orçamento do imóvel.

## Como transformar as bases em premissas mais fiéis

Para cada linha do `/flip`, montar uma cesta de **composições de serviço** e quantidades, com um memorial mínimo de escopo. A unidade física deve corresponder ao serviço: pintura por m² de parede/teto pintável e preparação especificada; elétrica por pontos, metros de eletrodutos/fios, quadro, circuitos e testes; hidráulica por pontos, metros de tubulação, registros, abertura e recomposição; pisos e revestimentos por m² executado com demolição, regularização e acabamento separados. Conferir se a composição inclui materiais, mão de obra e transporte; não somar pacote completo a seus componentes. Registrar código, fonte, UF/localidade, competência, regime, unidade e inclusões/exclusões.

Para **marcenaria planejada**, o SINAPI pode ajudar com algum serviço de instalação ou insumo, mas a estimativa útil exige medidas e especificações de chapa, acabamento, ferragens, puxadores e instalação. Cotar pelo menos três marcenarias de BH com o mesmo desenho. Aplicar a mesma disciplina a bancadas, box, louças e taco, cujo preço varia muito com material e estado existente. As três propostas locais por escopo padronizado servem para calibrar a diferença entre tabela pública e contratação privada de pequena obra, além de criar faixas por padrão do imóvel.

Recomendação prática: usar a tabela **SUDECAP onerada julho/2026** como referência local inicial e cruzar cada serviço equivalente com **SINAPI MG da competência mais recente disponível**, conferindo o relatório analítico e notas de retificação. No produto, manter uma estimativa-base, faixa de incerteza e contingência por condição do imóvel, com data e origem da premissa. Tabelas de obras públicas são referências técnicas de custo; não substituem propostas executáveis de empreiteiros para apartamento ocupado, acesso ao condomínio, mobilização pequena e descarte.

## Limite desta pesquisa

Não foi possível abrir diretamente os arquivos da CAIXA na consulta: o servidor respondeu com redirecionamentos repetidos. A página oficial e trechos indexados da nota e do livro foram verificados; os ZIPs mensais, códigos e valores unitários de MG **não foram extraídos**. A planilha SUDECAP foi baixada e os exemplos acima foram conferidos, mas faltam quantidades reais e o detalhamento de cada composição para comparar o custo total de um cômodo com as premissas atuais do `/flip`.

## Aplicação inicial no `/flip`

O simulador agora oferece os escopos **retoques**, **revenda** e **retrofit**, com medições opcionais de pintura, preparação, impermeabilização, pisos, cabos, tubos e rasgos. O orçamento separa demolição, infraestrutura/recomposição, acabamentos, marcenaria e logística, e identifica a fonte de cada linha. Estudos salvos antes desta revisão permanecem no motor **legado** até o usuário trocar explicitamente o escopo; os valores das premissas de cada estudo continuam congelados no snapshot.

As linhas SUDECAP incluídas são somente as verificadas acima. Quando uma medição está ausente, o sistema usa uma **provisão inicial** para aquele pacote, não uma composição deduzida por m². Para elétrica, preencher a metragem de cabo troca a provisão global por quadro, cabo, rasgo/recomposição medidos e provisão complementar; para hidráulica, preencher tubo faz o mesmo. Não se somam o pacote global e seus componentes. Os preços complementares de elétrica, hidráulica, marcenaria, bancada, box, tacos, portas e limpeza ainda **não são cotações verificadas** e precisam de propostas locais.

Se apenas paredes ou teto forem medidos, a outra superfície mantém provisão própria, repartida em 75%/25% do antigo pacote de R$ 60 por m² de área seca. Essa repartição é hipótese operacional, não composição SUDECAP. Para pisos de banheiros e cozinhas, a área medida precisa vir com o número de ambientes cobertos; os demais mantêm a provisão por unidade. O estudo salvo congela também rótulo, unidade e fonte de cada premissa nova; snapshots antigos sem metadados exibem “Fonte histórica não registrada”.

O item de assentamento de piso pode incluir parte dos materiais: não somamos automaticamente uma provisão de revestimento para evitar dupla contagem. Antes de fechar uma proposta de compra, verificar a composição analítica do item 15.17.23/87246, padrão/fornecimento do revestimento e regularização do contrapiso. Similarmente, 2,5 mm² não cobre todos os circuitos (por exemplo, chuveiro), nem tubo de água fria 25 mm cobre esgoto. A contingência de 15% não substitui BDI, frete, mobilização, dificuldade de acesso nem uma vistoria técnica. O próximo salto de precisão é registrar 2–3 cotações reais de BH por escopo padronizado e calibrar as provisões separadamente dos preços oficiais.
