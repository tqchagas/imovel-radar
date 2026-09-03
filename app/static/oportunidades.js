const {
  $,
  el,
  emptyState,
  fetchJson,
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatInteger,
  formatNumber,
  mountChrome,
  resolveCity,
  cityLabel,
} = window.IR;

const PAGE_SIZE = 25;
const SEEN_KEY = 'imovelradar:oportunidades:vistas';
const MUTED_KEY = 'imovelradar:oportunidades:silenciadas';

const REFERENCE_LABELS = {
  endereco_exato: 'Endereço exato',
  rua: 'Rua',
  bairro_area: 'Bairro + faixa de área',
  bairro_amplo: 'Bairro amplo',
};
const TYPE_LABELS = { APARTAMENTO: 'Apartamento', CASA: 'Casa' };

let city = '';
let page = 1;
let lastPayload = null;

/* —— Estado local: "vista" e "silenciado" são preferências do navegador,
   não entram na timeline de ITBI nem no banco. ——————————————— */

const readSet = (key) => {
  try {
    return new Set(JSON.parse(localStorage.getItem(key) || '[]'));
  } catch (error) {
    return new Set();
  }
};

const writeSet = (key, values) => {
  try {
    localStorage.setItem(key, JSON.stringify([...values]));
  } catch (error) {
    /* modo privado: a tela continua funcionando sem persistir */
  }
};

const listingKey = (item) => `${item.source}:${item.listing_id}`;

function toggleIn(key, item) {
  const set = readSet(key);
  const id = listingKey(item);
  if (set.has(id)) set.delete(id);
  else set.add(id);
  writeSet(key, set);
  return set.has(id);
}

/* —— Formatação ————————————————————————————————— */

const discountLabel = (value) =>
  value == null ? '—' : `${formatNumber(value * 100, 1)}%`;

const diasNoAr = (iso) => {
  if (!iso) return null;
  const dias = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  return Number.isFinite(dias) && dias >= 0 ? dias : null;
};

const addressLabel = (item) => {
  const street = [item.rua, item.numero].filter(Boolean).join(', ');
  return street || item.bairro || '—';
};

const headline = (item) => {
  const rooms = item.quartos ? `${item.quartos} ${item.quartos === 1 ? 'quarto' : 'quartos'}` : null;
  return [rooms, item.bairro].filter(Boolean).join(' · ') || addressLabel(item);
};

const SOURCE_LABELS = { loft: 'Loft', quintoandar: 'QuintoAndar', vivareal: 'VivaReal' };
const sourceLabel = (source) => SOURCE_LABELS[source] || source;

const listingMeta = (item) =>
  [
    sourceLabel(item.source),
    TYPE_LABELS[item.tipo_imovel] || item.tipo_imovel,
    item.area_util_m2 ? `${formatNumber(item.area_util_m2, 0)} m²` : null,
  ]
    .filter(Boolean)
    .join(' · ');

/* —— Tabela ————————————————————————————————— */

function referenceCell(item) {
  // Quem respondeu "quanto vale". Mostrar o tier de ITBI aqui quando a
  // avaliação veio do QuintoAndar fazia a linha se contradizer: "estimado
  // R$ 1,98 mi · referência: bairro amplo, 1.228 ITBIs".
  const cell = el('td');
  if (item.referencia_primaria === 'qpreco') {
    cell.appendChild(el('div', 'cell-title', 'QuintoAndar'));
    cell.appendChild(el('div', 'cell-sub', 'avaliou esta unidade'));
    return cell;
  }
  if (item.referencia_primaria === 'qpreco_vizinho') {
    cell.appendChild(el('div', 'cell-title', 'QuintoAndar'));
    cell.appendChild(el('div', 'cell-sub', 'vizinhos da mesma rua'));
    return cell;
  }
  cell.appendChild(el('div', 'cell-title', REFERENCE_LABELS[item.tipo_referencia] || '—'));
  cell.appendChild(el('div', 'cell-sub', `${formatInteger(item.amostra_count)} ITBIs`));
  return cell;
}

function listingCell(item) {
  const cell = el('td');
  const title = el('div', 'cell-title', headline(item));
  const seen = readSet(SEEN_KEY).has(listingKey(item));
  if (seen) title.appendChild(el('span', 'tag', 'vista'));
  cell.appendChild(title);
  cell.appendChild(el('div', 'cell-sub', addressLabel(item)));
  cell.appendChild(el('div', 'cell-sub', listingMeta(item)));
  return cell;
}

