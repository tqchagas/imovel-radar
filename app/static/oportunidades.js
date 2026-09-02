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
  // The score already carries the trust judgment, and it reads the sample
  // directly. Showing the old tier next to it produced rows labelled "baixa"
  // with a score of 100, which is a contradiction, not information. What is
  // still worth showing is the factual scope the reference came from.
  const cell = el('td');
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

function qprecoCell(item) {
  // Only QuintoAndar publishes an estimate, so most rows are empty here. When
  // there is one, the discount against it is what says whether the two
  // references agree — the score column already shows only the lower of them.
  const cell = el('td', 'numeric');
  if (!Number.isFinite(item.qpreco_estimado)) {
    cell.appendChild(el('span', 'cell-sub', '—'));
    return cell;
  }
  cell.appendChild(el('div', null, formatCompactCurrency(item.qpreco_estimado)));
  if (Number.isFinite(item.qpreco_desconto_pct)) {
    const pct = Math.abs(item.qpreco_desconto_pct);
    const lado = item.qpreco_desconto_pct >= 0 ? 'abaixo' : 'acima';
    cell.appendChild(el('div', 'cell-sub', `anúncio ${discountLabel(pct)} ${lado}`));
  }
  return cell;
}

function row(item) {
  const tr = el('tr', 'clickable');
  tr.appendChild(scoreCell(item));
  tr.appendChild(listingCell(item));
  tr.appendChild(el('td', 'numeric', formatCompactCurrency(item.preco_anunciado)));
  tr.appendChild(el('td', 'numeric', formatCompactCurrency(item.preco_estimado)));
  tr.appendChild(qprecoCell(item));
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
  const line = el('div', 'compare-cell');
  line.appendChild(el('span', 'compare-label', label));
  line.appendChild(el('span', null, value));
  return line;
}

function openDetail(item) {
  const panel = $('detail');
  const body = $('detail-body');
  body.replaceChildren();
  $('detail-title').textContent = `${headline(item)} — ${addressLabel(item)}`;

  const grid = el('div', 'divided-grid cols-4');
  grid.appendChild(detailLine('Anunciado', formatCurrency(item.preco_anunciado)));
  grid.appendChild(detailLine('Estimado', formatCurrency(item.preco_estimado)));
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
    grid.appendChild(
      detailLine(
        'QuintoAndar estima',
        `${formatCurrency(item.qpreco_estimado)} · nota ${formatInteger(item.nota_qpreco)}`
          + ` (ITBI ${formatInteger(item.nota_itbi)})`
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
  panel.hidden = false;
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* —— Render ————————————————————————————————— */

function visibleItems() {
  const muted = readSet(MUTED_KEY);
  return (lastPayload?.items || []).filter((item) => !muted.has(listingKey(item)));
}

function render() {
  const body = $('results-body');
  body.replaceChildren();
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

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  $('page-info').textContent = `Página ${page} de ${pages}`;
  $('prev').disabled = page <= 1;
  $('next').disabled = page >= pages;
}

function currentParams() {
  const params = { page, page_size: PAGE_SIZE, sort: $('sort').value };
  if (city) params.city = city;
  const neighborhood = $('neighborhood').value;
  if (neighborhood) params.neighborhood = neighborhood;
  const source = $('source').value;
  if (source) params.source = source;
  const tipo = $('tipo_imovel').value;
  if (tipo) params.tipo_imovel = tipo;
  const nota = $('min_nota').value;
  if (nota && Number(nota) > 0) params.min_nota = nota;
  if ($('com_qpreco').checked) params.com_qpreco = 'true';
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
  const names = await fetchJson('/neighborhoods', { city }).catch(() => []);
  const select = $('neighborhood');
  names.sort((a, b) => a.localeCompare(b, 'pt-BR')).forEach((name) => {
    const option = el('option', null, name);
    option.value = name;
    select.appendChild(option);
  });
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
  $('prev').addEventListener('click', () => {
    page = Math.max(1, page - 1);
    load();
  });
  $('next').addEventListener('click', () => {
    page += 1;
    load();
  });
  $('detail-close').addEventListener('click', () => {
    $('detail').hidden = true;
  });
  await load();
}

init();
