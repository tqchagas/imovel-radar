const {
  $,
  el,
  fetchJson,
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatInteger,
  formatNumber,
  formatPct,
  deltaTag,
  mountChrome,
  navigate,
  propertyUrl,
} = window.IR;

const TYPE_LABELS = {
  AP: 'Apartamento',
  CS: 'Casa',
  LO: 'Loja / sala',
  GA: 'Garagem',
  TE: 'Terreno',
};

let city = '';
let board = null;
let buildingsWindow = 'all';

const addressLabel = (item) =>
  item.street_number ? `${item.street}, ${item.street_number}` : item.street;

const unitLabel = (unit) =>
  unit.complement ? `${addressLabel(unit)} — ${unit.complement}` : addressLabel(unit);

/** Units come back without a city; the board is city-scoped, so add it here. */
const unitUrl = (unit) => propertyUrl({ ...unit, city });

const buildingUrl = (item) => {
  const params = new URLSearchParams({ city, street: item.street });
  if (item.street_number) params.set('street_number', item.street_number);
  return `/busca?${params.toString()}`;
};

const neighborhoodUrl = (name) =>
  `/bairro?${new URLSearchParams({ city, neighborhood: name }).toString()}`;

/** Rows are the primary navigation on this page, so every one of them links. */
function linkedRow(url, cells) {
  const row = el('tr', 'clickable');
  cells.forEach((cell) => row.appendChild(cell));
  row.addEventListener('click', (event) => navigate(event, url));
  return row;
}

const cell = (text, className) => el('td', className, text);

const spanYears = (from, to) => {
  const years = Number(from.slice(0, 4));
  const until = Number(to.slice(0, 4));
  return years === until ? String(years) : `${years}–${until}`;
};

/** "748 dias" is unreadable; the story is "2 anos e 1 mês". */
function humanDays(days) {
  if (days < 31) return `${days} ${days === 1 ? 'dia' : 'dias'}`;
  const months = Math.round(days / 30.44);
  if (months < 24) return `${months} ${months === 1 ? 'mês' : 'meses'}`;
  return `${formatNumber(days / 365.25, 1)} anos`;
}

/* —— Recordes ————————————————————————————————— */

function renderRecords() {
  const sale = board.priciest_sales[0];
  const m2 = board.priciest_per_m2[0];
  const building = board.top_buildings[0];
  const unit = board.top_units[0];
  if (!sale) return;

  $('records-section').hidden = false;

  $('rec-value').textContent = formatCompactCurrency(sale.declared_value);
  $('rec-value-meta').textContent =
    `${unitLabel(sale.unit)} · ${formatDate(sale.settlement_date)}`;

  if (m2) {
    $('rec-m2').textContent = formatCurrency(m2.price_per_m2);
    $('rec-m2-meta').textContent =
      `${unitLabel(m2.unit)} · ${formatNumber(m2.built_area_acquired, 0)} m²`;
  }

  if (building) {
    $('rec-building').textContent = formatInteger(building.transaction_count);
    $('rec-building-meta').textContent =
      `quitações em ${addressLabel(building)} · ${building.neighborhood}`;
  }

  if (unit) {
    $('rec-unit').textContent = formatInteger(unit.transaction_count);
    $('rec-unit-meta').textContent =
      `vendas de ${unitLabel(unit.unit)} · ${spanYears(
        unit.first_settlement_date,
        unit.last_settlement_date
      )}`;
  }
}

/* —— Endereços ————————————————————————————————— */

function renderBuildings() {
  const items =
    buildingsWindow === 'all' ? board.top_buildings : board.top_buildings_recent;
  const tbody = $('buildings-body');
  tbody.innerHTML = '';

  if (!items.length) {
    const row = el('tr');
    const empty = el('td', 'empty-state', 'Sem endereços com duas ou mais quitações.');
    empty.colSpan = 7;
    row.appendChild(empty);
    tbody.appendChild(row);
    return;
  }

  items.forEach((item, index) => {
    tbody.appendChild(
      linkedRow(buildingUrl(item), [
        cell(String(index + 1), 'numeric'),
        cell(addressLabel(item), 'strong'),
        cell(item.neighborhood),
        cell(formatInteger(item.transaction_count), 'numeric strong'),
        cell(formatInteger(item.unit_count), 'numeric'),
        cell(formatCurrency(item.median_price_per_m2), 'numeric'),
        cell(formatDate(item.last_settlement_date), 'numeric'),
      ])
    );
  });
}

