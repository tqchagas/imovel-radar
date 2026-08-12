const {
  $,
  el,
  fetchJson,
  formatCurrency,
  formatDate,
  formatInteger,
  deltaTag,
  mountChrome,
} = window.IR;

function linkTo(href, label) {
  const link = el('a', 'small', label);
  link.href = href;
  return link;
}

/** "Rua Antônio de Albuquerque, 512" -> street + street_number. */
function splitQuery(raw) {
  const value = raw.trim();
  if (!value) return {};
  const match = value.match(/^(.*?)[,\s]+(\d+[A-Za-z]?)$/);
  if (match) return { street: match[1].trim(), street_number: match[2] };
  return { street: value };
}

function renderRanking(city, ranking) {
  const list = $('rank-list');
  list.innerHTML = '';

  if (!ranking.items.length) {
    list.append(
      el('p', 'small', 'Sem quitações suficientes nos últimos 12 meses.'),
      linkTo('/enviar', 'Enviar um CSV de ITBI →')
    );
    return;
  }

  ranking.items.slice(0, 4).forEach((item) => {
    const row = el('button', 'rank-row');
    row.type = 'button';

    const grow = el('div', 'grow');
    grow.append(
      el('div', 'name', item.neighborhood),
      el('div', 'sub', `${formatInteger(item.transaction_count)} quitações`)
    );

    row.append(
      grow,
      el('div', 'm2', formatCurrency(item.median_price_per_m2)),
      deltaTag(item.delta_pct)
    );

    row.addEventListener('click', () => {
      window.location.assign(window.IR.neighborhoodUrl(city, item.neighborhood));
    });
    list.appendChild(row);
  });
}

function renderOverview(overview) {
  $('stat-transactions').textContent = formatInteger(overview.transaction_count);
  $('stat-neighborhoods').textContent = formatInteger(overview.neighborhood_count);
  if (overview.city) {
    $('stat-neighborhoods-label').textContent =
      `bairros de ${window.IR.cityLabel(overview.city)} cobertos`;
  }

  const years = $('stat-years');
  years.textContent = '';
  if (overview.year_from && overview.year_to) {
    if (overview.year_from === overview.year_to) {
      years.textContent = String(overview.year_from);
    } else {
      years.append(
        document.createTextNode(String(overview.year_from)),
        el('span', 'dim', '—'),
        document.createTextNode(String(overview.year_to))
      );
    }
  } else {
    years.textContent = '—';
  }

  // The claim is "real settled deals"; the date of the last one is the proof.
  const freshness = $('data-freshness');
  if (overview.last_settlement_date) {
    freshness.hidden = false;
    freshness.textContent =
      `Última quitação registrada na base: ${formatDate(overview.last_settlement_date)}.`;
  }

  const browse = $('browse-link');
  if (overview.transaction_count) {
    browse.textContent = `navegue pelas ${formatInteger(overview.transaction_count)} quitações`;
  }
}

async function init() {
  // Legacy deep links (/?street=X) belong to the search screen now.
  if (window.location.search) {
    window.location.replace(`/busca${window.location.search}`);
    return;
  }

  const city = await mountChrome('home');

  $('hero-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const params = new URLSearchParams(splitQuery($('hero-query').value));
    if (city) params.set('city', city);
    window.location.assign(`/busca?${params.toString()}`);
  });

  try {
    const [overview, ranking] = await Promise.all([
      fetchJson('/stats/overview', { city }),
      fetchJson('/stats/neighborhoods', { city, months: 12, limit: 4 }),
    ]);
    renderOverview(overview);
    renderRanking(city, ranking);
    if (overview.neighborhood_count) {
      $('all-neighborhoods').textContent =
        `Ver todos os ${formatInteger(overview.neighborhood_count)} bairros →`;
    }
  } catch (error) {
    $('rank-list').innerHTML = '';
    $('rank-list').appendChild(el('p', 'small', `Falha ao carregar: ${error.message}`));
  }
}

init();
