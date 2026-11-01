"""Read-only access to the Arcium Data Hub warehouse (the Postgres the Data Hub records into).

Only the laptop and the server hold a copy of the warehouse, so this runs on one of those two.
It never writes. Where it connects, first found:
  ARCIUM_HUB_DATABASE_URL, DATABASE_URL, or DATABASE_URL in ../arciumsignals/.env.local

    from arcium_signals import hub
    hub.catalog('oanda_practice')                    # what's recorded: hooks, rows, first/last
    hub.bars('EUR_USD', 'M1')                        # OHLCV, UTC index (tz-naive)
    hub.bars('AAPL', 'D', source='yahoo')            # stocks/ETFs/FX/crypto daily+
    hub.series('fred', 'DGS10')                      # a FRED series (once the hub has a FRED key)
    hub.facts('AAPL')                                # SEC EDGAR financial figures, one column each
    hub.cot('099741')                                # CFTC positioning

The same from the command line: python -m arcium_signals hub list|bars|facts|series ...
"""
from __future__ import annotations

import json
import os
import re

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ENV = os.path.join(_HERE, '..', '..', 'arciumsignals', '.env.local')

# source -> (connection, keys tried in order); a key's params name the instrument and data rate
SOURCES = {
    'oanda': ('oanda_practice', ['candles']),
    'yahoo': ('yahoo', ['stocks.candles', 'etfs.candles', 'fx.candles', 'crypto.candles']),
    'webull': ('webull_stocks', ['stocks.candles', 'etfs.candles']),
    'webull_crypto': ('webull', ['crypto.candles']),
}


def database_url() -> str:
    url = os.environ.get('ARCIUM_HUB_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if url:
        return url
    try:
        with open(_APP_ENV, encoding='utf-8') as f:
            for line in f:
                m = re.match(r'\s*DATABASE_URL\s*=\s*(.+?)\s*$', line)
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    raise SystemExit('No warehouse database: set ARCIUM_HUB_DATABASE_URL (or DATABASE_URL in arciumsignals/.env.local)')


def _query(sql: str, args: tuple = ()) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(database_url(), row_factory=dict_row) as c:
        c.read_only = True   # every transaction on this connection is READ ONLY; the server refuses writes
        return c.execute(sql, args).fetchall()


def _utc_naive(ts: pd.Series) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(ts, utc=True)).tz_localize(None)


def catalog(connection: str | None = None, key: str | None = None) -> pd.DataFrame:
    """One row per recording hook: what it records, how many rows, and the span it covers."""
    rows = _query("""
        SELECT h.connection_name AS connection, h.key, h.params, h.mode, h.enabled, h.last_status,
               COUNT(s.series_id) AS streams, COALESCE(SUM(s.n_rows), 0) AS rows,
               MIN(s.first_ts) AS first, MAX(s.last_ts) AS last
        FROM wh_hooks h LEFT JOIN wh_series s ON s.hook_id = h.hook_id
        WHERE (%s::text IS NULL OR h.connection_name = %s) AND (%s::text IS NULL OR h.key = %s)
        GROUP BY h.hook_id ORDER BY 1, 2, rows DESC""", (connection, connection, key, key))
    df = pd.DataFrame(rows)
    if not df.empty:
        df['params'] = df['params'].map(lambda p: json.dumps(p, sort_keys=True))
    return df


def _ohlcv_series(connection: str, keys: list[str], instrument: str, rate: str) -> int | None:
    rows = _query("""
        SELECT s.series_id FROM wh_series s JOIN wh_hooks h ON h.hook_id = s.hook_id
        WHERE h.connection_name = %s AND h.key = ANY(%s) AND s.store = 'ohlcv'
          AND (h.params->>'instrument' = %s OR h.params->>'ticker' = %s) AND h.params->>'data_rate' = %s
        ORDER BY s.n_rows DESC LIMIT 1""", (connection, keys, instrument, instrument, rate))
    return rows[0]['series_id'] if rows else None


