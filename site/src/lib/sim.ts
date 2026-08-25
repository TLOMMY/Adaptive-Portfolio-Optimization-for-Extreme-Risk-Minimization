// In-browser simulation of the user's own buy-and-hold picks, plus the same
// metrics the Python side computes (metrics.py) so the two are comparable.
import type { Metrics, Prices } from './data';

const TRADING_DAYS = 252;

/** Daily value of a buy-and-hold portfolio. `dollars` maps ticker -> amount invested on day 0. */
export function buyAndHold(prices: Prices, dollars: Record<string, number>, total: number): number[] {
	const idx = new Map(prices.assets.map((a, i) => [a, i]));
	const cashIdx = idx.get('CASH')!;
	const invested = Object.values(dollars).reduce((s, v) => s + v, 0);
	const cash = Math.max(0, total - invested);
	const entries = Object.entries(dollars)
		.filter(([, v]) => v > 0)
		.map(([t, v]) => [idx.get(t)!, v] as const);
	return prices.rows.map((row) => {
		let v = cash * row[cashIdx];
		for (const [i, d] of entries) v += d * row[i];
		return v;
	});
}

/** Column of the normalised price table as a series. */
export function series(prices: Prices, ticker: string): number[] {
	const i = prices.assets.indexOf(ticker);
	return prices.rows.map((r) => r[i]);
}

export function dailyReturns(value: number[]): number[] {
	const out: number[] = [];
	for (let i = 1; i < value.length; i++) out.push(value[i] / value[i - 1] - 1);
	return out;
}

function mean(x: number[]): number {
	return x.reduce((s, v) => s + v, 0) / x.length;
}
function std(x: number[]): number {
	const m = mean(x);
	return Math.sqrt(x.reduce((s, v) => s + (v - m) ** 2, 0) / (x.length - 1));
}

/** Mirror of portfolio/metrics.py: summarise(value, rf). `rf` is the daily risk-free return series. */
export function summarise(dates: string[], value: number[], rf: number[]): Metrics {
	const r = dailyReturns(value);
	const years = (Date.parse(dates[dates.length - 1]) - Date.parse(dates[0])) / (365.25 * 864e5);
	const cagr = (value[value.length - 1] / value[0]) ** (1 / years) - 1;
	const sd = std(r);
	const vol = sd * Math.sqrt(TRADING_DAYS);
	const excess = r.map((v, i) => v - (rf[i] ?? 0));
	const sharpe = sd > 0 ? (mean(excess) / sd) * Math.sqrt(TRADING_DAYS) : 0;
	const neg = r.filter((v) => v < 0);
	const downside = neg.length > 1 ? std(neg) * Math.sqrt(TRADING_DAYS) : 0;
	const sortino = downside > 0 ? (mean(excess) * TRADING_DAYS) / downside : 0;

	let peak = value[0],
		maxDd = 0,
		maxDdI = 0;
	value.forEach((v, i) => {
		if (v > peak) peak = v;
		const dd = v / peak - 1;
		if (dd < maxDd) {
			maxDd = dd;
			maxDdI = i;
		}
	});

	// month-end values -> monthly returns
	const monthEnds: number[] = [];
	for (let i = 0; i < dates.length; i++) {
		if (i === dates.length - 1 || dates[i].slice(0, 7) !== dates[i + 1].slice(0, 7)) monthEnds.push(value[i]);
	}
	const monthly = dailyReturns(monthEnds);

	const k = Math.max(1, Math.round(0.05 * r.length));
	const losses = r.map((v) => -v).sort((a, b) => b - a);
	const cvar = mean(losses.slice(0, k));

	return {
		start_value: value[0],
		end_value: value[value.length - 1],
		total_return: value[value.length - 1] / value[0] - 1,
		cagr,
		volatility: vol,
		sharpe,
		sortino,
		max_drawdown: maxDd,
		max_drawdown_date: dates[maxDdI],
		worst_month: Math.min(...monthly),
		best_month: Math.max(...monthly),
		cvar_95_daily: cvar,
		years
	};
}

/** Risk-free daily returns derived from the CASH column. */
export function riskFree(prices: Prices): number[] {
	return dailyReturns(series(prices, 'CASH'));
}
