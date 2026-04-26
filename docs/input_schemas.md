# Saxo Full Transaction + Balance Parser Schemas

This document defines the parser-ready schemas for the **future full Saxo report**.

> Important: The repository currently contains only parser scaffolding and mocked tests.
> Real PDF extraction is intentionally not executed yet.

Expected future input path:

- `data/raw_trades/samples/TransactionBalance_12644841_2026-01-01_2026-04-24.pdf`

## Workflow

1. Parse **Holdings** section into an instrument master.
2. Parse **Transactions** section into extracted trade rows.
3. Enrich extracted transactions using holdings-derived mapping.
4. Split unresolved instruments into a dedicated unresolved issues file.

## Instrument master output schema

| Field | Type | Description |
|---|---|---|
| instrument_name | string | Instrument name as shown in holdings. |
| symbol_raw | string | Raw Saxo symbol (example: `INTC:xnas`). |
| ticker | string | Ticker parsed from `symbol_raw`; no guessing. |
| exchange | string | Exchange suffix parsed from `symbol_raw`. |
| isin | string | ISIN from holdings row. |
| product | string | Product type (e.g., Stock, ADR). |
| instrument_currency | string | Instrument currency from holdings row. |
| source_section | string | Source section tag (`holdings`). |
| source_page | integer | PDF page number where row was found. |
| source_row_text | string | Original row text snapshot used for parsing. |
| confidence | float | Parse confidence score. |
| note | string | Parsing notes / warnings. |

## Extracted transactions output schema

| Field | Type | Description |
|---|---|---|
| trade_date | string | Trade date parsed from transaction row. |
| value_date | string | Value/settlement date from transaction row. |
| trade_id | string | Trade identifier from transaction row. |
| account_no | string | Account identifier. |
| broker | string | Broker value (defaults to `Saxo` if missing). |
| product | string | Product type from transaction row. |
| instrument_name | string | Instrument text from transaction row. |
| symbol_raw | string | Enriched from holdings mapping. |
| ticker | string | Enriched from holdings mapping. |
| exchange | string | Enriched from holdings mapping. |
| isin | string | Enriched from holdings mapping. |
| instrument_currency | string | Enriched from holdings mapping. |
| transaction_type | string | BUY / SELL etc. |
| open_close | string | Open/Close indicator when present. |
| quantity | float | Parsed transaction quantity. |
| price | float | Parsed transaction price. |
| conversion_rate | float | FX conversion rate. |
| realized_pnl | float | Realized PnL value if present. |
| booked_amount | float | Booked amount. |
| booked_costs | float | Booked costs. |
| total_costs | float | Total costs. |
| source_page | integer | PDF page number where row was found. |
| source_row_text | string | Original row text snapshot used for parsing. |
| confidence | float | Parse/enrichment confidence score. |
| note | string | Parsing/enrichment notes. |

## Unresolved instruments / issue output

Transactions that cannot be matched to holdings-derived instrument master are kept in a separate unresolved file.

Minimum issue fields:

- `trade_id`
- `instrument_name`
- `source_page`
- `reason`
- `source_row_text`

## Guardrails

- No core holdings engine changes.
- No valuation/Excel report logic changes.
- No external APIs.
- No ticker guessing.
- Holdings-derived mapping is the first and only enrichment source in this parser stage.
