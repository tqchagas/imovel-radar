(() => {
  const { $, el, fetchJson, formatCurrency, formatDate, formatNumber, formatInteger, cityLabel, slugify } = window.IR;
  const PAGE_SIZE = 50;
  const MATCH_PAGE_SIZE = 25;
  const DETAIL_PAGE_SIZE = 25;
  let condoOffset = 0;
  let condoTotal = 0;
  let matchOffset = 0;
  let matchTotal = 0;
  let detailOffset = 0;
  let detailBuildingId = null;

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

  function addText(parent, tag, className, value) {
    const node = el(tag, className, value);
    parent.appendChild(node);
    return node;
  }

  async function refreshOverview() {
    const data = await fetchJson('/admin/api/overview', { city: city() });
    const matched = (data.matches.matched || 0) + (data.matches.matched_manual || 0);
    $('kpi-condos').textContent = formatInteger(data.condominiums);
    $('kpi-linked-condos').textContent = formatInteger(data.associated_condominiums);
    $('kpi-matched').textContent = formatInteger(matched);
    $('kpi-ambiguous').textContent = formatInteger(data.matches.ambiguous || 0);
  }

  function renderBuildingRow(building) {
    const row = el('tr');
    const addressCell = el('td');
    addText(addressCell, 'strong', 'admin-table-primary', [building.street, building.street_number].filter(Boolean).join(', ') || 'Endereço não informado');
    addText(addressCell, 'small', 'admin-table-secondary', `ID ${building.id} · ${building.external_id}`);
    row.appendChild(addressCell);

    const areaCell = el('td');
    addText(areaCell, 'span', '', building.neighborhood || 'Bairro não informado');
    addText(areaCell, 'small', 'admin-table-secondary', building.postal_code || 'CEP não informado');
    row.appendChild(areaCell);

    const unitsCell = el('td');
    const areaRange = building.min_area_m2 == null && building.max_area_m2 == null
      ? 'Área não informada'
      : `${formatNumber(building.min_area_m2)}–${formatNumber(building.max_area_m2)} m²`;
    const bedroomRange = building.min_bedrooms == null && building.max_bedrooms == null
      ? 'Quartos não informados'
      : `${building.min_bedrooms ?? '—'}–${building.max_bedrooms ?? '—'} quartos`;
    addText(unitsCell, 'span', '', areaRange);
    addText(unitsCell, 'small', 'admin-table-secondary', bedroomRange);
    row.appendChild(unitsCell);

    const matchCell = el('td');
    if (building.associated_transactions) {
      addText(matchCell, 'strong', 'association-count', formatInteger(building.associated_transactions));
      addText(matchCell, 'small', 'admin-table-secondary', `${building.automatic_matches} automáticos · ${building.manual_matches} manuais`);
    } else {
      addText(matchCell, 'span', 'association-empty', 'Nenhum ITBI');
    }
    row.appendChild(matchCell);

    const updateCell = el('td');
    addText(updateCell, 'span', '', formatDate(building.source_lastmod || building.updated_at?.slice(0, 10)));
    addText(updateCell, 'small', 'admin-table-secondary', building.source_lastmod ? 'Atualização do portal' : 'Coletado pelo ImóvelRadar');
    row.appendChild(updateCell);

    const actionCell = el('td', 'admin-actions-cell');
    const details = el('button', 'btn btn-secondary btn-sm', 'Ver dados');
    details.type = 'button';
    details.setAttribute('aria-label', `Ver dados do condomínio ${building.street || building.external_id}`);
    details.addEventListener('click', () => openBuilding(building.id));
    actionCell.appendChild(details);
    row.appendChild(actionCell);
    return row;
  }

  async function loadCondominiums() {
    const list = $('condo-list');
    list.replaceChildren();
    const loading = el('tr');
    loading.appendChild(el('td', 'admin-empty', 'Carregando condomínios…'));
    loading.firstChild.colSpan = 6;
    list.appendChild(loading);
    const params = {
      city: city(), q: $('condo-search').value.trim(),
      association: $('association-filter').value, limit: PAGE_SIZE, offset: condoOffset,
    };
    try {
      const data = await fetchJson('/admin/api/condominiums', params);
      condoTotal = data.total;
      list.replaceChildren();
      if (!data.items.length) {
        const empty = el('tr');
        const cell = el('td', 'admin-empty', 'Nenhum condomínio encontrado com esses filtros.');
        cell.colSpan = 6;
        empty.appendChild(cell);
        list.appendChild(empty);
      } else {
        data.items.forEach((building) => list.appendChild(renderBuildingRow(building)));
      }
      const first = condoTotal ? condoOffset + 1 : 0;
      const last = Math.min(condoOffset + PAGE_SIZE, condoTotal);
      $('condo-page-label').textContent = `${first}–${last} de ${formatInteger(condoTotal)} condomínios`;
      $('condo-previous').disabled = condoOffset <= 0;
      $('condo-next').disabled = condoOffset + PAGE_SIZE >= condoTotal;
    } catch (error) {
      list.replaceChildren();
      const row = el('tr');
      const cell = el('td', 'admin-empty', `Não foi possível carregar o catálogo: ${error.message}`);
      cell.colSpan = 6;
      row.appendChild(cell);
      list.appendChild(row);
      $('condo-page-label').textContent = '—';
    }
  }

  function renderBuildingDetail(data) {
    const target = $('condo-detail');
    target.replaceChildren();
    const building = data.building;
    const facts = el('dl', 'condo-facts');
    const fact = (label, value) => {
      const group = el('div', 'condo-fact');
      addText(group, 'dt', '', label);
      addText(group, 'dd', '', value || '—');
      facts.appendChild(group);
    };
    fact('Endereço', [building.street, building.street_number].filter(Boolean).join(', '));
    fact('Bairro', building.neighborhood);
    fact('CEP', building.postal_code);
    fact('Área das unidades', building.min_area_m2 == null && building.max_area_m2 == null
      ? 'Não informada' : `${formatNumber(building.min_area_m2)}–${formatNumber(building.max_area_m2)} m²`);
    fact('Quartos publicados', building.min_bedrooms == null && building.max_bedrooms == null
      ? 'Não informado' : `${building.min_bedrooms ?? '—'}–${building.max_bedrooms ?? '—'}`);
    fact('Portaria', building.doorman);
    fact('Latitude / longitude', building.latitude == null ? '—' : `${building.latitude}, ${building.longitude}`);
    fact('Código do portal', building.external_id);
    target.appendChild(facts);

    if (building.installations?.length) {
      const amenities = el('section', 'condo-amenities');
      addText(amenities, 'h3', '', 'Instalações informadas');
      addText(amenities, 'p', '', building.installations.join(' · '));
      target.appendChild(amenities);
    }
    if (building.url) {
      const linkRow = el('p', 'condo-source-link');
      const link = el('a', '', 'Abrir condomínio no QuintoAndar');
      link.href = building.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      linkRow.appendChild(link);
      target.appendChild(linkRow);
    }

    const associated = el('section', 'condo-associated');
    const header = el('div', 'admin-panel-heading');
    const title = el('div');
    addText(title, 'h3', '', `ITBIs associados (${formatInteger(data.total)})`);
    addText(title, 'p', '', 'Transações vinculadas a este condomínio por endereço.');
    header.appendChild(title);
    associated.appendChild(header);
    if (!data.associated_transactions.length) {
      associated.appendChild(el('p', 'admin-empty', 'Nenhum registro ITBI está associado a este condomínio.'));
    } else {
      const wrapper = el('div', 'admin-table-wrap');
      const table = el('table', 'admin-table condo-transaction-table');
      const head = el('thead');
      const headRow = el('tr');
      ['Data', 'Endereço no ITBI', 'Valor declarado', 'Área adquirida', 'Associação'].forEach((label) => {
        const th = el('th', '', label);
        th.scope = 'col';
        headRow.appendChild(th);
      });
      head.appendChild(headRow);
      table.appendChild(head);
      const body = el('tbody');
      data.associated_transactions.forEach((transaction) => {
        const row = el('tr');
        row.appendChild(el('td', '', formatDate(transaction.settlement_date)));
        row.appendChild(el('td', '', transaction.raw_address || [transaction.street, transaction.street_number].filter(Boolean).join(', ')));
        row.appendChild(el('td', 'numeric', formatCurrency(transaction.declared_value)));
        row.appendChild(el('td', '', `${formatNumber(transaction.built_area_acquired_m2)} m²`));
        const status = el('td');
        addText(status, 'span', `admin-status status-${transaction.status}`, statusLabel(transaction.status));
        if (transaction.score != null) addText(status, 'small', 'admin-table-secondary', `Confiança ${transaction.score}%`);
        row.appendChild(status);
        body.appendChild(row);
      });
      table.appendChild(body);
      wrapper.appendChild(table);
      associated.appendChild(wrapper);
      if (data.total > DETAIL_PAGE_SIZE) {
        const paging = el('div', 'admin-pagination');
        const previous = el('button', 'btn btn-secondary btn-sm', 'Anterior');
        previous.type = 'button';
        previous.disabled = detailOffset <= 0;
        previous.addEventListener('click', () => { detailOffset = Math.max(0, detailOffset - DETAIL_PAGE_SIZE); loadBuildingDetail(); });
        paging.appendChild(previous);
        paging.appendChild(el('span', '', `${detailOffset + 1}–${Math.min(detailOffset + DETAIL_PAGE_SIZE, data.total)} de ${data.total}`));
        const next = el('button', 'btn btn-secondary btn-sm', 'Próxima');
        next.type = 'button';
        next.disabled = detailOffset + DETAIL_PAGE_SIZE >= data.total;
        next.addEventListener('click', () => { if (detailOffset + DETAIL_PAGE_SIZE < data.total) detailOffset += DETAIL_PAGE_SIZE; loadBuildingDetail(); });
        paging.appendChild(next);
        associated.appendChild(paging);
      }
    }
    target.appendChild(associated);
  }

  async function loadBuildingDetail() {
    const target = $('condo-detail');
    target.replaceChildren(el('p', 'admin-empty', 'Carregando dados do condomínio…'));
    try {
      const data = await fetchJson(`/admin/api/condominiums/${detailBuildingId}`, {
        limit: DETAIL_PAGE_SIZE, offset: detailOffset,
      });
      renderBuildingDetail(data);
    } catch (error) {
      target.replaceChildren(el('p', 'admin-empty', `Não foi possível carregar os detalhes: ${error.message}`));
    }
  }

  async function openBuilding(buildingId) {
    detailBuildingId = buildingId;
    detailOffset = 0;
    $('condo-dialog').showModal();
    $('condo-detail-title').textContent = 'Condomínio';
    await loadBuildingDetail();
  }

  async function saveChoice(transactionId, buildingId) {
    const result = await request(`/admin/api/itbi/transactions/${transactionId}/match`, {
      method: 'POST', body: JSON.stringify({ building_id: buildingId }),
    });
    setMessage(`ITBI ${transactionId}: ${statusLabel(result.status).toLowerCase()}.`, 'success');
    await Promise.all([refreshOverview(), loadCondominiums(), loadMatches()]);
  }

  function renderCandidate(transaction, candidate) {
    const row = el('div', 'candidate-row');
    const details = el('div');
    const address = [candidate.street, candidate.street_number].filter(Boolean).join(', ');
    addText(details, 'strong', '', address || `Condomínio ${candidate.id}`);
    addText(details, 'small', '', [candidate.neighborhood, candidate.postal_code].filter(Boolean).join(' · '));
    row.appendChild(details);
    const detailButton = el('button', 'btn btn-secondary btn-sm', 'Dados');
    detailButton.type = 'button';
    detailButton.addEventListener('click', () => openBuilding(candidate.id));
    row.appendChild(detailButton);
    if (candidate.url) {
      const link = el('a', 'btn btn-secondary btn-sm', 'QuintoAndar');
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
    addText(heading, 'span', `admin-status status-${transaction.status}`, statusLabel(transaction.status));
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
      addText(card, 'p', '', `Evidências: ${transaction.evidence.join(', ')}${transaction.score != null ? ` · confiança ${transaction.score}%` : ''}`);
    }
    if (transaction.candidates.length) {
      transaction.candidates.forEach((candidate) => card.appendChild(renderCandidate(transaction, candidate)));
    } else {
      addText(card, 'p', '', 'Nenhum condomínio candidato disponível para escolha manual.');
    }
    const reject = el('button', 'btn btn-secondary btn-sm', 'Descartar associação');
    reject.type = 'button';
    reject.addEventListener('click', () => {
      if (window.confirm(`Descartar o vínculo do ITBI ${transaction.id}?`)) {
        saveChoice(transaction.id, null).catch((error) => setMessage(error.message, 'error'));
      }
    });
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
      q: $('address-filter').value.trim(), limit: MATCH_PAGE_SIZE, offset: matchOffset,
    };
    try {
      const data = await fetchJson('/admin/api/itbi/matches', params);
      matchTotal = data.total;
      list.replaceChildren();
      if (!data.items.length) {
        list.appendChild(el('p', 'admin-empty', 'Nenhum registro encontrado com esses filtros.'));
      } else {
        data.items.forEach((item) => list.appendChild(renderTransaction(item)));
      }
      const first = matchTotal ? matchOffset + 1 : 0;
      const last = Math.min(matchOffset + MATCH_PAGE_SIZE, matchTotal);
      $('match-page-label').textContent = `${first}–${last} de ${formatInteger(matchTotal)} ITBIs`;
      $('match-previous').disabled = matchOffset <= 0;
      $('match-next').disabled = matchOffset + MATCH_PAGE_SIZE >= matchTotal;
    } catch (error) {
      list.replaceChildren(el('p', 'admin-empty', `Não foi possível carregar os registros: ${error.message}`));
      $('match-page-label').textContent = '—';
    }
  }

  async function runMatch() {
    setMessage('Recalculando associações para os condomínios já coletados…');
    document.body.classList.add('admin-loading');
    try {
      const result = await request(`/admin/api/itbi/match?city=${encodeURIComponent(city())}`, { method: 'POST' });
      setMessage(`Revisão concluída: ${result.matched} associados, ${result.ambiguous} ambíguos e ${result.not_found} sem candidato.`, 'success');
      matchOffset = 0;
      await Promise.all([refreshOverview(), loadCondominiums(), loadMatches()]);
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
    const button = $('sync-button');
    button.disabled = true;
    setMessage('Coleta em andamento. Cada página é processada e salva conforme chega…');
    document.body.classList.add('admin-loading');
    try {
      const result = await request('/admin/api/condominiums/sync', {
        method: 'POST',
        body: JSON.stringify({ city: city(), city_slug: slugify(city().replaceAll('_', ' ')), limit: requestedLimit }),
      });
      const association = result.itbi_association || {};
      const summary = result.pulado || `${result.gravados || 0} páginas salvas, ${result.falhas || 0} falhas${result.interrompido ? `; interrupção: ${result.interrompido}` : ''}`;
      setMessage(`Coleta concluída: ${summary}. Associações encontradas: ${association.matched || 0}; ambíguas: ${association.ambiguous || 0}.`, 'success');
      condoOffset = 0;
      matchOffset = 0;
      await Promise.all([refreshOverview(), loadCondominiums(), loadMatches()]);
    } catch (error) {
      setMessage(`Coleta não concluída: ${error.message}`, 'error');
      await refreshOverview().catch(() => {});
    } finally {
      document.body.classList.remove('admin-loading');
      button.disabled = false;
    }
  }

  function selectTab(name, focus = false) {
    const tabs = [
      { id: 'condominiums', button: $('tab-condominiums'), panel: $('panel-condominiums') },
      { id: 'associations', button: $('tab-associations'), panel: $('panel-associations') },
    ];
    tabs.forEach((tab) => {
      const selected = tab.id === name;
      tab.button.setAttribute('aria-selected', String(selected));
      tab.button.tabIndex = selected ? 0 : -1;
      tab.panel.hidden = !selected;
    });
    if (focus) $(`tab-${name}`).focus();
    if (name === 'associations') loadMatches();
    else loadCondominiums();
  }

  async function initialize() {
    try {
      const session = await request('/admin/api/session');
      $('admin-login').hidden = session.authenticated;
      $('admin-content').hidden = !session.authenticated;
      if (!session.configured) {
        $('admin-login-message').textContent = 'O painel está desativado. Configure ADMIN_PASSWORD no ambiente da aplicação.';
        return;
      }
      if (!session.authenticated) {
        $('admin-password').focus();
        return;
      }
    } catch (error) {
      $('admin-login').hidden = false;
      $('admin-content').hidden = true;
      $('admin-login-message').textContent = error.message;
      $('admin-login-message').dataset.kind = 'error';
      return;
    }

    try {
      const cities = await fetchJson('/admin/api/cities');
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
      await Promise.all([refreshOverview(), loadCondominiums()]);
    } catch (error) {
      setMessage(`Não foi possível carregar o painel: ${error.message}`, 'error');
    }
  }

  $('admin-login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = $('admin-login-button');
    const message = $('admin-login-message');
    button.disabled = true;
    message.textContent = '';
    try {
      await request('/admin/api/login', {
        method: 'POST', body: JSON.stringify({ password: $('admin-password').value }),
      });
      $('admin-password').value = '';
      await initialize();
    } catch (error) {
      message.textContent = error.message;
      message.dataset.kind = 'error';
      $('admin-password').select();
    } finally {
      button.disabled = false;
    }
  });

  $('admin-logout').addEventListener('click', async () => {
    try {
      await request('/admin/api/logout', { method: 'POST' });
    } catch (error) {
      setMessage(error.message, 'error');
    }
    $('admin-login-message').textContent = '';
    await initialize();
  });

  $('admin-city').addEventListener('change', () => {
    condoOffset = 0;
    matchOffset = 0;
    Promise.all([refreshOverview(), loadCondominiums()]);
    if (!$('panel-associations').hidden) loadMatches();
  });
  $('condo-filter-form').addEventListener('submit', (event) => {
    event.preventDefault();
    condoOffset = 0;
    loadCondominiums();
  });
  $('association-filter').addEventListener('change', () => { condoOffset = 0; loadCondominiums(); });
  $('condo-previous').addEventListener('click', () => { condoOffset = Math.max(0, condoOffset - PAGE_SIZE); loadCondominiums(); });
  $('condo-next').addEventListener('click', () => { if (condoOffset + PAGE_SIZE < condoTotal) condoOffset += PAGE_SIZE; loadCondominiums(); });
  $('sync-button').addEventListener('click', syncCondos);
  $('match-button').addEventListener('click', runMatch);
  $('match-filter-form').addEventListener('submit', (event) => { event.preventDefault(); matchOffset = 0; loadMatches(); });
  $('match-previous').addEventListener('click', () => { matchOffset = Math.max(0, matchOffset - MATCH_PAGE_SIZE); loadMatches(); });
  $('match-next').addEventListener('click', () => { if (matchOffset + MATCH_PAGE_SIZE < matchTotal) matchOffset += MATCH_PAGE_SIZE; loadMatches(); });
  $('tab-condominiums').addEventListener('click', () => selectTab('condominiums'));
  $('tab-associations').addEventListener('click', () => selectTab('associations'));
  document.querySelectorAll('.admin-tab').forEach((tab) => tab.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      selectTab(tab.id === 'tab-condominiums' ? 'associations' : 'condominiums', true);
    }
  }));
  $('condo-dialog-close').addEventListener('click', () => $('condo-dialog').close());
  $('condo-dialog').addEventListener('click', (event) => {
    if (event.target === $('condo-dialog')) $('condo-dialog').close();
  });

  initialize();
})();
