(() => {
  const { $, el, fetchJson, formatCurrency, formatDate, formatNumber, formatInteger, cityLabel, slugify } = window.IR;
  const PAGE_SIZE = 25;
  let offset = 0;
  let total = 0;

  const city = () => $('admin-city').value;
  const statusLabel = (status) => ({
    pending: 'Pendente', insufficient_address: 'Endereço incompleto', not_found: 'Sem candidato',
    ambiguous: 'Ambíguo', matched: 'Associado automaticamente',
    matched_manual: 'Associado manualmente', rejected: 'Descartado',
  }[status] || status || '—');

  async function request(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Erro ${response.status}`);
    }
    return response.json();
  }

  function setMessage(message, kind = '') {
    const node = $('admin-message');
    node.textContent = message;
    node.dataset.kind = kind;
  }

  async function refreshOverview() {
    const data = await fetchJson('/admin/api/overview', { city: city() });
    $('kpi-condos').textContent = formatInteger(data.condominiums);
    $('kpi-transactions').textContent = formatInteger(data.transactions);
    $('kpi-matched').textContent = formatInteger((data.matches.matched || 0) + (data.matches.matched_manual || 0));
    $('kpi-ambiguous').textContent = formatInteger(data.matches.ambiguous || 0);
  }

  function addText(parent, tag, className, value) {
    const node = el(tag, className, value);
    parent.appendChild(node);
    return node;
  }

  async function saveChoice(transactionId, buildingId) {
    const result = await request(`/admin/api/itbi/transactions/${transactionId}/match`, {
      method: 'POST', body: JSON.stringify({ building_id: buildingId }),
    });
    setMessage(`ITBI ${transactionId}: ${statusLabel(result.status).toLowerCase()}.`, 'success');
    await Promise.all([refreshOverview(), loadMatches()]);
  }

  function renderCandidate(transaction, candidate) {
    const row = el('div', 'candidate-row');
    const details = el('div');
    const address = [candidate.street, candidate.street_number].filter(Boolean).join(', ');
    const range = candidate.min_area_m2 == null && candidate.max_area_m2 == null
      ? 'Área das unidades não informada'
      : `${formatNumber(candidate.min_area_m2)}–${formatNumber(candidate.max_area_m2)} m² publicados`;
    addText(details, 'strong', '', address || candidate.name || `Condomínio ${candidate.id}`);
    addText(details, 'small', '', [candidate.neighborhood, range].filter(Boolean).join(' · '));
    row.appendChild(details);
    if (candidate.url) {
      const link = el('a', 'btn btn-secondary btn-sm', 'Ver no QuintoAndar');
      link.href = candidate.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      row.appendChild(link);
    } else {
      row.appendChild(el('span'));
    }
    const choose = el('button', 'btn btn-sm', 'Associar');
    choose.type = 'button';
    choose.addEventListener('click', () => saveChoice(transaction.id, candidate.id).catch((error) => setMessage(error.message, 'error')));
    row.appendChild(choose);
    return row;
  }

  function renderTransaction(transaction) {
    const card = el('article', 'match-card');
    const heading = el('div', 'match-card-heading');
    const title = el('div');
    addText(title, 'h3', '', transaction.raw_address || [transaction.street, transaction.street_number].filter(Boolean).join(', '));
    addText(title, 'p', '', [transaction.neighborhood, transaction.postal_code].filter(Boolean).join(' · ') || 'Bairro ou CEP indisponível');
    heading.appendChild(title);
    addText(heading, 'span', 'admin-status', statusLabel(transaction.status));
    card.appendChild(heading);

    const meta = el('div', 'match-meta');
    [
      `ITBI ${formatDate(transaction.settlement_date)}`,
      `Valor declarado ${formatCurrency(transaction.declared_value)}`,
      `Área ITBI ${formatNumber(transaction.built_area_acquired_m2)} m²`,
      `Área total adquirida ${formatNumber(transaction.acquired_area_total_m2)} m²`,
    ].forEach((value) => meta.appendChild(el('span', '', value)));
    card.appendChild(meta);

    if (transaction.evidence?.length) {
      addText(card, 'p', '', `Evidências: ${transaction.evidence.join(', ')}${transaction.score ? ` · pontuação ${transaction.score}` : ''}`);
    }
    if (transaction.candidates.length) {
      transaction.candidates.forEach((candidate) => card.appendChild(renderCandidate(transaction, candidate)));
    } else {
      addText(card, 'p', '', 'Nenhum condomínio candidato disponível para escolha manual.');
    }
    const reject = el('button', 'btn btn-secondary btn-sm', 'Descartar associação');
    reject.type = 'button';
    reject.addEventListener('click', () => saveChoice(transaction.id, null).catch((error) => setMessage(error.message, 'error')));
    const actions = el('div', 'candidate-actions');
    actions.appendChild(reject);
    card.appendChild(actions);
    return card;
  }

  async function loadMatches() {
    const list = $('match-list');
    list.replaceChildren(el('p', 'admin-empty', 'Carregando registros…'));
    const params = {
      city: city(), status: $('status-filter').value,
      q: $('address-filter').value.trim(), limit: PAGE_SIZE, offset,
    };
    try {
      const data = await fetchJson('/admin/api/itbi/matches', params);
      total = data.total;
      list.replaceChildren();
      if (!data.items.length) {
        list.appendChild(el('p', 'admin-empty', 'Nenhum registro encontrado com esses filtros.'));
      } else {
        data.items.forEach((item) => list.appendChild(renderTransaction(item)));
      }
      const first = total ? offset + 1 : 0;
      const last = Math.min(offset + PAGE_SIZE, total);
      $('page-label').textContent = `${first}–${last} de ${formatInteger(total)}`;
      $('previous-button').disabled = offset <= 0;
      $('next-button').disabled = offset + PAGE_SIZE >= total;
    } catch (error) {
      list.replaceChildren(el('p', 'admin-empty', `Não foi possível carregar os registros: ${error.message}`));
      $('page-label').textContent = '—';
    }
  }

  async function runMatch() {
    setMessage('Associando ITBIs aos condomínios já coletados…');
    document.body.classList.add('admin-loading');
    try {
      const result = await request(`/admin/api/itbi/match?city=${encodeURIComponent(city())}`, { method: 'POST' });
      setMessage(`Associação concluída: ${result.matched} associados, ${result.ambiguous} ambíguos, ${result.not_found} sem candidato.`, 'success');
      offset = 0;
      await Promise.all([refreshOverview(), loadMatches()]);
    } catch (error) {
      setMessage(error.message, 'error');
    } finally {
      document.body.classList.remove('admin-loading');
    }
  }

  async function syncCondos() {
    const requestedLimit = Number($('admin-limit').value);
    if (!Number.isInteger(requestedLimit) || requestedLimit < 1 || requestedLimit > 500) {
      setMessage('Informe um limite entre 1 e 500 páginas.', 'error');
      return;
    }
    setMessage('Coleta iniciada. A atualização pode levar alguns minutos…');
    document.body.classList.add('admin-loading');
    $('sync-button').disabled = true;
    try {
      const result = await request('/admin/api/condominiums/sync', {
        method: 'POST',
        body: JSON.stringify({ city: city(), city_slug: slugify(city().replaceAll('_', ' ')), limit: requestedLimit }),
      });
      const association = result.itbi_association || {};
      const summary = result.pulado
        ? result.pulado
        : `${result.gravados || 0} páginas salvas, ${result.falhas || 0} falhas${result.interrompido ? `; interrompida: ${result.interrompido}` : ''}`;
      setMessage(`Coleta concluída: ${summary}. Associação ITBI: ${association.matched || 0} novas correspondências, ${association.ambiguous || 0} ambíguas.`, 'success');
      offset = 0;
      await Promise.all([refreshOverview(), loadMatches()]);
    } catch (error) {
      setMessage(`Coleta não concluída: ${error.message}`, 'error');
      await refreshOverview().catch(() => {});
    } finally {
      document.body.classList.remove('admin-loading');
      $('sync-button').disabled = false;
    }
  }

  $('sync-button').addEventListener('click', syncCondos);
  $('match-button').addEventListener('click', runMatch);
  $('refresh-button').addEventListener('click', () => Promise.all([refreshOverview(), loadMatches()]));
  $('filter-form').addEventListener('submit', (event) => { event.preventDefault(); offset = 0; loadMatches(); });
  $('previous-button').addEventListener('click', () => { offset = Math.max(0, offset - PAGE_SIZE); loadMatches(); });
  $('next-button').addEventListener('click', () => { if (offset + PAGE_SIZE < total) offset += PAGE_SIZE; loadMatches(); });

  async function initialize() {
    try {
      const cities = await fetchJson('/cities');
      if (cities.length) {
        const select = $('admin-city');
        select.replaceChildren(...cities.map((key) => {
          const option = document.createElement('option');
          option.value = key;
          option.textContent = cityLabel(key);
          return option;
        }));
        select.value = cities.includes('belo_horizonte') ? 'belo_horizonte' : cities[0];
      }
      await Promise.all([refreshOverview(), loadMatches()]);
    } catch (error) {
      setMessage(error.message, 'error');
    }
  }

  $('admin-city').addEventListener('change', () => { offset = 0; Promise.all([refreshOverview(), loadMatches()]); });
  initialize();
})();
