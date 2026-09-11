/* Simulador de flip: o cálculo é todo do servidor.
 *
 * A tela manda as entradas e pinta o que volta. Repetir a conta aqui daria uma
 * segunda implementação de MAO e DRE para divergir da primeira no primeiro
 * reajuste de premissa.
 */
const {
  API_BASE, $, el, fetchJson, formatCurrency, formatPct, mountChrome, resolveCity,
} = window.IR;

const CAMPOS_NUMERICOS = [
  'area_util_m2', 'area_seca_m2', 'quartos', 'banheiros', 'cozinhas', 'portas',
  'preco_compra', 'arv_total', 'meses_carrego',
];
const CAMPOS_BOOLEANOS = [
  'eletrica_completa', 'hidraulica_completa_banheiro', 'hidraulica_completa_cozinha',
];

const state = { id: null, cidade: '', origem: null, origemId: null, aviso: '', timer: null };

async function enviar(path, method, body) {
  const resposta = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resposta.ok) {
    const erro = await resposta.json().catch(() => ({}));
    throw new Error(typeof erro.detail === 'string' ? erro.detail : `Erro ${resposta.status}`);
  }
  return resposta.status === 204 ? null : resposta.json();
}

function lerFormulario() {
  const dados = { endereco: $('f-endereco').value.trim() };
  const apelido = $('f-apelido').value.trim();
  const bairro = $('f-bairro').value.trim();
  if (apelido) dados.apelido = apelido;
  if (bairro) dados.bairro = bairro;
  CAMPOS_NUMERICOS.forEach((campo) => {
    dados[campo] = Number(document.querySelector(`[name="${campo}"]`).value);
  });
  CAMPOS_BOOLEANOS.forEach((campo) => {
    dados[campo] = document.querySelector(`[name="${campo}"]`).checked;
  });
  dados.status = $('f-status').value;
  return dados;
}

function entradaDe(dados) {
  // O preview só quer a parte que entra na conta; endereço e apelido não entram.
  const entrada = {};
  [...CAMPOS_NUMERICOS, ...CAMPOS_BOOLEANOS]
    .filter((campo) => campo !== 'area_util_m2' && campo !== 'quartos')
    .forEach((campo) => { entrada[campo] = dados[campo]; });
  return entrada;
}

function mostrarErro(mensagem) {
  const caixa = $('erro');
  caixa.textContent = mensagem;
  caixa.hidden = !mensagem;
}

function linha(rotulo, valor, { total = false, negativa = false } = {}) {
  const classes = `flip-linha${total ? ' flip-linha-total' : ''}${negativa ? ' flip-linha-negativa' : ''}`;
  const div = el('div', classes);
  div.appendChild(el('span', null, rotulo));
  div.appendChild(el('strong', 'flip-valor', valor));
  return div;
}

function pintarKpis(simulacao, areaUtil) {
  const { dre, orcamento } = simulacao;
  $('kpi-obra').textContent = formatCurrency(orcamento.total);
  $('kpi-obra-meta').textContent = areaUtil > 0
    ? `${formatCurrency(orcamento.total / areaUtil)} por m² de área útil`
    : '';
  $('kpi-capital').textContent = formatCurrency(dre.capital_empatado);
  $('kpi-lucro').textContent = formatCurrency(dre.lucro_liquido);
  $('kpi-lucro').classList.toggle('alta', dre.lucro_liquido >= 0);
  $('kpi-lucro-meta').textContent = `ROI de ${formatPct(dre.roi * 100)} sobre o capital`;
  $('kpi-tir').textContent = formatPct(dre.tir_anual * 100);
  $('kpi-tir-meta').textContent = `Margem de ${formatPct((dre.lucro_liquido / dre.venda) * 100)} sobre a venda`;
}

