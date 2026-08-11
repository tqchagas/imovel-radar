const API_BASE = window.location.origin;

const $ = (id) => document.getElementById(id);

const formatCurrency = (value) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL',
        maximumFractionDigits: 0,
      }).format(value);

const formatDate = (value) =>
  value ? new Intl.DateTimeFormat('pt-BR').format(new Date(value + 'T12:00:00')) : '—';

const formatNumber = (value, digits = 2) =>
  value != null
    ? new Intl.NumberFormat('pt-BR', { maximumFractionDigits: digits }).format(value)
    : '—';

const formatPct = (value) => {
  if (value == null || Number.isNaN(value)) return 'Indisponível';
  const sign = value > 0 ? '+' : '';
  return `${sign}${formatNumber(value, 1)}%`;
};

const MARKER_LABELS = {
  cota_parcial: 'Cota parcial',
  area_divergente: 'Área divergente',
  base_divergente: 'Base ≠ declarado',
};

function cityLabel(city) {
  return (city || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function buildCanonicalUrl(data) {
  const params = new URLSearchParams();
  params.set('city', data.city);
  params.set('street', data.street);
  if (data.street_number) params.set('street_number', data.street_number);
  if (data.complement) params.set('complement', data.complement);
  return `/imovel?${params.toString()}`;
}

async function fetchJson(path, params = {}) {
  const url = new URL(path, API_BASE);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  });
  const response = await fetch(url);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Erro ${response.status}`);
  }
  return response.json();
}

function renderHeader(data) {
  const unit = data.complement
    ? `${data.street}, ${data.street_number ?? 's/n'} — ${data.complement}`
    : `${data.street}, ${data.street_number ?? 's/n'}`;
  $('property-title').textContent = unit;
  const norm = data.complement_normalized
    ? ` · chave ${data.complement_normalized}`
    : '';
  $('property-subtitle').textContent = `${cityLabel(data.city)}${norm}`;
  document.title = `ImovelRadar — ${unit}`;
}

function renderSummary(summary) {
  $('summary-section').hidden = false;
  $('sum-last-sale').textContent = formatCurrency(summary.last_sale_value);
  $('sum-last-date').textContent = formatDate(summary.last_sale_date);
  $('sum-appreciation').textContent = formatPct(summary.appreciation_pct);
  $('sum-m2').textContent =
    summary.last_price_per_m2 != null
      ? `${formatCurrency(summary.last_price_per_m2)}/m²`
      : '—';
  $('sum-m2-delta').textContent =
    summary.price_per_m2_delta_pct != null
      ? `Δ R$/m² ${formatPct(summary.price_per_m2_delta_pct)}`
      : '';
  $('sum-count').textContent = String(summary.transaction_count);
  if (summary.year_from && summary.year_to) {
    $('sum-years').textContent =
      summary.year_from === summary.year_to
        ? String(summary.year_from)
        : `${summary.year_from}–${summary.year_to}`;
  } else {
    $('sum-years').textContent = '';
  }
}

function renderTimeline(timeline) {
  const root = $('timeline');
  root.innerHTML = '';
  $('timeline-section').hidden = false;

  if (!timeline.length) {
    root.innerHTML = '<p class="muted">Nenhuma quitação neste imóvel.</p>';
    return;
  }

  const values = timeline.map((p) => p.declared_value);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const span = Math.max(maxV - minV, 1);
  const minH = 12;
  const maxH = 100;

  const track = document.createElement('div');
  track.className = 'timeline-track';

  timeline.forEach((point) => {
    const height = minH + ((point.declared_value - minV) / span) * (maxH - minH);
    const el = document.createElement('div');
    el.className = 'timeline-point';
    if (point.is_partial) el.classList.add('partial');
    if (point.area_divergent) el.classList.add('divergent');

    const bar = document.createElement('div');
    bar.className = 'timeline-bar';
    bar.style.height = `${height}px`;

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

    const label = document.createElement('div');
    label.className = 'timeline-label';
    label.innerHTML = `<strong>${formatCurrency(point.declared_value)}</strong><br>${formatDate(point.settlement_date)}`;

    el.appendChild(bar);
    el.appendChild(label);
    track.appendChild(el);
  });

  root.appendChild(track);
}

function renderHistory(data) {
  $('history-section').hidden = false;
  const tbody = $('history-body');
  tbody.innerHTML = '';

  const byId = new Map(data.timeline.map((p) => [p.transaction_id, p]));

  data.transactions.forEach((item) => {
    const point = byId.get(item.id);
    const markers = (point?.markers || [])
      .map((m) => MARKER_LABELS[m] || m)
      .join(', ');
    const m2 =
      item.built_area_acquired && item.built_area_acquired > 0
        ? item.declared_value / item.built_area_acquired
        : null;

    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${formatDate(item.settlement_date)}</td>
      <td>${item.complement ?? '—'}</td>
      <td class="numeric">${formatNumber(item.built_area_acquired)}</td>
      <td class="numeric">${formatCurrency(item.declared_value)}</td>
      <td class="numeric">${formatCurrency(item.calc_base_value)}</td>
      <td class="numeric">${m2 != null ? formatCurrency(m2) : '—'}</td>
      <td>${item.acquired_fraction != null ? formatNumber(item.acquired_fraction, 5) : '—'}</td>
      <td>${markers || '—'}</td>
    `;
    tbody.appendChild(row);
  });
}

function showError(message) {
  const el = $('property-error');
  el.hidden = false;
  el.textContent = message;
  $('property-title').textContent = 'Imóvel não encontrado';
}

async function loadProperty() {
  const params = new URLSearchParams(window.location.search);
  const transactionId = params.get('transaction_id') || params.get('from_transaction');

  try {
    let data;
    if (transactionId) {
      data = await fetchJson(`/properties/by-transaction/${transactionId}`);
      const canonical = buildCanonicalUrl(data);
      window.history.replaceState({}, '', canonical);
    } else {
      const city = params.get('city');
      const street = params.get('street');
      if (!city || !street) {
        showError('Informe city e street na URL, ou transaction_id.');
        return;
      }
      data = await fetchJson('/properties', {
        city,
        street,
        street_number: params.get('street_number'),
        complement: params.get('complement'),
      });
    }

    renderHeader(data);
    renderSummary(data.summary);
    renderTimeline(data.timeline);
    renderHistory(data);
  } catch (error) {
    showError(error.message || 'Falha ao carregar o imóvel.');
  }
}

loadProperty();
