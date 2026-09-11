/* Imóveis de leilão: digitar, avaliar, acompanhar.
 *
 * A tela mostra as duas leituras lado a lado e a divergência entre elas, sem
 * arbitrar qual está certa. A coordenada aparece sempre, com a fonte, porque é
 * o campo mais sensível da conta — seis metros já moveram 18,4%.
 */
const { API_BASE, $, el, emptyState, fetchJson, formatCurrency, formatDate, mountChrome } = window.IR;

const NUMERICOS = new Set([
  'latitude', 'longitude', 'total_area', 'bedroom_count', 'bathroom_count',
  'suites_count', 'parking_slots', 'floor', 'condominium_per_month',
  'iptu_per_year', 'lance_minimo',
]);

// Como o portal declara a própria confiança. "low" é comum, inclusive em bairro
// denso — é ele admitindo que tem pouca base, e não um erro.
const CERTEZA = { low: 'baixa', medium: 'média', high: 'alta' };

const state = { imoveis: [], incluirPassados: false };

/* `fetchJson` do common.js é só leitura: o segundo argumento vira query string
 * e o método é sempre GET. Escrita precisa de fetch de verdade. */
async function enviar(path, method, body) {
  const resposta = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resposta.ok) {
    const erro = await resposta.json().catch(() => ({}));
    throw new Error(erro.detail || `Erro ${resposta.status}`);
  }
  return resposta.status === 204 ? null : resposta.json();
}

function valoresDoForm(form) {
  const dados = {};
  new FormData(form).forEach((valor, chave) => {
    const texto = String(valor).trim();
    if (!texto) return;
    dados[chave] = NUMERICOS.has(chave) ? Number(texto) : texto;
  });
  return dados;
}

