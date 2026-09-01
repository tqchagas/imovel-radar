"""Plain-text opportunity alerts and the SMTP adapter that delivers them."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

from app.core.config import settings
from app.models.market_comparable import MarketComparable

CONFIDENCE_LABELS = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}
REFERENCE_LABELS = {
    "endereco_exato": "endereço exato",
    "bairro_area": "bairro e faixa de área",
    "bairro_amplo": "bairro amplo",
}
SOURCE_LABELS = {"quintoandar": "QuintoAndar", "vivareal": "VivaReal"}


@dataclass(frozen=True)
class EmailMessage:
    subject: str
    body: str
    recipients: tuple[str, ...]


def _number(value: float, digits: int = 2) -> str:
    formatted = f"{value:,.{digits}f}"
    return formatted.replace(",", "@").replace(".", ",").replace("@", ".")


def _money(value: float | None) -> str:
    return "—" if value is None else f"R$ {_number(float(value))}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{_number(float(value) * 100, 1)}%"


def _date(value) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _address(listing: MarketComparable) -> str:
    street = ", ".join(part for part in (listing.rua, listing.numero) if part)
    return street or listing.bairro or listing.listing_id


def render_opportunity_email(
    listing: MarketComparable, recipients: list[str] | tuple[str, ...]
) -> EmailMessage:
    """One alert per listing, with every number the reader needs to judge it."""
    address = _address(listing)
    source = SOURCE_LABELS.get(listing.source, listing.source)
    confidence = CONFIDENCE_LABELS.get(listing.confianca or "", listing.confianca or "—")
    subject = (
        f"{_pct(listing.desconto_pct)} abaixo do estimado — "
        f"{listing.bairro or listing.cidade or ''} — {address}".strip()
    )
    lines = [
        f"{address} — {listing.bairro or ''} ({listing.cidade or ''})".strip(),
        f"Fonte: {source}",
        f"Tipo: {listing.tipo_imovel or '—'}"
        + (f" · {_number(float(listing.area_util_m2), 0)} m²" if listing.area_util_m2 else ""),
        "",
        f"Preço anunciado: {_money(listing.preco_total)}",
        f"Preço estimado: {_money(listing.preco_estimado)}",
        f"Desconto: {_pct(listing.desconto_pct)} ({_money(listing.desconto_reais)})",
        "",
        f"Confiança: {confidence}",
        f"Referência: {REFERENCE_LABELS.get(listing.tipo_referencia or '', '—')}",
        f"Amostra: {listing.amostra_count or 0} ITBIs entre "
        f"{_date(listing.referencia_data_inicio)} e {_date(listing.referencia_data_fim)}",
        "",
    ]
    if listing.oportunidade_motivo:
        lines.extend(listing.oportunidade_motivo.split("\n"))
        lines.append("")
    if listing.url:
        lines.append(f"Anúncio: {listing.url}")
    lines.append(
        "Estimativa estatística a partir de ITBI declarado; não constitui avaliação."
    )
    return EmailMessage(subject=subject, body="\n".join(lines), recipients=tuple(recipients))


def send_email(message: EmailMessage) -> None:
    """Deliver through the configured SMTP server."""
    if not settings.smtp_host:
        raise RuntimeError("smtp_host is not configured")
    if not message.recipients:
        raise RuntimeError("no recipients configured")

    mime = MimeMessage()
    mime["Subject"] = f"{settings.smtp_subject_prefix} {message.subject}".strip()
    mime["From"] = settings.smtp_from or settings.smtp_user
    mime["To"] = ", ".join(message.recipients)
    mime.set_content(message.body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(mime)
