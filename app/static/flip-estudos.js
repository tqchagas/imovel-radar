/* Pipeline de estudos de flip.
 *
 * Cada linha vem com os indicadores já recalculados pelo servidor, com as
 * premissas que aquele estudo congelou. A tela filtra e mostra, nada mais.
 */
const {
  API_BASE, $, el, emptyState, fetchJson, formatCurrency, formatPct, mountChrome, navigate,
} = window.IR;

const ROTULO_STATUS = {
  oportunidade: 'Oportunidade',
  em_analise: 'Em análise',
  descartado: 'Descartado',
};

const state = { estudos: [] };

function mostrarErro(mensagem) {
  const caixa = $('erro');
  caixa.textContent = mensagem;
  caixa.hidden = !mensagem;
}

function filtros() {
  return {
    bairro: $('f-bairro').value.trim(),
    status: $('f-status').value,
    preco_min: $('f-preco-min').value,
    preco_max: $('f-preco-max').value,
  };
}

function cartao(rotulo, valor, meta) {
  const card = el('article', 'card');
  card.appendChild(el('span', 'card-label', rotulo));
  card.appendChild(el('strong', 'card-value', valor));
  if (meta) card.appendChild(el('span', 'card-meta', meta));
  return card;
}

function pintarKpis(estudos) {
  const alvo = $('kpis');
  alvo.textContent = '';
  // Descartado não entra: ele existe para não repetir a análise, não para
  // inflar o capital comprometido.
  const ativos = estudos.filter((e) => e.status !== 'descartado');
  const capital = ativos.reduce((soma, e) => soma + e.capital_empatado, 0);
  const lucro = ativos.reduce((soma, e) => soma + e.lucro_liquido, 0);
  const tirMedia = ativos.length
    ? ativos.reduce((soma, e) => soma + e.tir_anual, 0) / ativos.length
    : 0;

  alvo.appendChild(cartao('Estudos ativos', String(ativos.length), `${estudos.length} no total`));
  alvo.appendChild(cartao('Capital comprometido', formatCurrency(capital), 'Se todas as compras fecharem'));
  alvo.appendChild(cartao('Lucro projetado', formatCurrency(lucro), 'Soma dos estudos ativos'));
  alvo.appendChild(cartao('TIR média', formatPct(tirMedia * 100), 'Média simples, não ponderada'));
}

function pintarTabela(estudos) {
  const corpo = $('corpo-tabela');
  corpo.textContent = '';
  $('vazio').textContent = '';
  $('tabela').hidden = estudos.length === 0;

  if (!estudos.length) {
    $('vazio').appendChild(
      emptyState(
        'Nenhum estudo por aqui',
        'Simule um imóvel e clique em "Salvar estudo" para ele aparecer nesta lista.',
        [{ label: 'Abrir o simulador', href: '/flip' }],
      ),
    );
    return;
  }

  estudos.forEach((estudo) => {
    const tr = el('tr');
    const identidade = el('td');
    identidade.appendChild(el('strong', null, estudo.apelido || estudo.endereco));
    if (estudo.apelido) identidade.appendChild(el('span', 'card-meta', estudo.endereco));
    tr.appendChild(identidade);
    tr.appendChild(el('td', null, estudo.bairro || '—'));
    tr.appendChild(el('td', 'num', formatCurrency(estudo.preco_compra)));
    tr.appendChild(el('td', 'num', formatCurrency(estudo.obra_total)));
    tr.appendChild(el('td', 'num', formatCurrency(estudo.capital_empatado)));
    tr.appendChild(el('td', `num ${estudo.lucro_liquido >= 0 ? 'alta' : 'baixa'}`, formatCurrency(estudo.lucro_liquido)));
    tr.appendChild(el('td', 'num', formatPct(estudo.roi * 100)));
    tr.appendChild(el('td', 'num', formatPct(estudo.tir_anual * 100)));
    // Teto acima da proposta é margem; abaixo, é alerta.
    tr.appendChild(el('td', `num ${estudo.mao >= estudo.preco_compra ? 'alta' : 'baixa'}`, formatCurrency(estudo.mao)));
    tr.appendChild(el('td', null, ROTULO_STATUS[estudo.status] || estudo.status));

    const acoes = el('td');
    const abrir = el('button', 'btn btn-secondary btn-sm', 'Abrir');
    abrir.type = 'button';
    abrir.addEventListener('click', (evento) => navigate(evento, `/flip?id=${estudo.id}`));
    const excluir = el('button', 'btn btn-ghost btn-sm', 'Excluir');
    excluir.type = 'button';
    excluir.addEventListener('click', async () => {
      if (!window.confirm(`Excluir o estudo de ${estudo.apelido || estudo.endereco}?`)) return;
      const resposta = await fetch(`${API_BASE}/flips/${estudo.id}`, { method: 'DELETE' });
      if (!resposta.ok) {
        mostrarErro(`Não foi possível excluir: erro ${resposta.status}`);
        return;
      }
      await carregar();
    });
    acoes.append(abrir, excluir);
    tr.appendChild(acoes);
    corpo.appendChild(tr);
  });
}

async function carregar() {
  try {
    state.estudos = await fetchJson('/flips', filtros());
    mostrarErro('');
  } catch (erro) {
    mostrarErro(`Não foi possível carregar os estudos: ${erro.message}`);
    return;
  }
  pintarKpis(state.estudos);
  pintarTabela(state.estudos);
}

async function iniciar() {
  await mountChrome('flip');
  $('filtros').addEventListener('submit', (evento) => evento.preventDefault());
  ['f-bairro', 'f-status', 'f-preco-min', 'f-preco-max'].forEach((id) => {
    $(id).addEventListener('change', carregar);
  });
  await carregar();
}

iniciar();