function scoreCell(item) {
  const cell = el('td', 'numeric');
  const nota = Number.isFinite(item.nota) ? item.nota : null;
  // The bands match the alert floor: 80 is what "worth a look" means here.
  const tone = nota === null ? '' : nota >= 80 ? ' alta' : nota >= 60 ? '' : ' baixa';
  cell.appendChild(el('strong', `score${tone}`, nota === null ? '—' : String(nota)));
  return cell;
}

function conferenciaCell(item) {
  // A outra régua, para quem quiser ver se as duas concordam: o ITBI quando o
  // QuintoAndar avaliou, e o qpreço quando foi o ITBI que respondeu.
  const cell = el('td', 'numeric');
  const porQpreco = (item.referencia_primaria || 'itbi').startsWith('qpreco');
  const valor = porQpreco ? item.preco_estimado_itbi : item.qpreco_estimado;
  const desconto = porQpreco ? item.desconto_itbi_pct : item.qpreco_desconto_pct;
  if (!Number.isFinite(valor)) {
    cell.appendChild(el('span', 'cell-sub', '—'));
    return cell;
  }
  cell.appendChild(el('div', null, formatCompactCurrency(valor)));
  cell.appendChild(el('div', 'cell-sub', porQpreco ? 'por ITBI' : 'QuintoAndar'));
  if (Number.isFinite(desconto)) {
    const lado = desconto >= 0 ? 'abaixo' : 'acima';
    cell.appendChild(el('div', 'cell-sub', `${discountLabel(Math.abs(desconto))} ${lado}`));
  }
  return cell;
}

function row(item) {
  const tr = el('tr', 'clickable');
  tr.appendChild(scoreCell(item));
  tr.appendChild(listingCell(item));
  tr.appendChild(el('td', 'numeric', formatCompactCurrency(item.preco_anunciado)));
  tr.appendChild(el('td', 'numeric', formatCompactCurrency(item.preco_estimado)));
  tr.appendChild(conferenciaCell(item));
  const discount = el('td', 'numeric');
  const strong = el('strong', item.desconto_pct >= 0 ? 'alta' : null, discountLabel(item.desconto_pct));
  discount.appendChild(strong);
  tr.appendChild(discount);
  tr.appendChild(referenceCell(item));
  tr.addEventListener('click', () => openDetail(item));
  return tr;
}

/* —— Detalhe ————————————————————————————————— */

function detailLine(label, value) {
  const line = el('div', 'detail-cell');
  line.appendChild(el('span', 'detail-label', label));
  line.appendChild(el('span', 'detail-value', value));
  return line;
}

