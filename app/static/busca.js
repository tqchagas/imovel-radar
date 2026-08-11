const {
  $,
  el,
  chevron,
  emptyState,
  fetchJson,
  formatCurrency,
  formatDate,
  formatInteger,
  formatNumber,
  deltaTag,
  mountChrome,
  navigate,
  propertyUrl,
} = window.IR;

const LIMIT = 50;
const VIEW_KEY = 'imovelradar:busca-view';

const TYPE_LABELS = {
  AP: 'Apartamento',
  CS: 'Casa',
  LO: 'Loja / sala',
  GA: 'Garagem',
  TE: 'Terreno',
};

const FILTER_IDS = [
  'city',
  'neighborhood',
  'street',
  'street_number',
  'min_value',
  'max_value',
  'min_area',
  'max_area',
  'construction_type',
  'occupation_type',
  'date_from',
  'date_to',
];

const CHIP_LABELS = {
  neighborhood: (v) => v,
  street: (v) => `Rua: ${v}`,
  street_number: (v) => `Nº ${v}`,
  min_value: (v) => `A partir de ${formatCurrency(Number(v))}`,
  max_value: (v) => `Até ${formatCurrency(Number(v))}`,
  min_area: (v) => `≥ ${v} m²`,
  max_area: (v) => `≤ ${v} m²`,
  construction_type: (v) => TYPE_LABELS[v] || v,
  occupation_type: (v) => v.charAt(0) + v.slice(1).toLowerCase(),
  date_from: (v) => `Desde ${formatDate(v)}`,
  date_to: (v) => `Até ${formatDate(v)}`,
};

let currentPage = 0;
let totalResults = 0;
let view = window.localStorage.getItem(VIEW_KEY) === 'cards' ? 'cards' : 'tabela';
let neighborhoodMedians = new Map();
let relaxSuggestion = null;

const filterValues = () =>
  Object.fromEntries(
    FILTER_IDS.map((id) => [id, $(id).value]).filter(([, value]) => value !== '')
  );

const pricePerM2 = (item) =>
  item.built_area_acquired && item.built_area_acquired > 0
    ? item.declared_value / item.built_area_acquired
    : null;

/** How this unit's R$/m² sits against its neighborhood median. */
function neighborhoodDelta(item) {
  const median = neighborhoodMedians.get(item.neighborhood);
  const m2 = pricePerM2(item);
  if (!median || m2 == null) return null;
  return (m2 / median - 1) * 100;
}

const addressLabel = (item) =>
  item.street_number ? `${item.street}, ${item.street_number}` : item.street;

/* —— URL <-> formulário ————————————————————————— */

function readUrl() {
  const params = new URLSearchParams(window.location.search);
  FILTER_IDS.forEach((id) => {
    const value = params.get(id);
    if (value !== null) $(id).value = value;
  });
  const sort = params.get('sort');
  if (sort) $('sort').value = sort;
  const page = params.get('page');
  if (page) currentPage = Math.max(0, parseInt(page, 10) - 1);
  return params.get('neighborhood');
}

function writeUrl() {
  const params = new URLSearchParams(filterValues());
  if ($('sort').value !== 'date_desc') params.set('sort', $('sort').value);
  if (currentPage > 0) params.set('page', String(currentPage + 1));
  const query = params.toString();
  window.history.replaceState({}, '', query ? `/busca?${query}` : '/busca');
}

/* —— Filtros ativos ————————————————————————————— */

function renderChips() {
  const box = $('active-filters');
  box.innerHTML = '';
  const active = Object.entries(filterValues()).filter(([id]) => id !== 'city');
  if (!active.length) return;

  box.appendChild(el('span', 'label', 'Filtros ativos'));
  active.forEach(([id, value]) => {
    const chip = el('button', 'chip');
    chip.type = 'button';
    chip.append(
      document.createTextNode((CHIP_LABELS[id] || ((v) => v))(value)),
      el('span', 'x', '✕')
    );
    chip.title = 'Remover filtro';
    chip.addEventListener('click', () => {
      $(id).value = '';
      currentPage = 0;
      search();
    });
    box.appendChild(chip);
  });

  const clear = el('button', 'link-button', 'Limpar tudo');
  clear.type = 'button';
  clear.addEventListener('click', () => {
    active.forEach(([id]) => {
      $(id).value = '';
    });
    currentPage = 0;
    search();
  });
  box.appendChild(clear);
}

/* —— Sem resultados ————————————————————————————— */

/* Narrowest filter first: dropping it is the widest single step back. */
const RELAX_ORDER = [
  'street_number',
  'street',
  'min_value',
  'max_value',
  'min_area',
  'max_area',
  'date_from',
  'date_to',
  'occupation_type',
  'construction_type',
  'neighborhood',
];

const chipLabel = (id, value) => (CHIP_LABELS[id] || ((v) => v))(value);

/** Which single filter, once dropped, actually brings results back. Probing
    beats guessing: an escape hatch that lands on another empty screen is
    worse than none, so the suggestion carries its own count as proof. */
