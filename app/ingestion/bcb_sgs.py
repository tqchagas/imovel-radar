"""A série de um índice publicada pelo Banco Central (SGS).

O SGS entrega a variação percentual do mês como texto, com o dia fixado em 01 e
sinal quando o mês fecha em deflação. Este módulo só traduz isso em objetos: não
conhece banco, e quem grava é `services/monetary_index_sync`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.core import http_client

CODIGO_IPCA = 433
BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"


@dataclass(frozen=True)
class IndexPoint:
    competencia: date
    variacao_pct: float


def parse_series(payload: list[dict]) -> list[IndexPoint]:
    pontos = [
        IndexPoint(
            competencia=datetime.strptime(item["data"], "%d/%m/%Y").date(),
            variacao_pct=float(item["valor"]),
        )
        for item in payload
    ]
    return sorted(pontos, key=lambda p: p.competencia)


def fetch_series(
    codigo: int = CODIGO_IPCA, desde: date = date(2008, 1, 1)
) -> list[IndexPoint]:
    """Baixa a série inteira desde `desde`.

    São ~223 pontos para 2008-2026: baixar tudo e reconciliar sai mais barato do
    que pedir só o que falta e ficar cego para revisão de mês já publicado — o
    IBGE revisa, e o SGS republica.
    """
    url = BASE_URL.format(codigo=codigo)
    resposta = http_client.request(
        "GET",
        f"{url}?formato=json&dataInicial={desde.strftime('%d/%m/%Y')}",
        timeout=60,
    )
    resposta.raise_for_status()
    return parse_series(resposta.json())