function openDetail(item) {
  const panel = $('detail');
  const body = $('detail-body');
  body.replaceChildren();
  $('detail-title').textContent = `${headline(item)} — ${addressLabel(item)}`;

  const grid = el('div', 'divided-grid cols-4');
  grid.appendChild(detailLine('Anunciado', formatCurrency(item.preco_anunciado)));
  // Quem respondeu "quanto vale" muda a régua inteira: o qpreço avalia a
  // unidade e erra ~5%, a escada de ITBI vê rua e metragem e erra 22%.
  const REGUA = {
    qpreco: 'Vale · QuintoAndar avaliou esta unidade',
    qpreco_vizinho: 'Vale · QuintoAndar avaliou vizinhos da rua',
    itbi: 'Vale · mediana de ITBI',
  };
  const porQpreco = (item.referencia_primaria || 'itbi').startsWith('qpreco');
  grid.appendChild(detailLine(
    REGUA[item.referencia_primaria] || REGUA.itbi,
    formatCurrency(item.preco_estimado),
  ));
  if (porQpreco && Number.isFinite(item.preco_estimado_itbi)) {
    grid.appendChild(detailLine(
      'Conferência por ITBI',
      `${formatCurrency(item.preco_estimado_itbi)} · ${discountLabel(item.desconto_itbi_pct)}`,
    ));
  }
  grid.appendChild(detailLine('Nota', Number.isFinite(item.nota) ? `${item.nota}/100` : '—'));
  grid.appendChild(detailLine('Desconto', `${discountLabel(item.desconto_pct)} · ${formatCurrency(item.desconto_reais)}`));
  if (Number.isFinite(item.dispersao_relativa)) {
    grid.appendChild(detailLine(
      'Variação da referência',
      `${Math.round(item.dispersao_relativa * 100)}% entre os ITBIs comparados`,
    ));
  }
  if (Number.isFinite(item.fator_calibracao)) {
    // O fator junta dois efeitos: prêmio de anúncio sobre venda e a diferença
    // entre área construída (ITBI) e área útil (anúncio). O rótulo antigo
    // prometia só o primeiro.
    grid.appendChild(detailLine('Fator anúncio ÷ ITBI', `${item.fator_calibracao.toFixed(2)}x · inclui a diferença de área entre cartório e anúncio`));
  }
  grid.appendChild(
    detailLine('Referência', `${REFERENCE_LABELS[item.tipo_referencia] || '—'} · ${formatInteger(item.amostra_count)} ITBIs`)
  );
  const dias = diasNoAr(item.anunciado_em);
  if (dias !== null) {
    // Metade do estoque do Loft está no ar há mais de um ano. Desconto em
    // anúncio parado é preço que o mercado já recusou, não achado.
    grid.appendChild(detailLine('No ar há', `${formatInteger(dias)} dias`));
  }
  if (Number.isFinite(item.similares_m2_anunciado)) {
    // Média do entorno para imóveis de tamanho parecido, não avaliação desta
    // unidade: um apartamento pode estar abaixo dela por ser pior.
    const proprio = item.area_util_m2 ? item.preco_anunciado / item.area_util_m2 : null;
    const comparacao = proprio
      ? ` · este pede ${formatCurrency(proprio)}/m²`
      : '';
    grid.appendChild(detailLine(
      'Vizinhança (anúncios)',
      `${formatCurrency(item.similares_m2_anunciado)}/m²${comparacao}`,
    ));
  }
  if (Number.isFinite(item.similares_m2_negociado)) {
    grid.appendChild(detailLine(
      'Vizinhança (fora do mercado)',
      `${formatCurrency(item.similares_m2_negociado)}/m²`,
    ));
  }
  if (Number.isFinite(item.similares_dias_ate_negocio)) {
    grid.appendChild(detailLine(
      'Liquidez da região',
      `${formatInteger(item.similares_dias_ate_negocio)} dias até fechar, em média`,
    ));
  }
  if (Number.isFinite(item.condominio) || Number.isFinite(item.iptu)) {
    const custo = [
      Number.isFinite(item.condominio) ? `condomínio ${formatCurrency(item.condominio)}` : null,
      Number.isFinite(item.iptu) ? `IPTU ${formatCurrency(item.iptu)}` : null,
    ].filter(Boolean).join(' · ');
    grid.appendChild(detailLine('Custo mensal', custo));
  }
  if (Number.isFinite(item.qpreco_estimado)) {
    // The score column shows only the lower of the two references, so the
    // detail is where both halves have to be visible.
    // O valor já aparece na célula "Vale"; aqui interessa como as duas réguas
    // pontuaram o mesmo anúncio.
    grid.appendChild(
      detailLine(
        'Notas das duas réguas',
        `QuintoAndar ${formatInteger(item.nota_qpreco)} · ITBI ${formatInteger(item.nota_itbi)}`
      )
    );
  }
  body.appendChild(grid);

  body.appendChild(
    el(
      'p',
      'panel-note',
      `Período da amostra: ${formatDate(item.referencia_data_inicio)} a ${formatDate(item.referencia_data_fim)}.`
    )
  );

  if (Number.isFinite(item.nota_qpreco) && Number.isFinite(item.nota_itbi) && item.nota_qpreco < item.nota_itbi) {
    body.appendChild(
      el(
        'p',
        'scope-banner',
        'As duas referências discordam: o ITBI vê desconto maior do que a estimativa do próprio QuintoAndar. A nota exibida é a menor das duas.'
      )
    );
  }

  if (Number.isFinite(item.nota) && item.nota < 60) {
    body.appendChild(
      el(
        'p',
        'scope-banner',
        'Nota baixa: o desconto é pequeno frente ao quanto a referência varia, ou a amostra é rasa demais. Use apenas como indício.'
      )
    );
  }

  const reasons = el('ul');
  (item.motivos || []).forEach((motivo) => reasons.appendChild(el('li', null, motivo)));
  body.appendChild(reasons);

  const actions = el('div', 'property-actions');
  const seen = el('button', 'btn btn-secondary btn-sm');
  seen.type = 'button';
  seen.textContent = readSet(SEEN_KEY).has(listingKey(item)) ? 'Desmarcar vista' : 'Marcar como vista';
  seen.addEventListener('click', () => {
    toggleIn(SEEN_KEY, item);
    render();
    openDetail(item);
  });
  const mute = el('button', 'btn btn-secondary btn-sm');
  mute.type = 'button';
  mute.textContent = readSet(MUTED_KEY).has(listingKey(item)) ? 'Reexibir anúncio' : 'Silenciar anúncio';
  mute.addEventListener('click', () => {
    toggleIn(MUTED_KEY, item);
    render();
  });
  actions.append(seen, mute);
  if (item.url) {
    const open = el('a', 'btn btn-sm', 'Abrir no portal');
    open.href = item.url;
    open.target = '_blank';
    open.rel = 'noopener noreferrer';
    actions.appendChild(open);
  }
  body.appendChild(actions);
  abrirModal(panel);
}