async function findRelaxable() {
  const active = filterValues();
  const candidates = RELAX_ORDER.filter((id) => active[id]).slice(0, 4);

  const totals = await Promise.all(
    candidates.map((id) => {
      const params = { ...active, limit: 1 };
      delete params[id];
      return fetchJson('/transactions', params)
        .then((data) => data.total)
        .catch(() => 0);
    })
  );

  let best = null;
  candidates.forEach((id, index) => {
    if (totals[index] > 0 && (!best || totals[index] > best.total)) {
      best = { id, total: totals[index] };
    }
  });
  return best;
}

/** A "no results" screen with no next move ends the session. */
function buildEmptyState() {
  const active = filterValues();
  const applied = Object.keys(active).filter((id) => id !== 'city');
  const actions = [];

  if (relaxSuggestion && active[relaxSuggestion.id]) {
    const { id, total } = relaxSuggestion;
    actions.push({
      label: `Remover "${chipLabel(id, active[id])}" · ${formatInteger(total)} quitações`,
      onClick: () => {
        $(id).value = '';
        currentPage = 0;
        search();
      },
    });
  }

  if (applied.length > 1) {
    actions.push({
      label: 'Limpar filtros',
      onClick: () => {
        applied.forEach((id) => {
          $(id).value = '';
        });
        currentPage = 0;
        search();
      },
    });
  }

  actions.push({
    label: 'Ver ranking de bairros',
    href: active.city ? `/bairro?city=${encodeURIComponent(active.city)}` : '/bairro',
  });

  return emptyState(
    'Nenhuma quitação com esses filtros.',
    'A base só tem ITBI quitado: um endereço sem venda registrada na janela não ' +
      'aparece — o que não é o mesmo que não existir.',
    actions
  );
}

/* —— Renderização ————————————————————————————— */

