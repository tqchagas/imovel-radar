const {
  $,
  el,
  chevron,
  emptyState,
  fetchJson,
  formatCurrency,
  formatCompactCurrency,
  formatDate,
  formatInteger,
  formatNumber,
  formatPct,
  cityLabel,
  deltaTag,
  mountChrome,
  navigate,
  propertyUrl,
  unslugCity,
  neighborhoodUrl,
  resolveNeighborhood,
} = window.IR;

let city = '';
let neighborhood = '';
let months = 12;

const searchUrl = (extra = {}) => {
  const params = new URLSearchParams({ city, ...extra });
  if (neighborhood) params.set('neighborhood', neighborhood);
  return `/busca?${params.toString()}`;
};

function readMonths() {
  const params = new URLSearchParams(window.location.search);
  const requested = parseInt(params.get('months') || '12', 10);
  months = [12, 24, 120].includes(requested) ? requested : 12;
  $('months').value = String(months);
}

function writeUrl() {
  const next =
    city && neighborhood ? neighborhoodUrl(city, neighborhood, { months }) : '/bairro';
  window.history.replaceState({}, '', next);
}

function showError(message, action) {
  const box = $('error');
  box.hidden = false;
  box.textContent = message;
  if (action) {
    const link = el('a', null, action.label);
    link.href = action.href;
    box.append(' ', link);
  }
}

/* —— Lista de bairros ————————————————————————————— */