/* —— Unidades ————————————————————————————————— */

function renderUnits() {
  const tbody = $('units-body');
  tbody.innerHTML = '';

  board.top_units.forEach((item, index) => {
    tbody.appendChild(
      linkedRow(unitUrl(item.unit), [
        cell(String(index + 1), 'numeric'),
        cell(unitLabel(item.unit), 'strong'),
        cell(item.unit.neighborhood),
        cell(formatInteger(item.transaction_count), 'numeric strong'),
        cell(
          spanYears(item.first_settlement_date, item.last_settlement_date),
          'numeric'
        ),
        cell(formatCompactCurrency(item.last_value), 'numeric'),
      ])
    );
  });
}

/* —— Valorização ————————————————————————————— */

function renderAppreciation() {
  const tbody = $('appreciation-body');
  tbody.innerHTML = '';

  board.top_appreciation.forEach((item, index) => {
    const annual = el('td', 'numeric');
    annual.appendChild(deltaTag(item.annualized_pct));

    tbody.appendChild(
      linkedRow(unitUrl(item.unit), [
        cell(String(index + 1), 'numeric'),
        cell(unitLabel(item.unit), 'strong'),
        cell(formatCompactCurrency(item.from_value), 'numeric'),
        cell(formatCompactCurrency(item.to_value), 'numeric'),
        cell(`${formatNumber(item.years, 1)} anos`, 'numeric'),
        cell(formatPct(item.total_pct, 0), 'numeric strong'),
        annual,
      ])
    );
  });
}

/* —— Revendas ————————————————————————————————— */

function renderFlips() {
  const tbody = $('flips-body');
  tbody.innerHTML = '';

  board.fastest_flips.forEach((item, index) => {
    const delta = el('td', 'numeric');
    delta.appendChild(deltaTag(item.delta_pct));

    tbody.appendChild(
      linkedRow(unitUrl(item.unit), [
        cell(String(index + 1), 'numeric'),
        cell(unitLabel(item.unit), 'strong'),
        cell(humanDays(item.days), 'numeric strong'),
        cell(formatCompactCurrency(item.from_value), 'numeric'),
        cell(formatCompactCurrency(item.to_value), 'numeric'),
        delta,
      ])
    );
  });
}

/* —— Ritmo ————————————————————————————————— */

const MONTH_NAMES = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];

function renderRhythm() {
  const box = $('rhythm');
  box.innerHTML = '';
  if (!board.by_month.length) return;

  // Two hundred monthly bars are noise; the year is the readable unit, and the
  // peak month is called out in the note above it.
  const years = new Map();
  board.by_month.forEach((m) => {
    years.set(m.year, (years.get(m.year) || 0) + m.transaction_count);
  });

  const peak = board.by_month.reduce((best, m) =>
    m.transaction_count > best.transaction_count ? m : best
  );
  // The newest year stops at the last export, so its bar is not a collapse.
  const lastYear = board.by_month[board.by_month.length - 1].year;
  $('rhythm-note').textContent =
    `Quitações por ano na base. O mês mais movimentado foi ${
      MONTH_NAMES[peak.month - 1]
    } de ${peak.year}, com ${formatInteger(peak.transaction_count)}. ` +
    `${lastYear} está incompleto: a base vai até ${formatDate(board.reference_date)}.`;

  const top = Math.max(...years.values());
  [...years.entries()]
    .sort((a, b) => a[0] - b[0])
    .forEach(([year, count]) => {
      const row = el('div', 'bar-row');
      const head = el('div', 'bar-row-head');
      head.append(el('span', null, String(year)), el('b', null, formatInteger(count)));

      const track = el('div', 'bar-track');
      const fill = el('div', 'bar-fill');
      fill.style.width = `${Math.max(2, (count / top) * 100)}%`;
      track.appendChild(fill);

      row.append(head, track);
      box.appendChild(row);
    });
}