function pct(valor) {
  if (valor === null || valor === undefined) return '—';
  const n = Number(valor) * 100;
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`;
}

function linhaLeitura(rotulo, valor, extra) {
  const linha = el('div', 'bar-row');
  linha.appendChild(el('span', 'card-label', rotulo));
  linha.appendChild(el('strong', 'card-value', valor));
  if (extra) linha.appendChild(el('span', 'card-meta', extra));
  return linha;
}

function blocoAvaliacao(imovel) {
  const a = imovel.avaliacao;
  const bloco = el('div', 'stats-block');

  if (!a) {
    bloco.appendChild(el('p', 'panel-note', 'Ainda não avaliado.'));
    return bloco;
  }
  if (a.erro && a.preco_qpreco === null) {
    bloco.appendChild(el('p', 'panel-note', `Não foi possível avaliar: ${a.erro}`));
    bloco.appendChild(el('p', 'panel-note',
      'Confira a coordenada antes de concluir que o imóvel é atípico — o portal '
      + 'responde a mesma coisa nos dois casos.'));
    return bloco;
  }

  const m2 = a.preco_qpreco && imovel.total_area
    ? ` (${formatCurrency(a.preco_qpreco / imovel.total_area)}/m²)` : '';
  bloco.appendChild(linhaLeitura('Valor QuintoAndar', formatCurrency(a.preco_qpreco) + m2,
    `certeza ${CERTEZA[a.certeza] || a.certeza || '—'}`));

  // Os três preços não são uma faixa de incerteza: o portal os devolve também
  // como FASTER / REGULAR / SLOWER, isto é, quanto pedir para vender rápido,
  // no ritmo normal, ou esperando. Conferido idêntico em três imóveis.
  if (a.preco_rapido && a.preco_devagar) {
    const trio = el('div', 'form-grid');
    // Os rótulos são os do próprio portal, para o número bater quando você
    // conferir no site deles: lá, o destaque "Venda por / Ideal" é o MENOR dos
    // três, e "na média dos similares na região" é o maior. Chamar o do meio de
    // "sugerido" faria a comparação parecer divergente sem ser.
    [['Ideal (venda por)', a.preco_rapido],
     ['Sugerido pelo modelo', a.preco_qpreco],
     ['Média dos similares', a.preco_devagar]].forEach(([rotulo, valor]) => {
      const coluna = el('div', 'field');
      coluna.appendChild(el('label', null, rotulo));
      coluna.appendChild(el('strong', 'card-value', formatCurrency(valor)));
      trio.appendChild(coluna);
    });
    bloco.appendChild(trio);
  }
  if (a.limite_inferior && a.limite_superior) {
    bloco.appendChild(el('p', 'card-meta',
      `O modelo não vai abaixo de ${formatCurrency(a.limite_inferior)} nem acima de `
      + `${formatCurrency(a.limite_superior)} — são os extremos dele, fora da faixa `
      + 'que ele recomenda pedir.'));
  }

  if (a.preco_vendidos) {
    bloco.appendChild(linhaLeitura('Mediana das vendas reais', formatCurrency(a.preco_vendidos),
      `${a.comparaveis_usados} comparáveis`));
    const div = el('p', a.atipico ? 'tag tag-terracota' : 'card-meta',
      a.atipico
        ? `Divergência de ${pct(a.divergencia_pct)} — imóvel atípico, olhe os comparáveis.`
        : `Divergência de ${pct(a.divergencia_pct)}: as duas leituras concordam.`);
    bloco.appendChild(div);
  } else {
    bloco.appendChild(el('p', 'panel-note',
      'Sem comparáveis vendidos suficientes no entorno — a estimativa responde sozinha.'));
  }

  if (a.preco_itbi) {
    bloco.appendChild(linhaLeitura('Mediana de ITBI', formatCurrency(a.preco_itbi),
      `${a.itbi_tier} · ${a.itbi_amostra} quitações`));
  }

  if (a.comparaveis_json && a.comparaveis_json.length) {
    const detalhe = el('details');
    detalhe.appendChild(el('summary', null, `Vendas no entorno (${a.comparaveis_json.length})`));
    const tabela = el('table', 'tabular');
    const corpo = el('tbody');
    a.comparaveis_json.forEach((c) => {
      const tr = el('tr');
      tr.appendChild(el('td', null, c.sold_at ? c.sold_at.slice(0, 7) : '—'));
      tr.appendChild(el('td', 'numeric', formatCurrency(c.price)));
      tr.appendChild(el('td', 'numeric', c.price_m2 ? `${formatCurrency(c.price_m2)}/m²` : '—'));
      tr.appendChild(el('td', 'numeric', c.total_area ? `${c.total_area} m²` : '—'));
      tr.appendChild(el('td', 'numeric', c.bedroom_count != null ? `${c.bedroom_count}q` : '—'));
      tr.appendChild(el('td', 'numeric',
        c.distance_km != null ? `${Math.round(c.distance_km * 1000)} m` : '—'));
      tr.appendChild(el('td', null, (c.address || '') + (c.same_condo ? ' · mesmo condomínio' : '')));
      corpo.appendChild(tr);
    });
    tabela.appendChild(corpo);
    detalhe.appendChild(tabela);
    bloco.appendChild(detalhe);
  }

  if (a.consultado_em) {
    // `formatDate` concatena "T12:00:00" e só aceita YYYY-MM-DD; `consultado_em`
    // é datetime completo e faria `new Date` devolver Invalid Date.
    bloco.appendChild(
      el('p', 'panel-note', `Consultado em ${formatDate(a.consultado_em.slice(0, 10))}.`));
  }
  return bloco;
}

function cartao(imovel) {
  const card = el('article', 'card');

  const head = el('div', 'result-card-top');
  const numero = imovel.address_number ? `, ${imovel.address_number}` : '';
  head.appendChild(el('h3', 'cell-title',
    imovel.apelido || `${imovel.address}${numero}`));
  head.appendChild(el('span', 'card-meta',
    `${imovel.address}${numero} — ${imovel.neighborhood || ''} ${imovel.city}`));
  card.appendChild(head);

  const ficha = el('p', 'panel-note',
    `${imovel.total_area} m² úteis · ${imovel.bedroom_count} quartos · `
    + `${imovel.parking_slots} vagas${imovel.floor ? ` · ${imovel.floor}º andar` : ''}`);
  card.appendChild(ficha);

  // A coordenada e a sua origem ficam visíveis de propósito: é o único jeito
  // de o dono saber quanto confiar no número.
  const coord = el('p', imovel.coordenada_fonte === 'portal' ? 'card-meta' : 'tag tag-terracota',
    `${Number(imovel.latitude).toFixed(6)}, ${Number(imovel.longitude).toFixed(6)}`
    + ` — ${imovel.coordenada_rotulo || 'origem desconhecida'}`
    + (imovel.coordenada_fonte === 'portal' ? '' : ' (o portal usa outro ponto para o prédio)'));
  card.appendChild(coord);

  if (imovel.data_leilao || imovel.lance_minimo) {
    const leilao = el('p', 'panel-note',
      [imovel.data_leilao ? `Leilão em ${formatDate(imovel.data_leilao)}` : null,
       imovel.lance_minimo ? `lance mínimo ${formatCurrency(imovel.lance_minimo)}` : null]
        .filter(Boolean).join(' · '));
    card.appendChild(leilao);
  }

  card.appendChild(blocoAvaliacao(imovel));

  const acoes = el('div', 'result-card-foot');
  const reavaliar = el('button', 'btn btn-ghost btn-sm', 'Reavaliar');
  reavaliar.addEventListener('click', async () => {
    reavaliar.disabled = true;
    reavaliar.textContent = 'Consultando…';
    try {
      await enviar(`/auctions/${imovel.id}/avaliar?force=true`, 'POST');
      await carregar();
    } finally {
      reavaliar.disabled = false;
    }
  });
  acoes.appendChild(reavaliar);

  const remover = el('button', 'btn btn-ghost btn-sm', 'Remover');
  remover.addEventListener('click', async () => {
    if (!window.confirm('Remover este imóvel e o histórico dele?')) return;
    await enviar(`/auctions/${imovel.id}`, 'DELETE');
    await carregar();
  });
  acoes.appendChild(remover);

  // O edital já traz endereço, área e lance mínimo: o simulador de flip
  // começa daí em vez de pedir tudo de novo.
  const simular = el('a', 'btn btn-ghost btn-sm', 'Simular flip');
  simular.href = `/flip?origem=leilao&origem_id=${imovel.id}`;
  acoes.appendChild(simular);
  card.appendChild(acoes);

  if (imovel.edital_url) {
    const link = el('a', 'panel-note', 'Abrir o edital');
    link.href = imovel.edital_url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    card.appendChild(link);
  }
  return card;
}

function render() {
  const lista = $('lista');
  lista.innerHTML = '';
  if (!state.imoveis.length) {
    lista.appendChild(emptyState(
      'Nenhum imóvel acompanhado',
      'Cadastre um imóvel do edital para ver o que o QuintoAndar diz sobre ele.'));
    return;
  }
  state.imoveis.forEach((imovel) => lista.appendChild(cartao(imovel)));
}

async function carregar() {
  state.imoveis = await fetchJson('/auctions', {
    incluir_passados: state.incluirPassados ? 'true' : '',
  });
  render();
}

async function sugerirCoordenada() {
  const form = $('form-imovel');
  const dados = valoresDoForm(form);
  const nota = $('coordenada-nota');
  if (!dados.city || !dados.address) {
    nota.textContent = 'Preencha cidade e rua primeiro.';
    return;
  }
  try {
    const achado = await fetchJson('/auctions/coordenada', {
      city: dados.city, street: dados.address, number: dados.address_number,
    });
    $('latitude').value = achado.latitude;
    $('longitude').value = achado.longitude;
    nota.textContent = `${achado.rotulo}. Confira o pino no mapa antes de salvar.`;
  } catch (erro) {
    nota.textContent = 'Sem coordenada conhecida aqui — cole a do Google Maps.';
  }
}

function montar() {
  mountChrome('leilao');

  $('btn-coordenada').addEventListener('click', sugerirCoordenada);

  $('incluir-passados').addEventListener('change', (evento) => {
    state.incluirPassados = evento.target.checked;
    carregar();
  });

  $('form-imovel').addEventListener('submit', async (evento) => {
    evento.preventDefault();
    const botao = $('btn-salvar');
    const erro = $('form-erro');
    erro.textContent = '';
    erro.hidden = true;
    botao.disabled = true;
    botao.textContent = 'Consultando…';
    try {
      const criado = await enviar('/auctions', 'POST', valoresDoForm(evento.target));
      await enviar(`/auctions/${criado.id}/avaliar`, 'POST');
      evento.target.reset();
      $('coordenada-nota').textContent = '';
      await carregar();
    } catch (falha) {
      erro.textContent = String(falha.message || falha);
      erro.hidden = false;
    } finally {
      botao.disabled = false;
      botao.textContent = 'Salvar e avaliar';
    }
  });

  carregar();
}

document.addEventListener('DOMContentLoaded', montar);
