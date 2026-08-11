const { $, el, API_BASE, fetchJson, formatInteger, cityLabel, mountChrome } = window.IR;

const LOG_KEY = 'imovelradar:ingestoes';
const LOG_LIMIT = 5;

let selectedFile = null;

const readLog = () => {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(LOG_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const writeLog = (entries) =>
  window.localStorage.setItem(LOG_KEY, JSON.stringify(entries.slice(0, LOG_LIMIT)));

function renderLog() {
  const box = $('ingest-list');
  box.innerHTML = '';
  const entries = readLog();

  if (!entries.length) {
    box.appendChild(el('p', 'small', 'Nenhum envio registrado neste navegador ainda.'));
    return;
  }

  entries.forEach((entry) => {
    const row = el('div', 'ingest-row');

    const grow = el('div', 'grow');
    grow.append(
      el('div', 'file', entry.filename),
      el('div', 'meta', `${entry.date} · ${entry.city}`)
    );

    const counts = el('div', 'counts');
    counts.append(
      el('div', 'strong', formatInteger(entry.inserted)),
      el('div', 'meta', `de ${formatInteger(entry.total)} linhas`)
    );

    row.append(
      grow,
      counts,
      el(
        'span',
        entry.ok ? 'tag tag-salvia' : 'tag tag-terracota',
        entry.ok ? 'Concluído' : 'Falhou'
      )
    );
    box.appendChild(row);
  });
}

function logUpload(entry) {
  writeLog([
    {
      ...entry,
      date: new Intl.DateTimeFormat('pt-BR').format(new Date()),
    },
    ...readLog(),
  ]);
  renderLog();
}

function setStatus(message, kind = '') {
  const status = $('upload-status');
  status.className = `status ${kind}`.trim();
  status.innerHTML = '';
  if (!message) return;
  if (kind) status.appendChild(el('i'));
  status.append(document.createTextNode(message));
}

function pickFile(file) {
  selectedFile = file || null;
  $('filename').textContent = file ? file.name : '';
}

async function upload() {
  const city = $('upload-city').value;
  if (!selectedFile) {
    setStatus('Selecione um arquivo CSV.', 'error');
    return;
  }

  const button = $('upload-submit');
  button.disabled = true;
  button.textContent = 'Enviando…';
  setStatus('');

  const formData = new FormData();
  formData.append('city', city);
  formData.append('file', selectedFile);

  try {
    const response = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Erro ${response.status}`);
    }
    const data = await response.json();
    setStatus(
      `Último envio: ${formatInteger(data.inserted)} de ${formatInteger(data.total_rows)} linhas inseridas`,
      'success'
    );
    logUpload({
      filename: selectedFile.name,
      city: data.city,
      inserted: data.inserted,
      total: data.total_rows,
      ok: true,
    });
    window.IR.setCity(data.city);
    pickFile(null);
    $('upload-file').value = '';
  } catch (error) {
    setStatus(`Falha no upload: ${error.message}`, 'error');
    logUpload({
      filename: selectedFile?.name || '—',
      city,
      inserted: 0,
      total: 0,
      ok: false,
    });
  } finally {
    button.disabled = false;
    button.textContent = 'Enviar arquivo';
  }
}

function wireDropzone() {
  const zone = $('dropzone');
  const input = $('upload-file');

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      input.click();
    }
  });
  input.addEventListener('change', () => pickFile(input.files?.[0]));

  ['dragenter', 'dragover'].forEach((name) =>
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.add('dragging');
    })
  );
  ['dragleave', 'drop'].forEach((name) =>
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.remove('dragging');
    })
  );
  zone.addEventListener('drop', (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      // Keep the hidden input in sync so a later submit sends the dropped file.
      input.files = event.dataTransfer.files;
      pickFile(file);
    }
  });
}

async function init() {
  document.querySelectorAll('.select-wrap').forEach((wrap) =>
    wrap.appendChild(window.IR.chevron())
  );

  const city = await mountChrome('enviar');
  const cities = await fetchJson('/cities').catch(() => []);
  cities
    .filter((name) => name !== 'belo_horizonte')
    .forEach((name) => {
      const option = el('option', null, cityLabel(name));
      option.value = name;
      $('upload-city').appendChild(option);
    });
  if (city && [...$('upload-city').options].some((o) => o.value === city)) {
    $('upload-city').value = city;
  }

  wireDropzone();
  renderLog();
  $('upload-submit').addEventListener('click', upload);
}

init();
