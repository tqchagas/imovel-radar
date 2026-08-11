/* Shared chrome, formatters and cross-page state for ImovelRadar.
   Wrapped in an IIFE: page scripts destructure these names from window.IR,
   and top-level `const`s here would collide with those declarations. */

(() => {
const API_BASE = window.location.origin;
const COMPARE_KEY = 'imovelradar:comparar';
const COMPARE_LIMIT = 3;
const CITY_KEY = 'imovelradar:cidade';

const $ = (id) => document.getElementById(id);

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
};

const formatCurrency = (value, digits = 0) =>
  value == null || Number.isNaN(value)
    ? '—'
    : new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL',
        maximumFractionDigits: digits,
      }).format(value);

const formatCompactCurrency = (value) => {
  if (value == null || Number.isNaN(value)) return '—';
  if (value >= 1e6) return `R$ ${formatNumber(value / 1e6, 2)} mi`;
  if (value >= 1e5) return `R$ ${formatNumber(value / 1e3, 0)} mil`;
  return formatCurrency(value);
};

const formatDate = (value) =>
  value ? new Intl.DateTimeFormat('pt-BR').format(new Date(`${value}T12:00:00`)) : '—';

const formatNumber = (value, digits = 2) =>
  value != null && !Number.isNaN(value)
    ? new Intl.NumberFormat('pt-BR', { maximumFractionDigits: digits }).format(value)
    : '—';

const formatInteger = (value) => formatNumber(value, 0);

const formatPct = (value, digits = 1) => {
  if (value == null || Number.isNaN(value)) return '—';
  // Minus sign (U+2212) reads better than the hyphen next to tabular digits.
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${formatNumber(Math.abs(value), digits)}%`;
};

const cityLabel = (city) =>
  (city || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();

async function fetchJson(path, params = {}) {
  const url = new URL(path, API_BASE);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  });
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Erro ${response.status}`);
  }
  return response.json();
}

/** Delta pill: sálvia when up, terracota when down, dash when unknown. */
function deltaTag(pct) {
  if (pct == null || Number.isNaN(pct)) return el('span', 'dash', '—');
  const tag = el('span', 'tag tag-delta', formatPct(pct));
  tag.classList.add(pct >= 0 ? 'tag-salvia' : 'tag-terracota');
  return tag;
}

/** Empty state that points somewhere: a screen with nothing to do ends the
    session, so every "no results" carries the next move. */
function emptyState(title, hint, actions = []) {
  const box = el('div', 'empty-state');
  box.appendChild(el('p', 'empty-title', title));
  if (hint) box.appendChild(el('p', 'empty-hint', hint));
  if (actions.length) {
    const row = el('div', 'empty-actions');
    actions.forEach((action, index) => {
      const cls = index === 0 ? 'btn btn-sm' : 'btn btn-secondary btn-sm';
      if (action.href) {
        const link = el('a', cls, action.label);
        link.href = action.href;
        row.appendChild(link);
      } else {
        const button = el('button', cls, action.label);
        button.type = 'button';
        button.addEventListener('click', action.onClick);
        row.appendChild(button);
      }
    });
    box.appendChild(row);
  }
  return box;
}

/* —— Cidade corrente ————————————————————————————— */

const getCity = () => window.localStorage.getItem(CITY_KEY) || '';

const setCity = (city) => {
  if (city) window.localStorage.setItem(CITY_KEY, city);
  else window.localStorage.removeItem(CITY_KEY);
};

async function resolveCity() {
  const stored = getCity();
  if (stored) return stored;
  const cities = await fetchJson('/cities').catch(() => []);
  if (cities.length) {
    setCity(cities[0]);
    return cities[0];
  }
  return '';
}

/* —— Comparativo (só no cliente) ————————————————————— */

const compareKeyOf = (item) =>
  [item.city, item.street, item.street_number || '', item.complement || ''].join('|');

function readCompare() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(COMPARE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.slice(0, COMPARE_LIMIT) : [];
  } catch {
    return [];
  }
}

function writeCompare(items) {
  window.localStorage.setItem(COMPARE_KEY, JSON.stringify(items.slice(0, COMPARE_LIMIT)));
}

/** Returns 'added' | 'duplicate' | 'full'. */
function addToCompare(item) {
  const items = readCompare();
  if (items.some((i) => compareKeyOf(i) === compareKeyOf(item))) return 'duplicate';
  if (items.length >= COMPARE_LIMIT) return 'full';
  writeCompare([...items, item]);
  return 'added';
}

