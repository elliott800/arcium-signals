"""Test unit: slim engine, stats and Signal shim on synthetic bars; components when vendor/ is installed.

    python -m pytest -q
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcium_signals import VENDOR, engine, stats  # noqa: E402
from arcium_signals.signal_shim import Signal, _Instrument  # noqa: E402

INSTALLED = os.path.isfile(os.path.join(VENDOR, 'INSTALLED.json'))


def closes(values, freq='1min'):
    return pd.Series(values, index=pd.date_range('2026-05-25', periods=len(values), freq=freq), dtype=float)


def test_position_trades_from_the_next_bar_with_costs():
    close = closes([100, 101, 102, 101])
    bt = engine.backtest(close, pd.Series([1, 1, -1, 0], index=close.index), spread_bps=10)
    # bar0 long earns 100->101; bar1 long earns 101->102; bar2 short earns 102->101; bar3 flat
    assert bt['gross'].tolist() == pytest.approx([0.01, 1 / 101, 1 / 102, 0.0])
    # cost on each change of position: open 1, flip 2, close 1 -> 4 x 10 bps
    assert bt['cost'].sum() == pytest.approx(4 * 0.001)
    assert bt['equity'].iloc[-1] == pytest.approx(1 + bt['gross'].sum() - 0.004)


def test_trades_split_on_side_changes():
    close = closes([1, 1, 1, 1, 1, 1])
    bt = engine.backtest(close, pd.Series([0, 1, 1, -1, 0, 1], index=close.index), spread_bps=0)
    tr = engine.trades(bt)
    assert tr[['side', 'bars']].values.tolist() == [[1, 2], [-1, 1], [1, 1]]


def test_perfect_foresight_scores_well_and_ic_is_positive():
    rng = np.random.default_rng(1)
    close = closes(100 * np.exp(np.cumsum(rng.normal(0, 0.001, 2000))))
    future = np.sign(close.shift(-1) - close).fillna(0)
    s = stats.summary(*_run(close, future), close, None, future)
    assert s['gross_sharpe'] > 10 and s['hit_rate'] == 1.0 and s['ic_1'] > 0.8   # rank IC of a 3-valued sign tops out below 1


def _run(close, sig, bps=0.0):
    bt = engine.backtest(close, sig, bps)
    return bt, engine.trades(bt)


def test_bars_per_year_from_spacing():
    assert stats.bars_per_year(closes([1] * 10, freq='1min').index) == pytest.approx(260 * 1440)
    assert stats.bars_per_year(closes([1] * 10, freq='1D').index) == pytest.approx(260)


class _Up(Signal):
    def setup(self):
        self.space = {'lag': [1, 9, 1]}

    def algorithm(self):
        c = self.data['levels']['close']
        return 1 if c.iloc[-1] > c.iloc[-1 - self.params['lag']] else -1


def test_shim_reveals_bars_one_at_a_time():
    seen = []

    class Spy(_Up):
        def algorithm(self):
            seen.append(len(self.data['levels']))
            return super().algorithm()

    levels = pd.DataFrame({'close': [1, 2, 3, 2, 1, 2, 3, 4, 5, 6, 7, 8]})
    s = Spy(_Instrument('X', levels))
    assert s.default_params() == {'lag': 5}
    out = s.produce_signal()
    assert seen == list(range(6, 13))              # never more bars than "now"
    assert out.index.tolist() == list(range(5, 12))
    assert len(s.data['levels']) == 12             # full bars restored


@pytest.mark.skipif(not INSTALLED, reason='run python install.py first')
@pytest.mark.parametrize('kind', ['feature', 'alpha', 'sampler'])
def test_every_installed_component_runs(kind):
    from arcium_signals import components
    from arcium_signals.__main__ import analyse
    comps = {n: c for n, c in components.discover()[kind].items() if not isinstance(c, str)}
    assert comps
    for name in comps:
        init = {'instrument_b': 'GBP_USD'} if name == 'cross_instrument' else None
        rep = analyse(kind, name, init=init)
        s = rep['summary']
        assert s['bars'] > 1000 and s['trades'] > 0, name
        assert len(rep['equity']) == s['bars']


@pytest.mark.skipif(not INSTALLED, reason='run python install.py first')
def test_install_copies_only_allowed_files():
    import json
    rec = json.load(open(os.path.join(VENDOR, 'INSTALLED.json')))
    allowed = ('seed/features/', 'seed/event_samplers/', 'seed/alpha_models/', 'seed/indicators/',
               'super_classes/feature_base.py', 'primary_classifier_classes/deprado_ml.py', 'demo/')
    assert all(f.startswith(allowed) for f in rec['files'])
    dml = open(os.path.join(VENDOR, 'primary_classifier_classes', 'deprado_ml.py')).read()
    assert 'def getVol' in dml and 'def metaGetEvents' not in dml   # only the extracted helpers