function abrirModal(panel) {
  panel.hidden = false;
  document.body.classList.add('modal-aberto');
  panel.scrollTop = 0;
  $('detail-close').focus();
}

function fecharModal() {
  $('detail').hidden = true;
  document.body.classList.remove('modal-aberto');
}

/* —— Render ————————————————————————————————— */

function visibleItems() {
  const muted = readSet(MUTED_KEY);
  return (lastPayload?.items || []).filter((item) => !muted.has(listingKey(item)));
}


// --- faixas de nota e mapa ----------------------------------------------------

// Mesma ordem e mesmos cortes de `SCORE_BANDS` no domínio. Cada corte é um
// múltiplo do erro típico da referência que respondeu, não um número escolhido
// a dedo: nota 80 é um desconto de 3,2x esse erro, nota 40 é 1,6x.
const FAIXAS = [
  { chave: 'forte', rotulo: 'Forte', dica: 'Desconto muito acima do erro típico desta referência' },
  { chave: 'oferta', rotulo: 'Vale oferta', dica: 'Desconto grande o bastante para sustentar uma proposta' },
  { chave: 'monitorar', rotulo: 'Monitorar', dica: 'Desconto real, mas perto do que esta referência costuma errar' },
  { chave: 'ruido', rotulo: 'Ruído', dica: 'Desconto dentro da barra de erro da referência' },
  { chave: 'sem_sinal', rotulo: 'Sem sinal', dica: 'Sem desconto que a referência sustente' },
];

let faixaAtiva = null;
let mapa = null;
let camadaPinos = null;

function renderFaixas() {
  const alvo = $('band-legend');
  alvo.replaceChildren();
  // As contagens vêm do servidor, sobre o resultado inteiro. Contar na página
  // seria enganoso: ordenada por nota, a primeira página é de uma faixa só.
  const contagem = lastPayload?.summary?.faixas || {};
  const usadas = FAIXAS.filter(({ chave }) => contagem[chave]);
  if (!usadas.length) {
    alvo.hidden = true;
    return;
  }
  alvo.hidden = false;
  usadas.forEach(({ chave, rotulo, dica }) => {
    const chip = el('button', 'band-chip');
    chip.type = 'button';
    chip.dataset.band = chave;
    chip.title = dica;
    chip.setAttribute('aria-pressed', String(faixaAtiva === chave));
    chip.append(el('span', 'band-count', formatInteger(contagem[chave])), el('span', null, rotulo));
    chip.addEventListener('click', () => {
      // Clicar na faixa ativa a desliga: é filtro, não modo.
      faixaAtiva = faixaAtiva === chave ? null : chave;
      page = 1;
      load();
    });
    alvo.appendChild(chip);
  });
}