function removeFromCompare(key) {
  writeCompare(readCompare().filter((i) => compareKeyOf(i) !== key));
}

/* —— Chrome ————————————————————————————————— */

const NAV_ITEMS = [
  { id: 'home', href: '/', label: 'Início' },
  { id: 'busca', href: '/busca', label: 'Busca' },
  { id: 'bairro', href: '/bairro', label: 'Bairros' },
  { id: 'curiosidades', href: '/curiosidades', label: 'Curiosidades' },
  { id: 'comparar', href: '/comparar', label: 'Comparar' },
  { id: 'enviar', href: '/enviar', label: 'Enviar dados' },
  { id: 'estilo', href: '/estilo', label: 'Estilo', subtle: true },
];

function buildTopbar(active) {
  const bar = el('div', 'topbar');
  const inner = el('div', 'topbar-inner');

  const brand = el('a', 'brand');
  brand.href = '/';
  const mark = el('span', 'brand-mark');
  mark.appendChild(el('i'));
  brand.append(mark, el('span', 'brand-name', 'ImovelRadar'));

  const nav = el('nav', 'nav');
  NAV_ITEMS.forEach((item) => {
    const link = el('a', item.subtle ? 'subtle' : null, item.label);
    link.href = item.href;
    if (item.id === active) link.setAttribute('aria-current', 'page');
    // An open comparison is unfinished work: showing how many of the three
    // slots are taken is what brings the user back to the screen.
    if (item.id === 'comparar') {
      const count = readCompare().length;
      if (count) {
        link.appendChild(el('span', 'nav-count', `${count}/${COMPARE_LIMIT}`));
        link.title = `${count} de ${COMPARE_LIMIT} unidades no comparativo`;
      }
    }
    nav.appendChild(link);
  });

  const pill = el('div', 'city-pill');
  pill.id = 'city-pill';
  pill.append(el('i'), el('span', null, 'Carregando…'));

  inner.append(brand, nav, pill);
  bar.appendChild(inner);
  return bar;
}

const sourceNote = (city) =>
  `Dados de ITBI quitado publicados pela Prefeitura${
    city ? ` de ${cityLabel(city)}` : ''
  }. Valores declarados pelas partes; não constituem avaliação.`;

function buildFooter() {
  const footer = el('footer', 'site-footer');
  const disclaimer = el('span', 'disclaimer', sourceNote(''));
  disclaimer.id = 'source-note';
  footer.append(el('span', 'brand-name', 'ImovelRadar'), disclaimer);
  const api = el('a', 'api-link', 'API pública');
  api.href = '/docs';
  footer.appendChild(api);
  return footer;
}

/** Injects header + footer and fills the city pill. */
async function mountChrome(active) {
  document.body.prepend(buildTopbar(active));
  document.body.appendChild(buildFooter());

  const city = await resolveCity();
  const pill = $('city-pill');
  if (pill) {
    pill.lastChild.textContent = city ? cityLabel(city) : 'Sem dados carregados';
  }
  const note = $('source-note');
  if (note) note.textContent = sourceNote(city);
  return city;
}

const chevron = (size = 15) => {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'chevron');
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2.75');
  svg.setAttribute('stroke-linecap', 'round');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'm6 9 6 6 6-6');
  svg.appendChild(path);
  return svg;
};

/** Same-tab navigation avoids popup blockers; Ctrl/Cmd+click still opens a tab. */
function navigate(event, url) {
  if (event.metaKey || event.ctrlKey || event.button === 1) {
    window.open(url, '_blank', 'noopener,noreferrer');
    return;
  }
  window.location.assign(url);
}

const propertyUrl = (item) => {
  const params = new URLSearchParams();
  params.set('city', item.city);
  params.set('street', item.street);
  if (item.street_number) params.set('street_number', item.street_number);
  if (item.complement) params.set('complement', item.complement);
  return `/imovel?${params.toString()}`;
};

window.IR = {
  API_BASE,
  COMPARE_LIMIT,
  $,
  el,
  chevron,
  emptyState,
  fetchJson,
  formatCurrency,
  formatCompactCurrency,
  formatDate,
  formatNumber,
  formatInteger,
  formatPct,
  cityLabel,
  deltaTag,
  getCity,
  setCity,
  resolveCity,
  mountChrome,
  navigate,
  propertyUrl,
  compareKeyOf,
  readCompare,
  writeCompare,
  addToCompare,
  removeFromCompare,
};
})();
