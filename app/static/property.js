const {
  $,
  el,
  emptyState,
  fetchJson,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPct,
  cityLabel,
  mountChrome,
  addToCompare,
  propertyUrl,
  parsePropertyPath,
} = window.IR;

const MARKER_LABELS = {
  cota_parcial: 'Cota parcial',
  area_divergente: 'Área divergente',
  base_divergente: 'Base ≠ declarado',
};

const BAR_MIN = 12;
const BAR_MAX = 160;

let property = null;

function requestedKey() {
  const fromPath = parsePropertyPath(window.location.pathname);
  const params = new URLSearchParams(window.location.search);
  return {
    city: params.get('city') || fromPath?.city || '',
    street: params.get('street') || fromPath?.street || '',
    street_number: params.get('street_number') || fromPath?.street_number || '',
    complement: params.get('complement') || fromPath?.complement || '',
  };
}

const unitLabel = (data) =>
  data.complement
    ? `${data.street}, ${data.street_number ?? 's/n'} — ${data.complement}`
    : `${data.street}, ${data.street_number ?? 's/n'}`;

function renderHeader(data) {
  const unit = unitLabel(data);
  $('property-title').textContent = unit;
  document.title = `ImovelRadar — ${unit}`;
  $('property-eyebrow').textContent = cityLabel(data.city);

  if (data.complement_normalized) {
    const key = $('property-key');
    key.hidden = false;
    key.textContent = `chave ${data.complement_normalized}`;
  }

  const scope = $('property-scope');
  scope.hidden = false;
  scope.textContent = data.complement
    ? `Histórico só desta unidade (${data.complement_normalized || data.complement}) — não inclui outros apartamentos do mesmo prédio.`
    : 'Histórico do lote/número (registros sem complemento). Outras unidades do prédio não entram aqui.';
}

function renderSummary(summary) {
  $('summary-section').hidden = false;
  $('sum-last-sale').textContent = formatCurrency(summary.last_sale_value);
  $('sum-last-date').textContent = formatDate(summary.last_sale_date);

  const appreciation = $('sum-appreciation');
  appreciation.textContent = formatPct(summary.appreciation_pct);
  appreciation.classList.toggle('alta', (summary.appreciation_pct ?? 0) > 0);

  const years =
    summary.year_from && summary.year_to && summary.year_from !== summary.year_to
      ? `${summary.year_from}–${summary.year_to}`
      : String(summary.year_from ?? '');
  $('sum-appreciation-meta').textContent = years
    ? `entre vendas plenas · ${years}`
    : 'entre vendas plenas';

  $('sum-m2').textContent =
    summary.last_price_per_m2 != null ? `${formatCurrency(summary.last_price_per_m2)}` : '—';
  $('sum-m2-delta').textContent =
    summary.price_per_m2_delta_pct != null
      ? `Δ R$/m² ${formatPct(summary.price_per_m2_delta_pct)}`
      : '';

  $('sum-count').textContent = String(summary.transaction_count);
  $('sum-years').textContent = years;
}

function pointNote(point) {
  if (point.is_partial) return 'cota parcial';
  if (point.area_divergent) return 'área divergente';
  return 'venda plena';
}

function renderTimeline(timeline) {
  const track = $('timeline');
  const axis = $('timeline-axis');
  track.innerHTML = '';
  axis.innerHTML = '';
  $('timeline-section').hidden = false;

  if (!timeline.length) {
    // A unit with no settlement is the one case where the building around it
    // is the answer — offer it instead of a dead end.
    const params = new URLSearchParams({ city: property.city, street: property.street });
    if (property.street_number) params.set('street_number', property.street_number);
    track.appendChild(
      emptyState(
        'Nenhuma quitação nesta unidade.',
        'Sem ITBI quitado, não há preço a mostrar. Outras unidades do mesmo ' +
          'endereço podem ter — elas dão a referência mais próxima.',
        [{ label: 'Ver o endereço inteiro', href: `/busca?${params.toString()}` }]
      )
    );
    return;
  }

  const values = timeline.map((p) => p.declared_value);
  const min = Math.min(...values);
  const span = Math.max(Math.max(...values) - min, 1);

  timeline.forEach((point) => {
    const item = el('div', 'timeline-point');
    if (point.is_partial) item.classList.add('partial');
    if (point.area_divergent) item.classList.add('divergent');

    const bar = el('div', 'timeline-bar');
    bar.style.height = `${BAR_MIN + ((point.declared_value - min) / span) * (BAR_MAX - BAR_MIN)}px`;

    const markers = point.markers.map((m) => MARKER_LABELS[m] || m).join(' · ');
    const gap =
      point.calc_base_gap_pct != null
        ? ` (gap ${formatNumber(point.calc_base_gap_pct, 1)}%)`
        : '';
    bar.title = [
      formatDate(point.settlement_date),
      `Declarado: ${formatCurrency(point.declared_value)}`,
      `Base cálculo: ${formatCurrency(point.calc_base_value)}${gap}`,
      point.price_per_m2 != null ? `R$/m²: ${formatCurrency(point.price_per_m2)}` : null,
      markers || null,
    ]
      .filter(Boolean)
      .join('\n');

    item.append(el('div', 'timeline-value', formatCurrency(point.declared_value)), bar);
    track.appendChild(item);

    const tick = el('div');
    tick.append(
      el('div', 'timeline-date', formatDate(point.settlement_date)),
      el('div', 'timeline-note', pointNote(point))
    );
    axis.appendChild(tick);
  });
}

