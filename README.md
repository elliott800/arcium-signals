# arcium-signals: test unit

Private. A slim trade engine that analyses **one** Arcium seed component at a time (a feature, alpha model or event sampler). It turns the component into a −1..+1 signal, trades it on one instrument with fixed size, and reports its results and its own predictive power.

## What it contains, and what it never contains

| In this repo | Installed locally into `vendor/` (git-ignored) | Never copied |
|---|---|---|
| Slim backtest engine, stats, the `Signal` stand-in, the component adapters, the CLI | Seed components (`features`, `alpha_models`, `event_samplers`, `indicators`), `feature_base.py`, 4 published AFML helpers pulled out of `deprado_ml.py`, the canned demo bars | Trade engine, GA, classifier pipeline, mixers, risk management, settings, keys |

`install.py` uses an allowlist, and `vendor/INSTALLED.json` records the source silo and every file's sha256, so you can check it against the foundation seal.

## Use

```
python install.py                       # from ../arcium_controller/.../silo/mean_reversion
python -m arcium_signals list
python -m arcium_signals run feature momentum --params mom_window=10
python -m arcium_signals run alpha dual_ma --params ma1=20,ma2=100 --instrument GBP_USD
python -m arcium_signals run sampler cusum --side reversal --hold 10
python -m arcium_signals run feature frac_diff_ffd --out report.json
python -m pytest -q
```

## Real data: the Data Hub warehouse

On the laptop or the server (the only two places with a copy of the warehouse), the test unit and any
side project can read what the Data Hub records. Read-only: the connection refuses writes.

```
python -m arcium_signals hub list                         # every recording: rows, first, last
python -m arcium_signals hub list oanda_practice
python -m arcium_signals hub bars EUR_USD --rate M1 --csv eurusd_m1.csv
python -m arcium_signals hub bars AAPL --rate D --source yahoo
python -m arcium_signals hub facts AAPL                   # SEC EDGAR figures
python -m arcium_signals run alpha dual_ma --data hub --instrument EUR_USD --rate M1
python -m arcium_signals run feature momentum --data hub:yahoo --instrument SPY --rate D
```

In Python: `from arcium_signals import hub` then `hub.bars(...)`, `hub.facts(...)`, `hub.series('fred', ...)`,
`hub.cot(...)`, `hub.catalog(...)`. It connects with `ARCIUM_HUB_DATABASE_URL`, else `DATABASE_URL`, else
the app's `../arciumsignals/.env.local`.

`python -m arcium_signals --help` lists every option.

## How each kind becomes a signal

- **feature:** its value, as a rolling z-score divided by 2 and clipped to ±1 (`--map sign` uses its sign instead). The IC uses the raw value.
- **alpha:** its own −1/0/+1, computed one bar at a time, as live.
- **sampler:** at each event, take the direction of the last `--side-window` bars (`momentum`) or the opposite (`reversal`), and hold for `--hold` bars.
- **indicator:** `indicatorpax` needs `mathpax`, `listpax` and `datapax`, which no longer exist. It's listed as unavailable.

The position over bar t→t+1 is the signal at bar t. Each change of position costs `--spread-bps` (default 1). There's no compounding and no risk management.

## Report

Trading: `total_return`, `sharpe`, `max_drawdown`, `trades`, `hit_rate`, `avg_trade_bars`, `exposure`, `turnover`, `long_share`.

Before costs: `gross_return`, `gross_sharpe`, `cost_paid`. On 1-minute bars a 1 bp cost is larger than the average move, so look at gross figures for the component's own edge.

Predictive power: `ic_1`, `ic_5`, `ic_20`, the rank correlation of the component's output with the next 1, 5 and 20 bars' return.

The demo bars are about 3.5 days of 1-minute bars for 6 pairs. For real conclusions, pass a longer CSV with `--data` (the datahub warehouse is next).