function renderTable(items) {
  const tbody = $('results-body');
  tbody.innerHTML = '';

  if (!items.length) {
    const row = el('tr');
    const cell = el('td');
    cell.colSpan = 8;
    cell.appendChild(buildEmptyState());
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  items.forEach((item) => {
    const row = el('tr', 'clickable');
    row.title = item.complement
      ? `Ver histórico de ${item.complement}`
      : 'Ver histórico do imóvel';

    row.appendChild(el('td', 'numeric', formatDate(item.settlement_date)));

    const address = el('td');
    address.append(
      el('div', 'cell-title', addressLabel(item)),
      el('div', 'cell-sub', item.complement || '—')
    );
    row.appendChild(address);

    row.appendChild(el('td', null, item.neighborhood));

    const type = el('td');
    type.appendChild(
      el('span', 'tag', TYPE_LABELS[item.construction_type] || item.construction_type || '—')
    );
    row.appendChild(type);

    row.appendChild(el('td', 'numeric', formatNumber(item.built_area_acquired)));
    row.appendChild(el('td', 'numeric strong', formatCurrency(item.declared_value)));
    row.appendChild(el('td', 'numeric', formatCurrency(pricePerM2(item))));

    const delta = el('td', 'numeric');
    delta.appendChild(deltaTag(neighborhoodDelta(item)));
    row.appendChild(delta);

    row.addEventListener('click', (event) => navigate(event, propertyUrl(item)));
    tbody.appendChild(row);
  });
}

function renderCards(items) {
  const grid = $('cards-view');
  grid.innerHTML = '';

  if (!items.length) {
    grid.appendChild(buildEmptyState());
    return;
  }

  items.forEach((item) => {
    const card = el('button', 'result-card');
    card.type = 'button';

    const top = el('div', 'result-card-top');
    top.append(
      el('span', 'tag', TYPE_LABELS[item.construction_type] || item.construction_type || '—'),
      el('span', 'small tabular', formatDate(item.settlement_date))
    );

    const head = el('div');
    head.append(
      el('div', 'result-card-address', addressLabel(item)),
      el('div', 'small', `${item.complement || 'sem complemento'} · ${item.neighborhood}`)
    );

    const foot = el('div', 'result-card-foot');
    foot.append(
      el('span', null, `${formatNumber(item.built_area_acquired)} m²`),
      el('span', null, `${formatCurrency(pricePerM2(item))}/m²`)
    );
    const push = el('span', 'push');
    push.appendChild(deltaTag(neighborhoodDelta(item)));
    foot.appendChild(push);

    card.append(top, head, el('div', 'result-card-value', formatCurrency(item.declared_value)), foot);
    card.addEventListener('click', (event) => navigate(event, propertyUrl(item)));
    grid.appendChild(card);
  });
}

function applyView() {
  $('table-view').hidden = view !== 'tabela';
  $('cards-view').hidden = view !== 'cards';
  $('view-table').setAttribute('aria-pressed', String(view === 'tabela'));
  $('view-cards').setAttribute('aria-pressed', String(view === 'cards'));
}

function renderScope(data) {
  $('results-count').textContent =
    totalResults === 1 ? '1 quitação' : `${formatInteger(totalResults)} quitações`;

  const filters = filterValues();
  const parts = [];
  if (filters.city) parts.push(window.IR.cityLabel(filters.city));
  if (filters.neighborhood) parts.push(filters.neighborhood);
  const sortLabel = $('sort').selectedOptions[0]?.textContent.toLowerCase();
  parts.push(`ordenado por ${sortLabel}`);
  if (data.items.length) {
    const dates = data.items.map((i) => i.settlement_date);
    parts.push(`${formatDate(dates[dates.length - 1])} – ${formatDate(dates[0])}`);
  }
  $('results-scope').textContent = parts.join(' · ');
}

/* —— Dados ————————————————————————————————— */

async function loadNeighborhoods(city, selected) {
  const select = $('neighborhood');
  select.innerHTML = '<option value="">Todos os bairros</option>';
  if (!city) return;

  const neighborhoods = await fetchJson('/neighborhoods', { city }).catch(() => []);
  neighborhoods.sort((a, b) => a.localeCompare(b, 'pt-BR')).forEach((name) => {
    const option = el('option', null, name);
    option.value = name;
    select.appendChild(option);
  });
  if (selected) select.value = selected;
}

async function loadNeighborhoodMedians(city) {
  const ranking = await fetchJson('/stats/neighborhoods', {
    city,
    months: 12,
    limit: 500,
    min_transactions: 3,
  }).catch(() => ({ items: [] }));

  neighborhoodMedians = new Map(
    ranking.items
      .filter((i) => i.median_price_per_m2 != null)
      .map((i) => [i.neighborhood, i.median_price_per_m2])
  );
}

async function search() {
  writeUrl();
  renderChips();
  $('search').disabled = true;

  try {
    const data = await fetchJson('/transactions', {
      ...filterValues(),
      sort: $('sort').value,
      limit: LIMIT,
      offset: currentPage * LIMIT,
    });
    totalResults = data.total;
    relaxSuggestion = data.total === 0 ? await findRelaxable() : null;
    renderScope(data);
    renderTable(data.items);
    renderCards(data.items);
    $('page-info').textContent = `Página ${currentPage + 1} de ${Math.max(
      1,
      Math.ceil(totalResults / LIMIT)
    )}`;
    $('prev').disabled = currentPage === 0;
    $('next').disabled = (currentPage + 1) * LIMIT >= totalResults;
  } catch (error) {
    $('results-count').textContent = 'Erro ao buscar';
    $('results-scope').textContent = error.message;
  } finally {
    $('search').disabled = false;
  }
}

async function init() {
  document.querySelectorAll('.select-wrap').forEach((wrap) => wrap.appendChild(chevron()));

  const defaultCity = await mountChrome('busca');

  const cities = await fetchJson('/cities').catch(() => []);
  cities.forEach((city) => {
    const option = el('option', null, window.IR.cityLabel(city));
    option.value = city;
    $('city').appendChild(option);
  });
  if (defaultCity && cities.includes(defaultCity)) $('city').value = defaultCity;

  const wantedNeighborhood = readUrl();
  await loadNeighborhoods($('city').value, wantedNeighborhood);
  await loadNeighborhoodMedians($('city').value);

  applyView();

  $('filter-form').addEventListener('submit', (event) => {
    event.preventDefault();
    currentPage = 0;
    search();
  });

  $('city').addEventListener('change', async () => {
    window.IR.setCity($('city').value);
    currentPage = 0;
    await loadNeighborhoods($('city').value);
    await loadNeighborhoodMedians($('city').value);
    search();
  });

  $('neighborhood').addEventListener('change', () => {
    currentPage = 0;
    search();
  });

  $('sort').addEventListener('change', () => {
    currentPage = 0;
    search();
  });

  $('toggle-advanced').addEventListener('click', () => {
    const advanced = $('advanced');
    advanced.hidden = !advanced.hidden;
    $('toggle-advanced').textContent = advanced.hidden ? 'Mais filtros' : 'Menos filtros';
    $('toggle-advanced').setAttribute('aria-expanded', String(!advanced.hidden));
  });

  $('view-table').addEventListener('click', () => {
    view = 'tabela';
    window.localStorage.setItem(VIEW_KEY, view);
    applyView();
  });

  $('view-cards').addEventListener('click', () => {
    view = 'cards';
    window.localStorage.setItem(VIEW_KEY, view);
    applyView();
  });

  $('prev').addEventListener('click', () => {
    if (currentPage > 0) {
      currentPage -= 1;
      search();
    }
  });

  $('next').addEventListener('click', () => {
    if ((currentPage + 1) * LIMIT < totalResults) {
      currentPage += 1;
      search();
    }
  });

  // Advanced block starts open when a deep link already uses one of its fields.
  const advancedIds = FILTER_IDS.filter(
    (id) => !['city', 'neighborhood', 'street'].includes(id)
  );
  if (advancedIds.some((id) => $(id).value !== '')) {
    $('toggle-advanced').click();
  }

  search();
}

init();