function renderHistory(data) {
  $('history-section').hidden = false;
  const tbody = $('history-body');
  tbody.innerHTML = '';

  const byId = new Map(data.timeline.map((p) => [p.transaction_id, p]));

  data.transactions.forEach((item) => {
    const point = byId.get(item.id);
    const markers = (point?.markers || []).map((m) => MARKER_LABELS[m] || m);
    const m2 =
      item.built_area_acquired && item.built_area_acquired > 0
        ? item.declared_value / item.built_area_acquired
        : null;

    const row = el('tr');
    row.append(
      el('td', 'numeric', formatDate(item.settlement_date)),
      el('td', null, item.complement ?? '—'),
      el('td', 'numeric', formatNumber(item.built_area_acquired)),
      el('td', 'numeric strong', formatCurrency(item.declared_value)),
      el('td', 'numeric', formatCurrency(item.calc_base_value)),
      el('td', 'numeric', m2 != null ? formatCurrency(m2) : '—'),
      el(
        'td',
        'numeric',
        item.acquired_fraction != null ? formatNumber(item.acquired_fraction, 5) : '—'
      )
    );

    const alerts = el('td');
    if (markers.length) {
      markers.forEach((label) => alerts.appendChild(el('span', 'tag tag-salvia', label)));
    } else {
      alerts.appendChild(el('span', 'dash', '—'));
    }
    row.appendChild(alerts);
    tbody.appendChild(row);
  });
}

/** Raw API text is a dead end; the address the user already typed is the
    nearest thing we can still answer, so the error screen offers it. */
function fallbackActions() {
  const key = requestedKey();
  if (!key.city || !key.street) return [{ label: 'Ir para a busca', href: '/busca' }];

  const search = new URLSearchParams({ city: key.city, street: key.street });
  if (key.street_number) search.set('street_number', key.street_number);
  return [
    {
      label: key.street_number ? 'Ver o endereço inteiro' : 'Ver a rua inteira',
      href: `/busca?${search}`,
    },
    { label: 'Nova busca', href: '/busca' },
  ];
}

function showError(message) {
  const box = $('property-error');
  box.hidden = false;
  box.textContent = '';
  box.appendChild(
    emptyState(
      'Nenhuma quitação registrada para esta unidade.',
      message === 'Property not found'
        ? 'O complemento pode estar escrito de outro jeito, ou a unidade nunca ' +
          'teve ITBI quitado na base.'
        : message,
      fallbackActions()
    )
  );
  // Echo back what was asked for: it confirms the query and kills the
  // duplicate "not found" heading over a "not found" body.
  const key = requestedKey();
  $('property-title').textContent = key.street
    ? unitLabel({
        street: key.street.replace(/-/g, ' ').toUpperCase(),
        street_number: key.street_number,
        complement: key.complement.replace(/-/g, ' ').toUpperCase(),
      })
    : 'Imóvel não encontrado';
  document.querySelector('.property-actions').hidden = true;
}

function wireActions() {
  $('copy-link').addEventListener('click', async () => {
    const button = $('copy-link');
    try {
      await navigator.clipboard.writeText(window.location.href);
      button.textContent = 'Link copiado';
    } catch {
      button.textContent = 'Copie da barra de endereço';
    }
    window.setTimeout(() => {
      button.textContent = 'Copiar link';
    }, 2000);
  });

  $('add-compare').addEventListener('click', () => {
    if (!property) return;
    const button = $('add-compare');
    const result = addToCompare({
      city: property.city,
      street: property.street,
      street_number: property.street_number,
      complement: property.complement,
      label: unitLabel(property),
    });
    button.textContent = {
      added: 'Adicionado ✓',
      duplicate: 'Já está no comparativo',
      full: `Comparativo cheio (${window.IR.COMPARE_LIMIT})`,
    }[result];
    window.setTimeout(() => {
      button.textContent = 'Adicionar ao comparativo';
    }, 2000);
  });
}

async function loadProperty() {
  const params = new URLSearchParams(window.location.search);
  const transactionId = params.get('transaction_id') || params.get('from_transaction');
  const key = requestedKey();

  try {
    let data;
    if (transactionId) {
      data = await fetchJson(`/properties/by-transaction/${transactionId}`);
    } else {
      if (!key.city || !key.street) {
        showError('Informe o endereço na URL, ou transaction_id.');
        return;
      }
      data = await fetchJson('/properties', {
        city: key.city,
        street: key.street,
        street_number: key.street_number || undefined,
        complement: key.complement || undefined,
      });
    }

    property = data;
    window.history.replaceState({}, '', propertyUrl(data));
    renderHeader(data);
    renderSummary(data.summary);
    renderTimeline(data.timeline);
    renderHistory(data);
  } catch (error) {
    showError(error.message || 'Falha ao carregar o imóvel.');
  }
}

async function init() {
  await mountChrome('busca');
  wireActions();
  await loadProperty();
}

init();