def bars(instrument: str, rate: str = 'M1', source: str = 'oanda', start=None, end=None) -> pd.DataFrame:
    """OHLCV bars, oldest first, index = UTC time (tz-naive, as the engine's bars are)."""
    if source not in SOURCES:
        raise SystemExit(f'unknown source {source!r}: one of {sorted(SOURCES)}')
    connection, keys = SOURCES[source]
    sid = _ohlcv_series(connection, keys, instrument, rate)
    if sid is None:
        raise SystemExit(f'no {rate} bars for {instrument} from {source}: see python -m arcium_signals hub list {source}')
    rows = _query("""SELECT ts, open, high, low, close, volume FROM wh_ohlcv
                     WHERE series_id = %s AND (%s::timestamptz IS NULL OR ts >= %s) AND (%s::timestamptz IS NULL OR ts < %s)
                     ORDER BY ts""", (sid, start, start, end, end))
    df = pd.DataFrame(rows, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df.index = _utc_naive(df.pop('ts'))
    df.index.name = 'time'
    return df.astype(float).fillna({'volume': 0.0})


def _values(connection: str, key: str, param: str, value: str) -> pd.DataFrame:
    rows = _query("""
        SELECT s.part, s.field, v.ts, v.value FROM wh_series s
        JOIN wh_hooks h ON h.hook_id = s.hook_id JOIN wh_values v ON v.series_id = s.series_id
        WHERE h.connection_name = %s AND h.key = %s AND h.params->>%s = %s ORDER BY v.ts""",
                  (connection, key, param, value))
    df = pd.DataFrame(rows, columns=['part', 'field', 'ts', 'value'])
    if df.empty:
        return df
    df['ts'] = _utc_naive(df['ts'])
    return df


def series(source: str, series_id: str) -> pd.Series:
    """A single economic series, e.g. series('fred', 'DGS10')."""
    if source != 'fred':
        raise SystemExit("series(): source 'fred'")
    df = _values('fred', 'series', 'series_id', series_id)
    if df.empty:
        raise SystemExit(f'no FRED {series_id} in the warehouse (the hub needs a FRED key to record FRED)')
    df = df[df['field'].isin(['', 'value'])] if 'value' in set(df['field']) else df
    return df.groupby('ts')['value'].last().rename(series_id)


def facts(ticker: str) -> pd.DataFrame:
    """SEC EDGAR figures: one row per period end, one column per concept (quarterly and .annual)."""
    df = _values('sec_edgar', 'facts', 'ticker', ticker)
    if df.empty:
        raise SystemExit(f'no EDGAR figures for {ticker}')
    df = df[df['field'] == 'value']
    return df.pivot_table(index='ts', columns='part', values='value', aggfunc='last').sort_index()


def cot(market_code: str) -> pd.DataFrame:
    """CFTC Commitments of Traders for one market: one column per position field."""
    df = _values('cftc_cot', 'positions', 'market_code', market_code)
    if df.empty:
        raise SystemExit(f'no COT data for {market_code}')
    df['col'] = (df['part'] + '.' + df['field']).str.strip('.')
    return df.pivot_table(index='ts', columns='col', values='value', aggfunc='last').sort_index()


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog='python -m arcium_signals hub', description='Read the Data Hub warehouse (read-only)')
    sub = ap.add_subparsers(dest='what', required=True)
    p = sub.add_parser('list', help='what is recorded'); p.add_argument('connection', nargs='?'); p.add_argument('--key')
    p = sub.add_parser('bars'); p.add_argument('instrument'); p.add_argument('--rate', default='M1')
    p.add_argument('--source', default='oanda', choices=sorted(SOURCES)); p.add_argument('--start'); p.add_argument('--end')
    p.add_argument('--csv', help='write the bars to this CSV')
    p = sub.add_parser('facts'); p.add_argument('ticker'); p.add_argument('--csv')
    p = sub.add_parser('series'); p.add_argument('series_id'); p.add_argument('--csv')
    a = ap.parse_args(argv)
    if a.what == 'list':
        df = catalog(a.connection, a.key)
        with pd.option_context('display.max_rows', 500, 'display.width', 200, 'display.max_colwidth', 70):
            print(df.drop(columns=['enabled']).to_string(index=False) if not df.empty else 'nothing recorded')
        return 0
    df = (bars(a.instrument, a.rate, a.source, a.start, a.end) if a.what == 'bars'
          else facts(a.ticker) if a.what == 'facts' else series('fred', a.series_id).to_frame())
    if a.csv:
        df.to_csv(a.csv)
        print(f'{len(df)} rows -> {a.csv}')
    else:
        print(df.tail(10).to_string())
        print(f'{len(df)} rows, {df.index[0]} .. {df.index[-1]}' if len(df) else 'no rows')
    return 0