function pino(item) {
  const marca = el('div', 'map-pin', String(item.nota ?? '—'));
  marca.dataset.band = item.faixa || 'sem_sinal';
  return L.divIcon({
    html: marca.outerHTML,
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

// A ordem é a mesma de FAIXAS: a primeira que aparecer num grupo é a melhor
// nota que ele esconde, e é a cor que o grupo veste.
const ORDEM_FAIXAS = FAIXAS.map((f) => f.chave);

function agrupamento(cluster) {
  const marcas = cluster.getAllChildMarkers();
  let melhor = ORDEM_FAIXAS.length - 1;
  marcas.forEach((m) => {
    const posicao = ORDEM_FAIXAS.indexOf(m.options.faixa);
    if (posicao >= 0 && posicao < melhor) melhor = posicao;
  });
  const marca = el('div', 'cluster-pin', formatInteger(marcas.length));
  marca.dataset.band = ORDEM_FAIXAS[melhor];
  return L.divIcon({ html: marca.outerHTML, className: '', iconSize: [38, 38] });
}

function popup(ponto) {
  const linhas = [
    `<strong>${ponto.rua || ''} ${ponto.numero || ''}</strong>`,
    ponto.bairro || '',
    `${formatCurrency(ponto.preco_anunciado)} · nota ${ponto.nota ?? '—'}`,
    `estimado ${formatCurrency(ponto.preco_estimado)} · ${discountLabel(ponto.desconto_pct)}`,
  ];
  return (
    `${linhas.filter(Boolean).join('<br>')}<br>` +
    (ponto.url ? `<a href="${ponto.url}" target="_blank" rel="noopener">abrir anúncio</a>` : '')
  );
}

function iniciaMapa() {
  mapa = L.map('map', { scrollWheelZoom: false });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; colaboradores do OpenStreetMap',
  }).addTo(mapa);
  camadaPinos = L.markerClusterGroup({
    iconCreateFunction: agrupamento,
    // O grupo se desfaz cedo: a partir daí interessa ver prédio por prédio.
    disableClusteringAtZoom: 17,
    // Bem abaixo do padrão de 80 px. Um bairro compacto como a Savassi tem dois
    // quilômetros de ponta a ponta, e com raio largo os trezentos anúncios dele
    // viram uma bolha única no zoom em que o bairro inteiro cabe na tela.
    maxClusterRadius: 32,
    showCoverageOnHover: false,
  }).addTo(mapa);
  mapa.setView([-19.9227, -43.9451], 12);
}

// O mapa mostra o resultado inteiro, não a página. Um mapa paginado desenha
// vinte e cinco pinos espalhados pela cidade e some com o resto sem avisar.
async function renderMapa() {
  if (typeof L === 'undefined' || $('map-view').hidden) return;
  if (!mapa) iniciaMapa();

  const total = lastPayload?.total || 0;
  $('map-note').textContent = 'Carregando os pontos…';
  let pontos = [];
  try {
    const { page: _p, page_size: _ps, sort: _s, ...filtros } = currentParams();
    pontos = await fetchJson('/opportunities/map', filtros);
  } catch (error) {
    $('map-note').textContent = 'Não foi possível carregar os pontos do mapa.';
    return;
  }

  camadaPinos.clearLayers();
  camadaPinos.addLayers(
    pontos.map((ponto) => {
      const marca = L.marker([ponto.lat, ponto.lon], {
        icon: pino(ponto),
        faixa: ponto.faixa || 'sem_sinal',
      });
      marca.bindPopup(popup(ponto));
      return marca;
    })
  );

  const semPonto = total - pontos.length;
  $('map-note').textContent = semPonto > 0
    ? `${formatInteger(pontos.length)} de ${formatInteger(total)} no mapa. `
      + `${formatInteger(semPonto)} sem coordenada aparecem só na tabela — o portal não publicou o ponto.`
    : `${formatInteger(pontos.length)} no mapa.`;

  // Antes do enquadramento, não depois: o contêiner nasce escondido, o Leaflet
  // guarda o tamanho errado, e `fitBounds` calculado contra ele escolhe um zoom
  // baixo demais — filtrar por um bairro abria a cidade inteira.
  mapa.invalidateSize();
  if (pontos.length) {
    mapa.fitBounds(L.latLngBounds(pontos.map((p) => [p.lat, p.lon])), {
      padding: [30, 30],
      maxZoom: 16,
    });
  }
}

function trocarVisao(paraMapa) {
  $('map-view').hidden = !paraMapa;
  $('table-view').hidden = paraMapa;
  // A paginação é da tabela; no mapa ela não governa nada.
  $('pagination').hidden = paraMapa;
  $('view-mapa').classList.toggle('is-active', paraMapa);
  $('view-tabela').classList.toggle('is-active', !paraMapa);
  if (paraMapa) renderMapa();
}

function render() {
  const body = $('results-body');
  body.replaceChildren();
  renderFaixas();
  const items = visibleItems();
  const total = lastPayload?.total || 0;

  $('kpi-total').textContent = formatInteger(total);
  $('kpi-max').textContent = discountLabel(lastPayload?.summary?.max_desconto_pct);
  const maxNota = lastPayload?.summary?.max_nota;
  $('kpi-nota').textContent = Number.isFinite(maxNota) ? String(maxNota) : '—';
  $('kpi-coleta').textContent = lastPayload?.summary?.last_collected_at
    ? new Date(lastPayload.summary.last_collected_at).toLocaleString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';
  $('kpi-referencia').textContent = formatDate(lastPayload?.summary?.reference_date);

  $('results-count').textContent = total
    ? `${formatInteger(total)} ${total === 1 ? 'oportunidade' : 'oportunidades'}`
    : 'Nenhuma oportunidade';
  $('results-scope').textContent = city ? cityLabel(city) : '';

  if (!items.length) {
    const cell = el('td');
    cell.colSpan = 7;
    cell.appendChild(
      emptyState(
        'Nenhuma oportunidade com esses filtros',
        'Reduza a nota mínima, ou desmarque "Só com qpreço" — a estimativa do '
          + 'QuintoAndar só existe para parte dos anúncios dele.'
      )
    );
    const tr = el('tr');
    tr.appendChild(cell);
    body.appendChild(tr);
  } else {
    items.forEach((item) => body.appendChild(row(item)));
  }

  renderMapa();

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  $('page-info').textContent = `Página ${page} de ${pages}`;
  $('prev').disabled = page <= 1;
  $('next').disabled = page >= pages;
}

function currentParams() {
  const params = { page, page_size: PAGE_SIZE, sort: $('sort').value };
  if (city) params.city = city;
  const neighborhood = $('neighborhood').value.trim();
  if (neighborhood) params.neighborhood = neighborhood;
  const source = $('source').value;
  if (source) params.source = source;
  const tipo = $('tipo_imovel').value;
  if (tipo) params.tipo_imovel = tipo;
  const nota = $('min_nota').value;
  if (nota && Number(nota) > 0) params.min_nota = nota;
  if ($('com_qpreco').checked) params.com_qpreco = 'true';
  if (faixaAtiva) params.faixa = faixaAtiva;
  return params;
}

async function load() {
  try {
    lastPayload = await fetchJson('/opportunities', currentParams());
  } catch (error) {
    lastPayload = { items: [], total: 0, summary: {} };
    $('results-count').textContent = 'Não foi possível carregar as oportunidades';
  }
  render();
}

async function fillNeighborhoods() {
  if (!city) return;
  // Os bairros vêm dos próprios anúncios pontuados, não do ITBI: a lista do
  // ITBI cobre a cidade inteira, e escolher um bairro sem anúncio devolve uma
  // tela vazia sem explicar por quê. A contagem vai junto para que a escolha
  // seja informada antes do clique.
  const bairros = await fetchJson('/opportunities/neighborhoods', { city }).catch(() => []);
  const lista = $('neighborhood-options');
  lista.replaceChildren();
  bairros.forEach(({ nome, total }) => {
    const opcao = el('option');
    opcao.value = nome;
    opcao.label = `${nome} (${formatInteger(total)})`;
    lista.appendChild(opcao);
  });
  $('neighborhood').placeholder = `Todos os ${formatInteger(bairros.length)} bairros`;
}

async function init() {
  await mountChrome('oportunidades');
  city = await resolveCity();
  await fillNeighborhoods();
  $('filter-form').addEventListener('submit', (event) => {
    event.preventDefault();
    page = 1;
    load();
  });
  const slider = $('min_nota');
  const readout = $('min_nota_valor');
  const showScore = () => {
    readout.innerHTML = '';
    readout.appendChild(el('strong', null, slider.value));
  };
  showScore();
  // Dragging only updates the label; the fetch waits for the slider to settle.
  slider.addEventListener('input', showScore);
  slider.addEventListener('change', () => {
    page = 1;
    load();
  });

  $('sort').addEventListener('change', () => {
    page = 1;
    load();
  });
  // Escolher da lista dispara `change`; digitar e sair do campo também. Nos
  // dois casos o usuário terminou de escolher, e exigir o botão depois disso
  // é um passo a mais sem função.
  $('neighborhood').addEventListener('change', () => {
    page = 1;
    load();
  });
  $('prev').addEventListener('click', () => {
    page = Math.max(1, page - 1);
    load();
  });
  $('next').addEventListener('click', () => {
    page += 1;
    load();
  });
  $('view-mapa').addEventListener('click', () => trocarVisao(true));
  $('view-tabela').addEventListener('click', () => trocarVisao(false));
  $('detail-close').addEventListener('click', fecharModal);
  // Fechar pelo fundo e pelo Esc: num modal, clicar fora é o gesto esperado.
  $('detail').addEventListener('click', (evento) => {
    if (evento.target === $('detail')) fecharModal();
  });
  document.addEventListener('keydown', (evento) => {
    if (evento.key === 'Escape' && !$('detail').hidden) fecharModal();
  });
  await load();
}

init();
