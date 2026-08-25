// Pure helpers that turn a daily value series into the things the simulator charts.
import type { RunResult } from '$lib/data';

const TRADING_DAYS = 252;

export interface Series {
	name: string;
	color: string;
	dates: string[];
	values: number[];
	dash?: boolean; // dashed stroke (benchmarks, limits)
	step?: boolean; // step-after interpolation (values that hold until the next change)
}

/** The prefix of a dated series up to and including `cursorDate` (ISO strings compare lexically). */
export function upTo<T extends { dates: string[]; values: number[] }>(s: T, cursorDate: string): T {
	let lo = 0,
		hi = s.dates.length;
	while (lo < hi) {
		const mid = (lo + hi) >> 1;
		if (s.dates[mid] <= cursorDate) lo = mid + 1;
		else hi = mid;
	}
	return { ...s, dates: s.dates.slice(0, lo), values: s.values.slice(0, lo) };
}

/** value / running maximum - 1, i.e. how far below its previous peak the portfolio sits. */
export function drawdown(values: number[]): number[] {
	let peak = -Infinity;
	return values.map((v) => {
		if (v > peak) peak = v;
		return v / peak - 1;
	});
}

/** Return over the trailing `win` trading days, starting once a full window exists. */
export function rollingReturn(dates: string[], values: number[], win = TRADING_DAYS): { dates: string[]; values: number[] } {
	const out: number[] = [];
	const d: string[] = [];
	for (let i = win; i < values.length; i++) {
		out.push(values[i] / values[i - win] - 1);
		d.push(dates[i]);
	}
	return { dates: d, values: out };
}

/** Annualised standard deviation of daily returns over the trailing `win` days. */
export function rollingVol(dates: string[], values: number[], win = TRADING_DAYS): { dates: string[]; values: number[] } {
	const r: number[] = [];
	for (let i = 1; i < values.length; i++) r.push(values[i] / values[i - 1] - 1);
	const out: number[] = [];
	const d: string[] = [];
	let s = 0,
		s2 = 0;
	for (let i = 0; i < r.length; i++) {
		s += r[i];
		s2 += r[i] * r[i];
		if (i >= win) {
			s -= r[i - win];
			s2 -= r[i - win] * r[i - win];
		}
		if (i >= win - 1) {
			const n = win;
			const mean = s / n;
			const variance = Math.max(0, (s2 - n * mean * mean) / (n - 1));
			out.push(Math.sqrt(variance) * Math.sqrt(TRADING_DAYS));
			d.push(dates[i + 1]);
		}
	}
	return { dates: d, values: out };
}

/** Cumulative trading cost paid, as a step series over the solve dates. */
export function cumulativeCost(run: RunResult, scale = 1): { dates: string[]; values: number[] } {
	let acc = 0;
	const dates = run.solves.map((s) => s.date);
	const values = run.solves.map((s) => (acc += s.cost * scale));
	dates.push(run.dates[run.dates.length - 1]);
	values.push(acc);
	return { dates, values };
}

/** Number of positions held after each re-solve, as a step series. */
export function holdingsCount(run: RunResult): { dates: string[]; values: number[] } {
	const dates = run.solves.map((s) => s.date);
	const values = run.solves.map((s) => s.n_holdings);
	dates.push(run.dates[run.dates.length - 1]);
	values.push(values[values.length - 1] ?? 0);
	return { dates, values };
}

/** Calendar-month returns: {year, month (1-12), value}. The first month uses the first value as its base. */
export function monthlyReturns(dates: string[], values: number[]): { year: number; month: number; value: number }[] {
	const out: { year: number; month: number; value: number }[] = [];
	let base = values[0];
	for (let i = 0; i < dates.length; i++) {
		const last = i === dates.length - 1 || dates[i].slice(0, 7) !== dates[i + 1].slice(0, 7);
		if (last) {
			out.push({ year: +dates[i].slice(0, 4), month: +dates[i].slice(5, 7), value: values[i] / base - 1 });
			base = values[i];
		}
	}
	return out;
}

/** Calendar-year returns: {year, value}. */
export function yearlyReturns(dates: string[], values: number[]): { year: number; value: number }[] {
	const out: { year: number; value: number }[] = [];
	let base = values[0];
	for (let i = 0; i < dates.length; i++) {
		const last = i === dates.length - 1 || dates[i].slice(0, 4) !== dates[i + 1].slice(0, 4);
		if (last) {
			out.push({ year: +dates[i].slice(0, 4), value: values[i] / base - 1 });
			base = values[i];
		}
	}
	return out;
}

/** Push labels apart vertically so none overlap; keeps order by original y. */
export function spreadLabels<T extends { y: number }>(items: T[], gap = 12, min = -Infinity, max = Infinity): T[] {
	const sorted = [...items].sort((a, b) => a.y - b.y);
	for (let i = 1; i < sorted.length; i++) {
		if (sorted[i].y - sorted[i - 1].y < gap) sorted[i].y = sorted[i - 1].y + gap;
	}
	const overflow = sorted.length ? sorted[sorted.length - 1].y - max : 0;
	if (overflow > 0) for (const it of sorted) it.y -= overflow;
	for (let i = sorted.length - 2; i >= 0; i--) {
		if (sorted[i + 1].y - sorted[i].y < gap) sorted[i].y = sorted[i + 1].y - gap;
	}
	for (const it of sorted) if (it.y < min) it.y = min;
	return sorted;
}