function pintarMao(simulacao, precoCompra) {
  $('mao-valor').textContent = formatCurrency(simulacao.mao);
  const folga = simulacao.mao - precoCompra;
  $('mao-comparativo').textContent = folga >= 0
    ? `Sua proposta de ${formatCurrency(precoCompra)} está ${formatCurrency(folga)} abaixo do teto.`
    : `Sua proposta de ${formatCurrency(precoCompra)} está ${formatCurrency(-folga)} acima do teto.`;
}

function pintarOrcamento(orcamento) {
  const alvo = $('orcamento');
  alvo.textContent = '';
  orcamento.grupos
    .filter((grupo) => grupo.itens.length)
    .forEach((grupo) => {
      const bloco = el('details', 'flip-grupo');
      const resumo = el('summary');
      resumo.appendChild(el('span', null, grupo.rotulo));
      resumo.appendChild(el('span', 'flip-valor', formatCurrency(grupo.total)));
      bloco.appendChild(resumo);
      grupo.itens.forEach((item) => {
        const linhaItem = el('div', 'flip-item');
        const quantidade = Number.isInteger(item.quantidade)
          ? item.quantidade
          : item.quantidade.toFixed(1);
        linhaItem.appendChild(el('span', null, `${item.rotulo} — ${quantidade} × ${formatCurrency(item.custo_unitario)}`));
        linhaItem.appendChild(el('span', 'flip-valor', formatCurrency(item.total)));
        bloco.appendChild(linhaItem);
      });
      alvo.appendChild(bloco);
    });
  alvo.appendChild(linha('Subtotal da obra', formatCurrency(orcamento.subtotal)));
  alvo.appendChild(linha('Contingência', formatCurrency(orcamento.contingencia)));
  alvo.appendChild(linha('Total da obra', formatCurrency(orcamento.total), { total: true }));
}

function pintarDre(dre) {
  const alvo = $('dre');
  alvo.textContent = '';
  alvo.appendChild(linha('(+) Venda estimada', formatCurrency(dre.venda)));
  alvo.appendChild(linha('(−) Corretagem', formatCurrency(dre.corretagem), { negativa: true }));
  alvo.appendChild(linha('(−) IR sobre ganho de capital', formatCurrency(dre.ir_ganho_capital), { negativa: true }));
  alvo.appendChild(linha('(−) Compra', formatCurrency(dre.preco_compra), { negativa: true }));
  alvo.appendChild(linha('(−) ITBI', formatCurrency(dre.itbi), { negativa: true }));
  alvo.appendChild(linha('(−) Escritura e registro', formatCurrency(dre.registro), { negativa: true }));
  alvo.appendChild(linha('(−) Obra', formatCurrency(dre.obra), { negativa: true }));
  alvo.appendChild(linha('(−) Carrego', formatCurrency(dre.carrego), { negativa: true }));
  alvo.appendChild(linha('(=) Lucro líquido', formatCurrency(dre.lucro_liquido), { total: true }));
}

function classeDaCelula(roi) {
  if (roi >= 0.18) return 'flip-celula-otima';
  if (roi >= 0.15) return 'flip-celula-aceitavel';
  return 'flip-celula-risco';
}

function pintarMatriz(matriz, mesesBase) {
  const alvo = $('matriz');
  alvo.textContent = '';
  const meses = [...new Set(matriz.map((c) => c.meses))].sort((a, b) => a - b);
  const variacoes = [...new Set(matriz.map((c) => c.variacao_venda))].sort((a, b) => b - a);

  const tabela = el('table', 'flip-matriz');
  const cabecalho = el('tr');
  cabecalho.appendChild(el('th', 'flip-matriz-rotulo', 'Venda \\ prazo'));
  meses.forEach((m) => cabecalho.appendChild(el('th', null, `${m}m`)));
  tabela.appendChild(cabecalho);

  variacoes.forEach((variacao) => {
    const tr = el('tr');
    tr.appendChild(el('th', 'flip-matriz-rotulo', variacao === 0 ? 'Base' : formatPct(variacao * 100)));
    meses.forEach((m) => {
      const celula = matriz.find((c) => c.variacao_venda === variacao && c.meses === m);
      const td = el('td', classeDaCelula(celula.roi));
      if (variacao === 0 && m === mesesBase) td.classList.add('flip-celula-base');
      td.appendChild(el('span', null, formatPct(celula.roi * 100)));
      td.appendChild(el('span', 'flip-celula-lucro', formatCurrency(celula.lucro_liquido)));
      tr.appendChild(td);
    });
    tabela.appendChild(tr);
  });
  // A tabela passa de treze colunas: rola dentro da própria caixa, para não
  // empurrar a página inteira para o lado.
  const rolagem = el('div', 'flip-matriz-rolagem');
  rolagem.appendChild(tabela);
  alvo.appendChild(rolagem);
  alvo.appendChild(el('p', 'card-meta', 'Verde: ROI ≥ 18%. Cinza: entre 15% e 18%. Coral: abaixo de 15%. Role para ver prazos mais longos.'));
}

