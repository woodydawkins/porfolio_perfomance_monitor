"""Saxo PDF parser scaffolding for holdings + transactions workflows.

This module intentionally avoids real PDF extraction. It expects pre-extracted,
mockable text rows from two logical sections in a future full report PDF:
- Holdings section (instrument master source)
- Transactions section (trade rows source)

The parser pipeline is:
1) parse_holdings_rows -> instrument master rows
2) parse_transaction_rows -> extracted transaction rows
3) enrich_transactions_with_instruments -> map transactions using holdings master
4) split_unresolved_transactions -> separate unresolved rows for issue handling
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RawRow:
    """A normalized text row extracted from a specific PDF section/page."""

    page: int
    text: str


@dataclass(frozen=True)
class InstrumentMasterRow:
    instrument_name: str
    symbol_raw: str
    ticker: str
    exchange: str
    isin: str
    product: str
    instrument_currency: str
    source_section: str
    source_page: int
    source_row_text: str
    confidence: float
    note: str


@dataclass(frozen=True)
class TransactionRow:
    trade_date: str
    value_date: str
    trade_id: str
    account_no: str
    broker: str
    product: str
    instrument_name: str
    symbol_raw: str
    ticker: str
    exchange: str
    isin: str
    instrument_currency: str
    transaction_type: str
    open_close: str
    quantity: float
    price: float
    conversion_rate: float
    realized_pnl: float
    booked_amount: float
    booked_costs: float
    total_costs: float
    source_page: int
    source_row_text: str
    confidence: float
    note: str


@dataclass(frozen=True)
class ParseResult:
    instruments: list[dict]
    transactions: list[dict]
    unresolved_transactions: list[dict]


def _parse_symbol(symbol_raw: str) -> tuple[str, str, float, str]:
    """Extract ticker/exchange from Saxo symbol format like 'INTC:xnas'."""

    symbol_clean = symbol_raw.strip().lower()
    if ":" not in symbol_clean:
        return "", "", 0.3, "symbol missing expected '<ticker>:<exchange>' pattern"

    ticker, exchange = symbol_clean.split(":", 1)
    if not ticker or not exchange:
        return "", "", 0.3, "symbol missing ticker or exchange part"

    return ticker.upper(), exchange.lower(), 0.95, "parsed from holdings symbol"


def parse_holdings_rows(rows: Sequence[RawRow]) -> list[InstrumentMasterRow]:
    """Parse holdings-section rows into instrument master records.

    Expected keys in row text (semicolon-separated for mock fixtures):
      Instrument=...; Symbol=...; ISIN=...; Product=...; Currency=...
    """

    parsed: list[InstrumentMasterRow] = []

    for row in rows:
        fields = _parse_key_value_row(row.text)
        symbol_raw = fields.get("symbol", "")
        ticker, exchange, symbol_confidence, symbol_note = _parse_symbol(symbol_raw)

        parsed.append(
            InstrumentMasterRow(
                instrument_name=fields.get("instrument", ""),
                symbol_raw=symbol_raw,
                ticker=ticker,
                exchange=exchange,
                isin=fields.get("isin", ""),
                product=fields.get("product", ""),
                instrument_currency=fields.get("currency", ""),
                source_section="holdings",
                source_page=row.page,
                source_row_text=row.text,
                confidence=symbol_confidence,
                note=symbol_note,
            )
        )

    return parsed


def parse_transaction_rows(rows: Sequence[RawRow]) -> list[TransactionRow]:
    """Parse transactions-section rows into transaction records.

    Expected keys in row text (semicolon-separated for mock fixtures):
      TradeDate=...; ValueDate=...; TradeID=...; Account=...; Broker=...;
      Product=...; Instrument=...; Transaction=BUY/SELL; OpenClose=...;
      Quantity=...; Price=...; ConversionRate=...; RealizedPnL=...;
      BookedAmount=...; BookedCosts=...; TotalCosts=...

    Note: symbol/ticker/exchange/isin/currency are intentionally left blank here;
    enrichment is performed from holdings-derived instrument master mapping.
    """

    parsed: list[TransactionRow] = []

    for row in rows:
        fields = _parse_key_value_row(row.text)

        parsed.append(
            TransactionRow(
                trade_date=fields.get("tradedate", ""),
                value_date=fields.get("valuedate", ""),
                trade_id=fields.get("tradeid", ""),
                account_no=fields.get("account", ""),
                broker=fields.get("broker", "Saxo"),
                product=fields.get("product", ""),
                instrument_name=fields.get("instrument", ""),
                symbol_raw="",
                ticker="",
                exchange="",
                isin="",
                instrument_currency="",
                transaction_type=fields.get("transaction", ""),
                open_close=fields.get("openclose", ""),
                quantity=float(fields.get("quantity", "0") or "0"),
                price=float(fields.get("price", "0") or "0"),
                conversion_rate=float(fields.get("conversionrate", "1") or "1"),
                realized_pnl=float(fields.get("realizedpnl", "0") or "0"),
                booked_amount=float(fields.get("bookedamount", "0") or "0"),
                booked_costs=float(fields.get("bookedcosts", "0") or "0"),
                total_costs=float(fields.get("totalcosts", "0") or "0"),
                source_page=row.page,
                source_row_text=row.text,
                confidence=0.8,
                note="parsed from transactions section; awaiting instrument enrichment",
            )
        )

    return parsed


def enrich_transactions_with_instruments(
    transactions: Sequence[TransactionRow],
    instruments: Sequence[InstrumentMasterRow],
) -> list[TransactionRow]:
    """Enrich transaction rows with holdings-derived instrument mapping only."""

    master_by_name = {
        instrument.instrument_name.strip().lower(): instrument for instrument in instruments
    }

    enriched: list[TransactionRow] = []

    for tx in transactions:
        key = tx.instrument_name.strip().lower()
        matched = master_by_name.get(key)

        if not matched:
            enriched.append(
                TransactionRow(
                    **{
                        **asdict(tx),
                        "confidence": 0.2,
                        "note": "unresolved instrument; no holdings mapping match",
                    }
                )
            )
            continue

        enriched.append(
            TransactionRow(
                **{
                    **asdict(tx),
                    "symbol_raw": matched.symbol_raw,
                    "ticker": matched.ticker,
                    "exchange": matched.exchange,
                    "isin": matched.isin,
                    "instrument_currency": matched.instrument_currency,
                    "confidence": min(1.0, tx.confidence + 0.15),
                    "note": f"enriched from holdings mapping on page {matched.source_page}",
                }
            )
        )

    return enriched


def split_unresolved_transactions(
    transactions: Sequence[TransactionRow],
) -> tuple[list[TransactionRow], list[TransactionRow]]:
    """Split transactions into resolved and unresolved groups for issue files."""

    resolved: list[TransactionRow] = []
    unresolved: list[TransactionRow] = []

    for tx in transactions:
        if tx.ticker and tx.symbol_raw and tx.isin:
            resolved.append(tx)
        else:
            unresolved.append(tx)

    return resolved, unresolved


def parse_saxo_sections(
    holdings_rows: Sequence[RawRow],
    transaction_rows: Sequence[RawRow],
) -> ParseResult:
    """End-to-end parse for pre-extracted section rows.

    This function intentionally does not extract from PDF bytes/files; it only
    works on supplied text rows to keep the integration testable without the
    full report PDF.
    """

    instruments = parse_holdings_rows(holdings_rows)
    extracted_transactions = parse_transaction_rows(transaction_rows)
    enriched = enrich_transactions_with_instruments(extracted_transactions, instruments)
    resolved, unresolved = split_unresolved_transactions(enriched)

    return ParseResult(
        instruments=[asdict(row) for row in instruments],
        transactions=[asdict(row) for row in resolved],
        unresolved_transactions=[asdict(row) for row in unresolved],
    )


def _parse_key_value_row(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for piece in text.split(";"):
        if "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def to_issue_records(unresolved_rows: Iterable[TransactionRow]) -> list[dict[str, str]]:
    """Convert unresolved transactions to issue file records."""

    issues = []
    for row in unresolved_rows:
        issues.append(
            {
                "trade_id": row.trade_id,
                "instrument_name": row.instrument_name,
                "source_page": str(row.source_page),
                "reason": row.note,
                "source_row_text": row.source_row_text,
            }
        )
    return issues
