const { $, el, fetchJson, formatCurrency, formatNumber, mountChrome } = window.IR;

const moneyPerM2 = (value) =>
  `R$ ${new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)}`;

function cell(text, className = '') {
  return el('td', className, text);
}

function render(items) {
  const body = $('results');
  body.replaceChildren();
  items.forEach((item) => {
    const tr = el('tr');
    const titleCell = el('td');
    const link = el('a', null, `${item.tipo_imovel} · ${item.bairro}`);
    link.href = item.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    titleCell.appendChild(link);
    if (item.rua) titleCell.appendChild(el('div', 'cell-sub', item.rua));
    titleCell.appendChild(el('div', 'cell-sub', `${item.source} · ${item.faixa_area} · ${item.comparaveis_count} comparáveis`));
    tr.appendChild(titleCell);
    tr.appendChild(cell(item.bairro));
    tr.appendChild(cell(`${formatNumber(item.area_util_m2, 2)} m²`, 'numeric'));
    tr.appendChild(cell(item.quartos == null ? '—' : String(item.quartos), 'numeric'));
    tr.appendChild(cell(String(item.vagas), 'numeric'));
    tr.appendChild(cell(formatCurrency(item.condominio), 'numeric'));
    tr.appendChild(cell(formatCurrency(item.preco_pedido), 'numeric'));
    tr.appendChild(cell(moneyPerM2(item.preco_m2_anuncio), 'numeric'));
    tr.appendChild(cell(moneyPerM2(item.preco_m2_bairro), 'numeric'));
    tr.appendChild(cell(`${(item.gap_pct * 100).toFixed(2)}%`, 'numeric'));
    const badge = el('span', item.status.startsWith('OUTLIER') ? 'tag tag-terracota' : item.gap_pct > 0 ? 'tag tag-salvia' : 'tag', item.status);
    tr.appendChild(cell(''));
    tr.lastChild.appendChild(badge);
    body.appendChild(tr);
  });
}

async function init() {
  await mountChrome('garimpo');
  try {
    const data = await fetchJson('/opportunities/flip');
    render(data.items);
    $('total').textContent = String(data.total);
    $('positive').textContent = String(data.items.filter((item) => item.gap_pct > 0).length);
    const latest = data.items.reduce((value, item) => {
      const candidate = item.pagina_verificada_em;
      return !value || new Date(candidate) > new Date(value) ? candidate : value;
    }, null);
    $('updated').textContent = latest
      ? new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(latest))
      : '—';
    $('status').textContent = data.total
      ? `${data.total} anúncios com página individual e mediana confirmadas`
      : 'Nenhum anúncio atende aos filtros e tem amostra suficiente do QuintoAndar.';
    $('rules').textContent = `A mediana exige pelo menos ${data.minimo_comparaveis} unidades distintas do QuintoAndar na mesma faixa. Faixas: 30–60, 60–90, 90–130 e 130–350 m². Gap positivo até 60%: oportunidade; acima de 60%: outlier para checagem; zero ou negativo: preço de mercado.`;
  } catch (error) {
    $('status').textContent = 'Não foi possível carregar o garimpo.';
    $('rules').textContent = error.message;
  }
}

init();
