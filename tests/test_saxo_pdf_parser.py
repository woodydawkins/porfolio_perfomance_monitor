from src.ingest.saxo_pdf_parser import (
    RawRow,
    enrich_transactions_with_instruments,
    parse_holdings_rows,
    parse_saxo_sections,
    parse_transaction_rows,
    split_unresolved_transactions,
    to_issue_records,
)


def _mock_holdings_rows():
    return [
        RawRow(
            page=2,
            text=(
                "Instrument=Intel Corp.; Symbol=INTC:xnas; ISIN=US4581401001; "
                "Product=Stock; Currency=USD"
            ),
        ),
        RawRow(
            page=2,
            text=(
                "Instrument=Alibaba Group Holding Ltd - ADR; Symbol=BABA:xnys; "
                "ISIN=US01609W1027; Product=ADR; Currency=USD"
            ),
        ),
    ]


def _mock_transaction_rows():
    return [
        RawRow(
            page=7,
            text=(
                "TradeDate=2026-04-11; ValueDate=2026-04-14; TradeID=T-BUY-001; "
                "Account=12644841; Broker=Saxo; Product=Stock; "
                "Instrument=Intel Corp.; Transaction=BUY; OpenClose=OPEN; "
                "Quantity=10; Price=34.5; ConversionRate=1.0; RealizedPnL=0; "
                "BookedAmount=-345.0; BookedCosts=-1.0; TotalCosts=-1.0"
            ),
        ),
        RawRow(
            page=8,
            text=(
                "TradeDate=2026-04-12; ValueDate=2026-04-15; TradeID=T-SELL-002; "
                "Account=12644841; Broker=Saxo; Product=ADR; "
                "Instrument=Alibaba Group Holding Ltd - ADR; Transaction=SELL; "
                "OpenClose=CLOSE; Quantity=5; Price=76.0; ConversionRate=1.0; "
                "RealizedPnL=12.2; BookedAmount=380.0; BookedCosts=-1.5; TotalCosts=-1.5"
            ),
        ),
        RawRow(
            page=8,
            text=(
                "TradeDate=2026-04-13; ValueDate=2026-04-16; TradeID=T-UNK-003; "
                "Account=12644841; Broker=Saxo; Product=Stock; Instrument=Unknown Co.; "
                "Transaction=BUY; OpenClose=OPEN; Quantity=2; Price=10; ConversionRate=1.0; "
                "RealizedPnL=0; BookedAmount=-20.0; BookedCosts=-0.2; TotalCosts=-0.2"
            ),
        ),
    ]


def test_parse_holdings_rows_extracts_symbol_components():
    instruments = parse_holdings_rows(_mock_holdings_rows())

    assert len(instruments) == 2
    assert instruments[0].instrument_name == "Intel Corp."
    assert instruments[0].symbol_raw == "INTC:xnas"
    assert instruments[0].ticker == "INTC"
    assert instruments[0].exchange == "xnas"


def test_enrichment_resolves_known_and_keeps_unknown_unresolved():
    instruments = parse_holdings_rows(_mock_holdings_rows())
    transactions = parse_transaction_rows(_mock_transaction_rows())

    enriched = enrich_transactions_with_instruments(transactions, instruments)
    resolved, unresolved = split_unresolved_transactions(enriched)

    assert len(resolved) == 2
    assert len(unresolved) == 1
    assert resolved[0].ticker == "INTC"
    assert resolved[1].ticker == "BABA"
    assert unresolved[0].instrument_name == "Unknown Co."


def test_parse_saxo_sections_returns_issue_ready_unresolved_rows():
    result = parse_saxo_sections(_mock_holdings_rows(), _mock_transaction_rows())

    assert len(result.instruments) == 2
    assert len(result.transactions) == 2
    assert len(result.unresolved_transactions) == 1

    unresolved_tx = parse_transaction_rows(_mock_transaction_rows())
    unresolved_tx = enrich_transactions_with_instruments(unresolved_tx, parse_holdings_rows(_mock_holdings_rows()))
    _, unresolved_only = split_unresolved_transactions(unresolved_tx)
    issue_records = to_issue_records(unresolved_only)
    assert issue_records[0]["trade_id"] == "T-UNK-003"
