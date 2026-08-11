const API_BASE = window.location.origin;
const LIMIT = 50;

let currentPage = 0;
let totalResults = 0;

const $ = (id) => document.getElementById(id);

const formatCurrency = (value) =>
  new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    maximumFractionDigits: 0,
  }).format(value);

const formatDate = (value) =>
  new Intl.DateTimeFormat('pt-BR').format(new Date(value));

const formatNumber = (value) =>
  value != null
    ? new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value)
    : '-';

async function fetchJson(path, params = {}) {
  const url = new URL(path, API_BASE);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) {
      url.searchParams.set(key, String(value));
    }
  });
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Erro ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

async function loadCities() {
  try {
    const cities = await fetchJson('/cities');
    const select = $('city');
    cities.forEach((city) => {
      const option = document.createElement('option');
      option.value = city;
      option.textContent = city.replace(/_/g, ' ').toUpperCase();
      select.appendChild(option);
    });
  } catch (error) {
    console.error('Falha ao carregar cidades:', error);
  }
}

async function loadNeighborhoods(city) {
  const select = $('neighborhood');
  select.innerHTML = '<option value="">Todos</option>';
  if (!city) return;

  try {
    const neighborhoods = await fetchJson('/neighborhoods', { city });
    neighborhoods
      .sort((a, b) => a.localeCompare(b))
      .forEach((neighborhood) => {
        const option = document.createElement('option');
        option.value = neighborhood;
        option.textContent = neighborhood;
        select.appendChild(option);
      });
  } catch (error) {
    console.error('Falha ao carregar bairros:', error);
  }
}

function buildFilters() {
  return {
    city: $('city').value,
    neighborhood: $('neighborhood').value,
    street: $('street').value,
    street_number: $('street_number').value,
    min_value: $('min_value').value,
    max_value: $('max_value').value,
    min_area: $('min_area').value,
    max_area: $('max_area').value,
    construction_type: $('construction_type').value,
    occupation_type: $('occupation_type').value,
    date_from: $('date_from').value,
    date_to: $('date_to').value,
    limit: LIMIT,
    offset: currentPage * LIMIT,
  };
}

function renderResults(data) {
  totalResults = data.total;
  const tbody = $('results-body');
  tbody.innerHTML = '';

  $('results-count').textContent =
    totalResults === 0
      ? 'Nenhum resultado'
      : `${totalResults} transação(ões) encontrada(s)`;

  data.items.forEach((item) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${formatDate(item.settlement_date)}</td>
      <td>${item.neighborhood}</td>
      <td>${item.street}</td>
      <td>${item.street_number ?? '-'}</td>
      <td>${item.complement ?? '-'}</td>
      <td class="numeric">${formatNumber(item.built_area_acquired)}</td>
      <td class="numeric">${formatCurrency(item.declared_value)}</td>
      <td>${item.construction_type ?? '-'}</td>
      <td>${item.occupation_type ?? '-'}</td>
    `;
    tbody.appendChild(row);
  });

  $('page-info').textContent = `Página ${currentPage + 1}`;
  $('prev').disabled = currentPage === 0;
  $('next').disabled = (currentPage + 1) * LIMIT >= totalResults;
}

async function search() {
  $('search').disabled = true;
  $('search').textContent = 'Buscando...';
  $('results-body').innerHTML = '<tr><td colspan="9" class="numeric">Carregando...</td></tr>';

  try {
    const data = await fetchJson('/transactions', buildFilters());
    renderResults(data);
  } catch (error) {
    $('results-count').textContent = `Erro ao buscar: ${error.message}`;
    $('results-body').innerHTML = '';
  } finally {
    $('search').disabled = false;
    $('search').textContent = 'Buscar';
  }
}

function resetFilters() {
  $('city').value = '';
  $('neighborhood').innerHTML = '<option value="">Todos</option>';
  $('street').value = '';
  $('street_number').value = '';
  $('min_value').value = '';
  $('max_value').value = '';
  $('min_area').value = '';
  $('max_area').value = '';
  $('construction_type').value = '';
  $('occupation_type').value = '';
  $('date_from').value = '';
  $('date_to').value = '';
  currentPage = 0;
  search();
}

function previousPage() {
  if (currentPage > 0) {
    currentPage -= 1;
    search();
  }
}

function nextPage() {
  if ((currentPage + 1) * LIMIT < totalResults) {
    currentPage += 1;
    search();
  }
}

function applyUrlFilters() {
  const params = new URLSearchParams(window.location.search);
  const setIfPresent = (id, key) => {
    const value = params.get(key);
    if (value !== null) {
      const el = $(id);
      if (el) el.value = value;
    }
  };

  setIfPresent('street', 'street');
  setIfPresent('street_number', 'street_number');
  setIfPresent('min_value', 'min_value');
  setIfPresent('max_value', 'max_value');
  setIfPresent('min_area', 'min_area');
  setIfPresent('max_area', 'max_area');
  setIfPresent('construction_type', 'construction_type');
  setIfPresent('occupation_type', 'occupation_type');
  setIfPresent('date_from', 'date_from');
  setIfPresent('date_to', 'date_to');

  const city = params.get('city');
  if (city) {
    $('city').value = city;
  }

  const neighborhood = params.get('neighborhood');
  if (neighborhood) {
    loadNeighborhoods($('city').value).then(() => {
      $('neighborhood').value = neighborhood;
    });
  }

  const page = params.get('page');
  if (page) {
    currentPage = Math.max(0, parseInt(page, 10) - 1);
  }
}

async function init() {
  await loadCities();

  $('city').addEventListener('change', () => {
    loadNeighborhoods($('city').value);
    currentPage = 0;
  });

  $('search').addEventListener('click', () => {
    currentPage = 0;
    search();
  });

  $('reset').addEventListener('click', resetFilters);
  $('prev').addEventListener('click', previousPage);
  $('next').addEventListener('click', nextPage);

  document.querySelectorAll('.filters input, .filters select').forEach((el) => {
    if (el.id !== 'city' && el.id !== 'neighborhood') {
      el.addEventListener('change', () => {
        currentPage = 0;
      });
    }
  });

  $('upload-submit').addEventListener('click', uploadFile);

  applyUrlFilters();
  search();
}

async function uploadFile() {
  const city = $('upload-city').value;
  const fileInput = $('upload-file');
  const status = $('upload-status');

  if (!city) {
    status.textContent = 'Selecione uma cidade.';
    status.className = 'status error';
    return;
  }

  if (!fileInput.files || fileInput.files.length === 0) {
    status.textContent = 'Selecione um arquivo CSV.';
    status.className = 'status error';
    return;
  }

  const formData = new FormData();
  formData.append('city', city);
  formData.append('file', fileInput.files[0]);

  const button = $('upload-submit');
  button.disabled = true;
  button.textContent = 'Enviando...';
  status.textContent = '';
  status.className = 'status';

  try {
    const response = await fetch(`${API_BASE}/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Erro ${response.status}`);
    }

    const data = await response.json();
    status.textContent =
      `Upload concluído: ${data.inserted} de ${data.total_rows} transações inseridas para ${data.city}.`;
    status.className = 'status success';

    fileInput.value = '';
    await loadCities();
    $('city').value = city;
    await loadNeighborhoods(city);
    currentPage = 0;
    await search();
  } catch (error) {
    status.textContent = `Falha no upload: ${error.message}`;
    status.className = 'status error';
  } finally {
    button.disabled = false;
    button.textContent = 'Enviar';
  }
}

init();