function renderRanking(ranking) {
  $('ranking-view').hidden = false;
  $('detail-view').hidden = true;
  $('breadcrumb').hidden = true;
  $('see-transactions').hidden = true;
  $('neighborhood-name').textContent = 'Bairros';

  $('neighborhood-summary').textContent = ranking.items.length
    ? `${cityLabel(city)} · ${formatInteger(ranking.items.length)} bairros com quitações na janela, ordenados por R$/m² mediano.`
    : 'Sem bairros com quitações suficientes nesta janela.';

  const tbody = $('ranking-body');
  tbody.innerHTML = '';

  if (!ranking.items.length) {
    // The window is the filter here, so widening it is the move to offer.
    const actions = [];
    if (months !== 120) {
      actions.push({
        label: months === 12 ? 'Ampliar para 24 meses' : 'Ver a série completa',
        onClick: () => {
          months = months === 12 ? 24 : 120;
          $('months').value = String(months);
          writeUrl();
          load();
        },
      });
    }
    actions.push({ label: 'Enviar dados', href: '/enviar' });

    const row = el('tr');
    const cell = el('td');
    cell.colSpan = 5;
    cell.appendChild(
      emptyState(
        'Nenhum bairro com quitações suficientes nesta janela.',
        'O ranking só usa bairros com área declarada suficiente para um R$/m² ' +
          'mediano confiável. Uma janela maior costuma resolver.',
        actions
      )
    );
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  ranking.items.forEach((item, index) => {
    const row = el('tr', 'clickable');
    row.append(
      el('td', 'numeric', String(index + 1)),
      el('td', 'strong', item.neighborhood),
      el('td', 'numeric', formatInteger(item.transaction_count)),
      el('td', 'numeric', formatCurrency(item.median_price_per_m2))
    );
    const delta = el('td', 'numeric');
    delta.appendChild(deltaTag(item.delta_pct));
    row.appendChild(delta);

    row.addEventListener('click', () => {
      neighborhood = item.neighborhood;
      writeUrl();
      load();
    });
    tbody.appendChild(row);
  });
}

/* —— Detalhe do bairro ————————————————————————————— */

function renderDetail(detail, recent) {
  $('ranking-view').hidden = true;
  $('detail-view').hidden = false;
  $('breadcrumb').hidden = false;
  $('see-transactions').hidden = false;
  $('neighborhood-name').textContent = detail.neighborhood;
  document.title = `ImovelRadar — ${detail.neighborhood}`;

  const share =
    detail.residential_share_pct != null
      ? `, das quais ${formatNumber(detail.residential_share_pct, 0)}% residenciais`
      : '';
  const window_ = months >= 120 ? 'na série completa' : `nos últimos ${months} meses`;
  $('neighborhood-summary').textContent =
    `${cityLabel(city)}. ${formatInteger(detail.transaction_count)} quitações ${window_}${share}.`;

  $('stat-m2').textContent = formatCurrency(detail.median_price_per_m2);
  const delta = $('stat-m2-delta');
  delta.textContent =
    detail.delta_pct != null
      ? `${formatPct(detail.delta_pct)} vs. janela anterior`
      : 'sem janela anterior para comparar';
  delta.classList.toggle('alta', (detail.delta_pct ?? 0) > 0);

  $('stat-ticket').textContent = formatCompactCurrency(detail.median_ticket);
  $('stat-ticket-range').textContent =
    detail.p25_ticket != null && detail.p75_ticket != null
      ? `P25 ${formatCompactCurrency(detail.p25_ticket)} · P75 ${formatCompactCurrency(detail.p75_ticket)}`
      : '';

  $('stat-area').textContent =
    detail.median_area != null ? `${formatNumber(detail.median_area, 0)} m²` : '—';
  $('stat-liquidity').textContent =
    detail.per_month != null ? `${formatNumber(detail.per_month, 0)} / mês` : '—';

  renderByType(detail.by_construction_type);
  renderStreets(detail.top_streets);
  renderRecent(recent.items);

  $('all-transactions').href = searchUrl();
  $('all-transactions').textContent = `Ver todas as ${formatInteger(recent.total)} →`;
}

function renderByType(types) {
  const box = $('by-type');
  box.innerHTML = '';
  const withPrice = types.filter((t) => t.median_price_per_m2 != null);

  if (!withPrice.length) {
    box.appendChild(el('p', 'small', 'Sem área declarada suficiente para calcular R$/m².'));
    return;
  }

  const top = withPrice[0].median_price_per_m2;
  withPrice.forEach((type) => {
    const row = el('div', 'bar-row');
    const head = el('div', 'bar-row-head');
    head.append(
      el('span', null, `${type.label} · ${formatInteger(type.transaction_count)}`),
      el('b', null, formatCurrency(type.median_price_per_m2))
    );

    const track = el('div', 'bar-track');
    const fill = el('div', 'bar-fill');
    fill.style.width = `${Math.max(4, (type.median_price_per_m2 / top) * 100)}%`;
    track.appendChild(fill);

    row.append(head, track);
    box.appendChild(row);
  });
}

function renderStreets(streets) {
  const box = $('top-streets');
  box.innerHTML = '';

  if (!streets.length) {
    box.appendChild(el('p', 'small', 'Nenhuma rua com quitações suficientes na janela.'));
    return;
  }

  streets.forEach((street, index) => {
    const row = el('div', 'street-row');
    row.append(
      el('div', 'pos', String(index + 1)),
      el('div', 'name', street.street),
      el('div', 'm2', formatCurrency(street.median_price_per_m2)),
      el('div', 'n', `${formatInteger(street.transaction_count)} quit.`)
    );
    box.appendChild(row);
  });
}

function renderRecent(items) {
  const tbody = $('recent-body');
  tbody.innerHTML = '';

  items.forEach((item) => {
    const m2 =
      item.built_area_acquired && item.built_area_acquired > 0
        ? item.declared_value / item.built_area_acquired
        : null;

    const row = el('tr', 'clickable');
    const address = el('td');
    address.append(
      el('span', 'cell-title', item.street_number ? `${item.street}, ${item.street_number}` : item.street),
      document.createTextNode(' '),
      el('span', 'cell-sub', item.complement || '')
    );

    row.append(
      el('td', 'numeric', formatDate(item.settlement_date)),
      address,
      el('td', 'numeric', formatNumber(item.built_area_acquired)),
      el('td', 'numeric strong', formatCurrency(item.declared_value)),
      el('td', 'numeric', formatCurrency(m2))
    );
    row.addEventListener('click', (event) => navigate(event, propertyUrl(item)));
    tbody.appendChild(row);
  });
}

/* —— Carga ————————————————————————————————— */

async function load() {
  $('error').hidden = true;

  try {
    if (!neighborhood) {
      const ranking = await fetchJson('/stats/neighborhoods', {
        city,
        months,
        limit: 500,
        min_transactions: 3,
      });
      renderRanking(ranking);
      return;
    }

    const [detail, recent] = await Promise.all([
      fetchJson(`/stats/neighborhoods/${encodeURIComponent(neighborhood)}`, { city, months }),
      fetchJson('/transactions', { city, neighborhood, limit: 8 }),
    ]);
    renderDetail(detail, recent);
  } catch (error) {
    $('ranking-view').hidden = true;
    $('detail-view').hidden = true;
    showError(error.message || 'Falha ao carregar o bairro.');
  }
}

async function init() {
  document.querySelectorAll('.select-wrap').forEach((wrap) => wrap.appendChild(chevron()));

  const defaultCity = await mountChrome('bairro');
  const params = new URLSearchParams(window.location.search);
  const path = window.location.pathname.match(/^\/bairro\/([^/]+)\/([^/]+)\/?$/);
  city = params.get('city') || (path ? unslugCity(path[1]) : '') || defaultCity;
  readMonths();
  if (params.get('neighborhood')) {
    neighborhood = params.get('neighborhood');
  } else if (path) {
    neighborhood = await resolveNeighborhood(city, path[2]);
  }
  writeUrl();

  $('months').addEventListener('change', () => {
    months = parseInt($('months').value, 10);
    writeUrl();
    load();
  });

  $('see-transactions').addEventListener('click', () => {
    window.location.assign(searchUrl());
  });

  if (!city) {
    showError('Nenhuma cidade com dados carregados.', {
      href: '/enviar',
      label: 'Enviar um CSV de ITBI →',
    });
    return;
  }

  if (path && !neighborhood) {
    showError('Bairro não encontrado.', { href: '/bairro', label: 'Ver todos os bairros →' });
    return;
  }

  load();
}

init();