/* —— Bairros ————————————————————————————————— */

function renderMovers(id, items) {
  const box = $(id);
  box.innerHTML = '';

  if (!items.length) {
    box.appendChild(el('p', 'small', 'Sem bairros com quitações suficientes na janela.'));
    return;
  }

  items.forEach((item, index) => {
    const row = el('div', 'street-row clickable');
    const name = el('div', 'name');
    name.append(
      el('div', null, item.neighborhood),
      el('div', 'cell-sub', `${formatInteger(item.transaction_count)} quitações`)
    );
    row.append(
      el('div', 'pos', String(index + 1)),
      name,
      el('div', 'm2', formatCurrency(item.median_price_per_m2)),
      deltaTag(item.delta_pct)
    );
    row.addEventListener('click', (event) =>
      navigate(event, neighborhoodUrl(item.neighborhood))
    );
    box.appendChild(row);
  });
}

function renderSpread() {
  const box = $('spread');
  box.innerHTML = '';

  if (!board.widest_spread.length) {
    box.appendChild(el('p', 'small', 'Sem bairros com quitações suficientes na janela.'));
    return;
  }

  board.widest_spread.forEach((item, index) => {
    const row = el('div', 'street-row clickable');
    const name = el('div', 'name');
    name.append(
      el('div', null, item.neighborhood),
      el(
        'div',
        'cell-sub',
        `${formatCompactCurrency(item.p25_ticket)} → ${formatCompactCurrency(
          item.p75_ticket
        )} · mediana ${formatCompactCurrency(item.median_ticket)}`
      )
    );
    row.append(
      el('div', 'pos', String(index + 1)),
      name,
      el('div', 'm2', `${formatNumber(item.spread_ratio, 1)}×`),
      el('div', 'n', `${formatInteger(item.transaction_count)} quit.`)
    );
    row.addEventListener('click', (event) =>
      navigate(event, neighborhoodUrl(item.neighborhood))
    );
    box.appendChild(row);
  });
}

/* —— Carga ————————————————————————————————— */

function wireBuildingsToggle() {
  const buttons = { all: $('buildings-all'), recent: $('buildings-recent') };
  Object.entries(buttons).forEach(([key, button]) => {
    button.addEventListener('click', () => {
      buildingsWindow = key;
      Object.entries(buttons).forEach(([other, node]) =>
        node.setAttribute('aria-pressed', String(other === key))
      );
      renderBuildings();
    });
  });
}

async function init() {
  city = await mountChrome('curiosidades');
  wireBuildingsToggle();

  if (!city) {
    $('error').hidden = false;
    $('error').textContent = 'Nenhuma cidade com dados carregados.';
    return;
  }

  try {
    board = await fetchJson('/stats/curiosities', { city });
  } catch (error) {
    $('error').hidden = false;
    $('error').textContent = `Falha ao carregar: ${error.message}`;
    return;
  }

  if (!board.transaction_count) {
    $('error').hidden = false;
    $('error').textContent = 'Sem quitações carregadas para esta cidade.';
    return;
  }

  const firstYear = board.by_month[0]?.year;
  const lastYear = Number(board.reference_date.slice(0, 4));
  $('lede').textContent =
    `${formatInteger(board.transaction_count)} quitações de ITBI` +
    (firstYear ? `, de ${firstYear} a ${lastYear}` : '') +
    '. O que a base inteira mostra quando você para de procurar um imóvel e ' +
    'começa a olhar a cidade.';

  renderRecords();
  renderBuildings();
  renderUnits();
  renderAppreciation();
  renderFlips();
  renderRhythm();
  renderMovers('risers', board.risers);
  renderMovers('fallers', board.fallers);
  renderSpread();
}

init();
