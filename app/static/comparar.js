const {
  $,
  el,
  emptyState,
  fetchJson,
  formatCurrency,
  formatDate,
  formatInteger,
  formatNumber,
  formatPct,
  mountChrome,
  propertyUrl,
  compareKeyOf,
  readCompare,
  removeFromCompare,
  COMPARE_LIMIT,
} = window.IR;

const TYPE_LABELS = {
  AP: 'Apartamento',
  CS: 'Casa',
  LO: 'Loja / sala',
  GA: 'Garagem',
  TE: 'Terreno',
};

let medians = new Map();

const latest = (property) => property.transactions[0] || null;

const pricePerM2 = (tx) =>
  tx && tx.built_area_acquired > 0 ? tx.declared_value / tx.built_area_acquired : null;

/** Compound annual growth between the first and last full sale. */
function annualized(summary) {
  if (
    summary.appreciation_pct == null ||
    !summary.year_from ||
    !summary.year_to ||
    summary.year_to <= summary.year_from
  ) {
    return null;
  }
  const years = summary.year_to - summary.year_from;
  return ((1 + summary.appreciation_pct / 100) ** (1 / years) - 1) * 100;
}

function vsNeighborhood(property) {
  const tx = latest(property);
  const median = tx ? medians.get(tx.neighborhood) : null;
  const m2 = pricePerM2(tx);
  if (!median || m2 == null) return null;
  return (m2 / median - 1) * 100;
}

const ROWS = [
  ['Última venda', (p) => formatCurrency(p.summary.last_sale_value)],
  ['Data', (p) => formatDate(p.summary.last_sale_date)],
  [
    'Área construída',
    (p) => {
      const tx = latest(p);
      return tx?.built_area_acquired ? `${formatNumber(tx.built_area_acquired)} m²` : '—';
    },
  ],
  ['R$/m²', (p) => formatCurrency(pricePerM2(latest(p)))],
  ['vs. mediana do bairro', (p) => formatPct(vsNeighborhood(p))],
  [
    'Quitações registradas',
    (p) => {
      const years =
        p.summary.year_from && p.summary.year_to && p.summary.year_from !== p.summary.year_to
          ? ` · ${p.summary.year_from}–${p.summary.year_to}`
          : '';
      return `${formatInteger(p.summary.transaction_count)}${years}`;
    },
  ],
  ['Valorização total', (p) => formatPct(p.summary.appreciation_pct)],
  [
    'Valorização anualizada',
    (p) => {
      const rate = annualized(p.summary);
      return rate == null ? '—' : `${formatPct(rate)} a.a.`;
    },
  ],
  ['Bairro', (p) => latest(p)?.neighborhood || '—'],
  ['Ano de construção', (p) => latest(p)?.construction_year ?? '—'],
];

function renderEmpty() {
  const root = $('compare-root');
  root.innerHTML = '';
  // The empty state already says how to fill the list; the intro would repeat it.
  $('compare-intro').hidden = true;
  const panel = el('div', 'panel');
  panel.appendChild(
    emptyState(
      `Nenhum imóvel no comparativo (0 de ${COMPARE_LIMIT})`,
      'Abra o histórico de uma unidade na busca e use "Adicionar ao comparativo". ' +
        'A lista fica salva neste navegador.',
      [
        { label: 'Ir para a busca', href: '/busca' },
        { label: 'Ver ranking de bairros', href: '/bairro' },
      ]
    )
  );
  root.append(panel);
}

function renderCards(grid, properties, entries) {
  properties.forEach((property, index) => {
    const card = el('div', 'compare-card');

    const top = el('div', 'compare-card-top');
    const tx = latest(property);
    top.appendChild(
      el('span', 'tag', TYPE_LABELS[tx?.construction_type] || tx?.construction_type || '—')
    );

    const remove = el('button', 'compare-remove', '✕');
    remove.type = 'button';
    remove.title = 'Remover do comparativo';
    remove.addEventListener('click', () => {
      removeFromCompare(compareKeyOf(entries[index]));
      load();
    });
    top.appendChild(remove);

    const address = el('a', 'address', property.street_number
      ? `${property.street}, ${property.street_number}`
      : property.street);
    address.href = propertyUrl(property);
    address.style.textDecoration = 'none';
    address.style.color = 'inherit';

    card.append(
      top,
      address,
      el(
        'div',
        'sub',
        `${property.complement || 'sem complemento'} · ${tx?.neighborhood || '—'}`
      )
    );
    grid.appendChild(card);
  });

  for (let i = properties.length; i < COMPARE_LIMIT; i += 1) {
    grid.appendChild(el('div'));
  }

  const empty = el('a', 'compare-empty');
  empty.href = '/busca';
  const plus = el('span', 'plus');
  plus.innerHTML =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#8c491a" stroke-width="2.75" stroke-linecap="round"><path d="M5 12h14"></path><path d="M12 5v14"></path></svg>';
  empty.append(
    plus,
    el(
      'span',
      'hint',
      properties.length >= COMPARE_LIMIT
        ? 'Remova um imóvel para trocar a comparação'
        : 'Adicionar outro imóvel pela busca'
    )
  );
  grid.appendChild(empty);
}

function renderRows(grid, properties) {
  ROWS.forEach(([label, value]) => {
    grid.appendChild(el('div', 'compare-label', label));
    for (let i = 0; i < COMPARE_LIMIT; i += 1) {
      const property = properties[i];
      grid.appendChild(el('div', 'compare-cell', property ? String(value(property)) : '—'));
    }
    grid.appendChild(el('div'));
  });
}

async function loadMedians(cities) {
  const rankings = await Promise.all(
    [...cities].map((city) =>
      fetchJson('/stats/neighborhoods', {
        city,
        months: 12,
        limit: 500,
        min_transactions: 3,
      }).catch(() => ({ items: [] }))
    )
  );
  medians = new Map(
    rankings
      .flatMap((r) => r.items)
      .filter((i) => i.median_price_per_m2 != null)
      .map((i) => [i.neighborhood, i.median_price_per_m2])
  );
}

async function load() {
  const entries = readCompare();
  if (!entries.length) {
    renderEmpty();
    return;
  }

  const root = $('compare-root');
  root.innerHTML = '';
  $('compare-intro').hidden = false;

  const settled = await Promise.all(
    entries.map((entry) =>
      fetchJson('/properties', {
        city: entry.city,
        street: entry.street,
        street_number: entry.street_number,
        complement: entry.complement,
      })
        .then((data) => ({ entry, data }))
        .catch(() => ({ entry, data: null }))
    )
  );

  const missing = settled.filter((s) => !s.data);
  const loaded = settled.filter((s) => s.data);

  await loadMedians(new Set(loaded.map((s) => s.data.city)));

  const grid = el('div', 'compare-grid');
  grid.appendChild(el('div'));
  renderCards(
    grid,
    loaded.map((s) => s.data),
    loaded.map((s) => s.entry)
  );
  renderRows(
    grid,
    loaded.map((s) => s.data)
  );
  root.appendChild(grid);

  if (missing.length) {
    const warning = el(
      'p',
      'status error',
      `${missing.length} imóvel(is) do comparativo não foi(ram) encontrado(s) na base atual.`
    );
    root.appendChild(warning);
  }
}

async function init() {
  await mountChrome('comparar');
  load();
}

init();
