"""The Data Hub reader (arcium_signals/hub.py) against the local warehouse; skipped where there is none."""
import pytest

from arcium_signals import data, hub


def _warehouse():
    try:
        return not hub.catalog('oanda_practice').empty
    except BaseException:
        return False


pytestmark = pytest.mark.skipif(not _warehouse(), reason='no Data Hub warehouse reachable')


def test_bars_are_ordered_utc_ohlcv():
    df = hub.bars('EUR_USD', 'M1')
    assert list(df.columns) == ['open', 'high', 'low', 'close', 'volume']
    assert df.index.tz is None and df.index.is_monotonic_increasing and len(df) > 100
    assert (df['high'] >= df['low']).all()


def test_the_engine_loads_hub_bars():
    bars = data.load('hub', 'EUR_USD', 'M1')
    assert list(bars) == ['EUR_USD'] and len(bars['EUR_USD']) > 100


def test_unknown_things_say_so():
    with pytest.raises(SystemExit, match='no M7'):
        hub.bars('EUR_USD', 'M7')
    with pytest.raises(SystemExit, match='unknown source'):
        hub.bars('EUR_USD', 'M1', source='nowhere')


def test_the_reader_cannot_write():
    import psycopg
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        hub._query('CREATE TABLE arcium_signals_write_probe (x int)')