function pintar(simulacao, dados) {
  pintarKpis(simulacao, dados.area_util_m2);
  pintarMao(simulacao, dados.preco_compra);
  pintarOrcamento(simulacao.orcamento);
  pintarDre(simulacao.dre);
  pintarMatriz(simulacao.matriz, dados.meses_carrego);
}

async function calcular() {
  const dados = lerFormulario();
  if (!(dados.area_seca_m2 > 0) || !(dados.preco_compra > 0) || !(dados.arv_total > 0)) {
    mostrarErro('Área seca, preço de compra e valor de venda precisam ser maiores que zero.');
    return;
  }
  try {
    const simulacao = await enviar('/flips/preview', 'POST', entradaDe(dados));
    // Um aviso de origem sobrevive ao repinte: ele fala do que a tela não
    // conseguiu trazer, e não do cálculo que acabou de dar certo.
    mostrarErro(state.aviso);
    pintar(simulacao, dados);
  } catch (erro) {
    // Mantém os últimos números na tela: zerar tudo esconde o que o dono estava
    // olhando por causa de uma digitação a meio caminho.
    mostrarErro(`Não foi possível recalcular: ${erro.message}`);
  }
}

function agendarCalculo() {
  clearTimeout(state.timer);
  state.timer = setTimeout(calcular, 200);
}

async function referenciaDoBairro() {
  const bairro = $('f-bairro').value.trim();
  const alvo = $('ref-bairro');
  alvo.textContent = '';
  if (!bairro || !state.cidade) return;
  try {
    const dados = await fetchJson(`/neighborhoods/${encodeURIComponent(bairro)}`, {
      city: state.cidade,
      months: 12,
    });
    // A corrigida pelo IPCA é a que compara com dinheiro de hoje; a nominal
    // entra só quando não há série de correção para o período.
    const mediana = dados.median_price_per_m2_corrected || dados.median_price_per_m2;
    if (mediana) {
      alvo.textContent = `Mediana de ITBI no bairro: ${formatCurrency(mediana)}/m² em 12 meses.`;
    }
  } catch (erro) {
    // Referência é conforto, não requisito: sem ela a tela segue funcionando.
    alvo.textContent = '';
  }
}

function preencher(dados) {
  if (dados.endereco !== undefined) $('f-endereco').value = dados.endereco || '';
  if (dados.apelido !== undefined) $('f-apelido').value = dados.apelido || '';
  if (dados.bairro !== undefined) $('f-bairro').value = dados.bairro || '';
  CAMPOS_NUMERICOS.forEach((campo) => {
    const input = document.querySelector(`[name="${campo}"]`);
    if (dados[campo] !== null && dados[campo] !== undefined) input.value = dados[campo];
  });
  CAMPOS_BOOLEANOS.forEach((campo) => {
    if (dados[campo] !== undefined) {
      document.querySelector(`[name="${campo}"]`).checked = Boolean(dados[campo]);
    }
  });
  if (dados.status) $('f-status').value = dados.status;
}

/* O que a origem sabe entra; o que ela não sabe (área seca, portas) fica no
 * padrão da tela, para o dono corrigir olhando as fotos. */
