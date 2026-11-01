"""
arcium-signals test unit.

    python -m arcium_signals list
    python -m arcium_signals run feature momentum --params mom_window=10
    python -m arcium_signals run feature cross_instrument --init instrument_b=GBP_USD
    python -m arcium_signals run alpha dual_ma --params ma1=10,ma2=50 --instrument GBP_USD
    python -m arcium_signals run sampler cusum --side reversal --hold 10
    python -m arcium_signals run feature volatility --data bars.csv --out report.json

Options for run:
    --data demo|<csv>      bars (default: the installed canned demo bars)
    --instrument NAME      default EUR_USD
    --params k=v,...       component parameters (default: its defaults / middle of its range)
    --init k=v,...         constructor arguments (cross_instrument's instrument_b, a sampler's threshold)
    --spread-bps N         cost per change of position (default 1.0)
    --map z|sign           feature -> signal mapping (default z: rolling z-score / 2)
    --z-window N           feature z-score window (default 100)
    --invert               flip the signal
    --side momentum|reversal, --hold N, --side-window N     sampler signal rules
    --out FILE             also write the full report (summary, trades, equity) as JSON
"""
from __future__ import annotations

import argparse
import json
import sys

from arcium_signals import components, data, engine, stats


def _kv(text: str | None) -> dict:
    out = {}
    for part in filter(None, (text or '').split(',')):
        k, _, v = part.partition('=')
        try:
            out[k.strip()] = int(v)
        except ValueError:
            try:
                out[k.strip()] = float(v)
            except ValueError:
                out[k.strip()] = v.strip()
    return out


def analyse(kind, name, source='demo', instrument='EUR_USD', params=None, init=None, opts=None, spread_bps=1.0) -> dict:
    bars = data.load(source, instrument)
    signal, raw, details = components.run_component(kind, name, bars, instrument, params, init, opts)
    close = bars[instrument]['close']
    bt = engine.backtest(close, signal, spread_bps)
    tr = engine.trades(bt)
    return {'component': {'kind': kind, 'name': name, **details}, 'instrument': instrument,
            'data': source, 'spread_bps': spread_bps,
            'period': [str(close.index[0]), str(close.index[-1])],
            'summary': stats.summary(bt, tr, close, raw, signal),
            'trades': tr.astype({'entry': str, 'exit': str}).to_dict('records'),
            'equity': {str(t): round(float(v), 6) for t, v in bt['equity'].items()}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    r = sub.add_parser('run')
    r.add_argument('kind', choices=components.KINDS)
    r.add_argument('name')
    r.add_argument('--data', default='demo')
    r.add_argument('--instrument', default='EUR_USD')
    r.add_argument('--params')
    r.add_argument('--init')
    r.add_argument('--spread-bps', type=float, default=1.0)
    r.add_argument('--map', choices=('z', 'sign'), default='z')
    r.add_argument('--z-window', type=int, default=100)
    r.add_argument('--invert', action='store_true')
    r.add_argument('--side', choices=('momentum', 'reversal'), default='momentum')
    r.add_argument('--hold', type=int, default=10)
    r.add_argument('--side-window', type=int, default=5)
    r.add_argument('--out')
    a = ap.parse_args(argv)

    if a.cmd == 'list':
        for kind, comps in components.discover().items():
            print(f'{kind}:')
            for name, c in sorted(comps.items()):
                print(f'  {name:<22} {c if isinstance(c, str) else ""}')
        print(f"demo instruments: {', '.join(data.demo_instruments()) or 'none (run install.py)'}")
        return 0

    opts = {'map': a.map, 'z_window': a.z_window, 'invert': a.invert, 'side': a.side,
            'hold': a.hold, 'side_window': a.side_window}
    rep = analyse(a.kind, a.name, a.data, a.instrument, _kv(a.params), _kv(a.init), opts, a.spread_bps)
    print(f"{a.kind} {a.name} on {a.instrument}  {rep['period'][0]} -> {rep['period'][1]}")
    print(json.dumps(rep['component'], default=str))
    for k, v in rep['summary'].items():
        print(f'  {k:<16} {v}')
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(rep, f, indent=1, default=str)
        print(f'report -> {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
