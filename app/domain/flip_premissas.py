"""Os preços que alimentam o simulador de flip.

Ficam num JSON versionado, e não numa tabela: reajuste de insumo é decisão
rara, e o histórico do git conta melhor essa história que uma coluna
`updated_at`. Um estudo salvo guarda a cópia dos valores que usou, então mudar
o arquivo não mexe em conta velha.
"""

import json
from dataclasses import dataclass
from pathlib import Path

ARQUIVO_PADRAO = Path(__file__).resolve().parent.parent / "config" / "flip_premissas.json"

CHAVES_OBRIGATORIAS = frozenset(
    {
        "taco",
        "pintura_seca",
        "banho_piso",
        "banho_azulejo_box",
        "banho_massa_acrilica",
        "banho_bancada",
        "banho_louca",
        "banho_box_espelho",
        "banho_mao_obra",
        "banho_marcenaria",
        "coz_piso",
        "coz_azulejo",
        "coz_massa_acrilica",
        "coz_bancada",
        "coz_mao_obra",
        "coz_marcenaria",
        "eletrica_led",
        "portas",
        "cacamba",
        "eletrica_completa",
        "hidraulica_completa_banheiro",
        "hidraulica_completa_cozinha",
        "contingencia_pct",
        "proporcao_taco",
        "itbi_pct",
        "registro_pct",
        "corretagem_pct",
        "ir_ganho_capital_pct",
        "meses_carrego_padrao",
        "condominio_mensal",
        "iptu_mensal",
        "consumo_mensal",
        "fator_saida_padrao",
        "roi_alvo_mao",
    }
)


class PremissaAusenteError(KeyError):
    """Premissa pedida que não existe. Carrega o nome da chave na mensagem."""


@dataclass(frozen=True)
class Premissa:
    chave: str
    rotulo: str
    unidade: str
    valor: float
    fonte: str = "Estimativa inicial; confirmar com orçamento local"


@dataclass(frozen=True)
class Premissas:
    itens: tuple[Premissa, ...]

    def valor(self, chave: str) -> float:
        for item in self.itens:
            if item.chave == chave:
                return item.valor
        raise PremissaAusenteError(f"premissa desconhecida: {chave}")

    def como_valores(self) -> dict[str, float]:
        """Preços numéricos; útil para cálculos e snapshots antigos."""
        return {item.chave: item.valor for item in self.itens}

    def como_snapshot(self) -> dict:
        """Congela preço e identificação da fonte para exibição histórica."""
        return {
            **self.como_valores(),
            "__metadados__": {
                item.chave: {
                    "rotulo": item.rotulo,
                    "unidade": item.unidade,
                    "fonte": item.fonte,
                }
                for item in self.itens
            },
        }


def _conferir(itens: tuple[Premissa, ...]) -> None:
    faltando = sorted(CHAVES_OBRIGATORIAS - {item.chave for item in itens})
    if faltando:
        raise PremissaAusenteError(f"premissas faltando: {', '.join(faltando)}")


def carregar_premissas(caminho: Path | None = None) -> Premissas:
    dados = json.loads((caminho or ARQUIVO_PADRAO).read_text(encoding="utf-8"))
    itens = tuple(
        Premissa(
            chave=linha["chave"],
            rotulo=linha["rotulo"],
            unidade=linha["unidade"],
            valor=float(linha["valor"]),
            fonte=linha.get("fonte", "Estimativa inicial; confirmar com orçamento local"),
        )
        for linha in dados
    )
    _conferir(itens)
    return Premissas(itens=itens)


def premissas_de_valores(valores: dict) -> Premissas:
    """Reconstrói premissas a partir do snapshot de um estudo salvo.

    Snapshots antigos continham só valores; neles a fonte histórica é
    explicitamente desconhecida, não atribuída retroativamente à tabela atual.
    """
    metadados = valores.get("__metadados__", {})
    conhecidos = {item.chave: item for item in carregar_premissas().itens}
    itens = tuple(
        Premissa(
            chave=chave,
            rotulo=metadados.get(chave, {}).get("rotulo", conhecidos[chave].rotulo if chave in conhecidos else chave),
            unidade=metadados.get(chave, {}).get("unidade", conhecidos[chave].unidade if chave in conhecidos else ""),
            valor=float(valor),
            fonte=metadados.get(chave, {}).get("fonte", "Fonte histórica não registrada"),
        )
        for chave, valor in sorted(valores.items()) if not chave.startswith("__")
    )
    _conferir(itens)
    return Premissas(itens=itens)