async function preencherDaOrigem(origem, origemId) {
  if (origem === 'oportunidade') {
    const anuncio = await enviar(`/opportunities/${origemId}`, 'GET');
    const numero = anuncio.numero ? `, ${anuncio.numero}` : '';
    preencher({
      endereco: `${anuncio.rua || ''}${numero}`.trim(),
      bairro: anuncio.bairro || '',
      area_util_m2: anuncio.area_util_m2 || undefined,
      area_seca_m2: anuncio.area_util_m2 || undefined,
      quartos: anuncio.quartos ?? undefined,
      banheiros: anuncio.banheiros ?? undefined,
      preco_compra: anuncio.preco_anunciado || undefined,
    });
    return;
  }
  if (origem === 'leilao') {
    const imoveis = await enviar('/auctions?incluir_passados=true', 'GET');
    const imovel = imoveis.find((item) => String(item.id) === String(origemId));
    if (!imovel) throw new Error('imóvel de leilão não encontrado');
    const numero = imovel.address_number ? `, ${imovel.address_number}` : '';
    preencher({
      apelido: imovel.apelido || '',
      endereco: `${imovel.address || ''}${numero}`.trim(),
      bairro: imovel.neighborhood || '',
      area_util_m2: imovel.total_area || undefined,
      area_seca_m2: imovel.total_area || undefined,
      quartos: imovel.bedroom_count ?? undefined,
      banheiros: imovel.bathroom_count ?? undefined,
      preco_compra: imovel.lance_minimo || undefined,
    });
  }
}

async function carregarEstudo(id) {
  const estudo = await enviar(`/flips/${id}`, 'GET');
  state.id = estudo.id;
  preencher(estudo);
  $('btn-salvar').textContent = 'Salvar alterações';
}

async function salvar(evento) {
  evento.preventDefault();
  const dados = lerFormulario();
  if (!dados.endereco) {
    mostrarErro('O endereço identifica o estudo na lista; preencha antes de salvar.');
    return;
  }
  try {
    if (state.id) {
      await enviar(`/flips/${state.id}`, 'PATCH', dados);
    } else {
      const criado = await enviar('/flips', 'POST', {
        ...dados,
        origem: state.origem || 'manual',
        origem_id: state.origemId || null,
      });
      state.id = criado.id;
      $('btn-salvar').textContent = 'Salvar alterações';
      window.history.replaceState({}, '', `/flip?id=${criado.id}`);
    }
    state.aviso = '';
    mostrarErro('');
  } catch (erro) {
    mostrarErro(`Não foi possível salvar: ${erro.message}`);
  }
}

async function iniciar() {
  await mountChrome('flip');
  state.cidade = await resolveCity().catch(() => '');

  const form = $('form-imovel');
  form.addEventListener('input', agendarCalculo);
  form.addEventListener('submit', salvar);
  $('f-bairro').addEventListener('change', referenciaDoBairro);
  $('btn-resetar').addEventListener('click', () => {
    form.reset();
    state.id = null;
    state.origem = null;
    state.origemId = null;
    state.aviso = '';
    $('btn-salvar').textContent = 'Salvar estudo';
    window.history.replaceState({}, '', '/flip');
    calcular();
  });

  const params = new URLSearchParams(window.location.search);
  const origem = params.get('origem');
  const origemId = params.get('origem_id');
  if (origem && origemId && !params.get('id')) {
    try {
      await preencherDaOrigem(origem, origemId);
      state.origem = origem;
      state.origemId = Number(origemId);
    } catch (erro) {
      state.aviso = `Não foi possível trazer os dados de origem: ${erro.message}`;
      mostrarErro(state.aviso);
    }
  }
  if (params.get('id')) {
    try {
      await carregarEstudo(params.get('id'));
    } catch (erro) {
      mostrarErro(`Estudo não encontrado: ${erro.message}`);
    }
  }
  await referenciaDoBairro();
  await calcular();
}

iniciar();
