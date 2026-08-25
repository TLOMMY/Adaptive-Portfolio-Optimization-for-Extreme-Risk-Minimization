// Turn the model's solve log into short letters from "your adviser".
import type { Asset, RunResult, Solve } from './data';

export interface Letter {
	date: string;
	solve: Solve;
	title: string;
	body: string;
	stocks: number; // target weight in stocks after this rebalance
	bonds: number;
	cash: number;
	biggestBuys: { asset: string; delta: number }[];
	biggestSells: { asset: string; delta: number }[];
}

const REASONS: Record<Solve['reason'], string> = {
	start: 'Today we begin. I have put your money to work for the first time.',
	calendar: 'A quarter has passed since my last review, so I have gone over the portfolio again.',
	drift: 'Market moves have pulled the portfolio more than 10% away from its targets, so I have brought it back into line.',
	volatility: 'Market volatility has jumped to more than twice its normal level. That is my signal to re-check every position.'
};

const pct = (x: number, d = 0) => `${(x * 100).toFixed(d)}%`;
const monthYear = (iso: string) =>
	new Date(iso).toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });

export function buildLetters(result: RunResult, assets: Asset[]): Letter[] {
	const kind = new Map(assets.map((a) => [a.ticker, a]));
	const target = new Map<string, number>(assets.map((a) => [a.ticker, a.kind === 'cash' ? 1 : 0]));
	const tradesByDate = new Map<string, typeof result.trades>();
	for (const t of result.trades) {
		if (!tradesByDate.has(t.date)) tradesByDate.set(t.date, []);
		tradesByDate.get(t.date)!.push(t);
	}

	return result.solves.map((solve) => {
		const trades = tradesByDate.get(solve.date) ?? [];
		for (const t of trades) target.set(t.asset, t.to);
		let stocks = 0,
			bonds = 0,
			cash = 0;
		for (const [tk, w] of target) {
			const a = kind.get(tk);
			if (!a) continue;
			if (a.kind === 'cash') cash += w;
			else if (a.sector === 'Bonds') bonds += w;
			else stocks += w;
		}
		const deltas = trades.map((t) => ({ asset: t.asset, delta: t.to - t.from }));
		const biggestBuys = deltas.filter((d) => d.delta > 0.005).sort((a, b) => b.delta - a.delta).slice(0, 3);
		const biggestSells = deltas.filter((d) => d.delta < -0.005).sort((a, b) => a.delta - b.delta).slice(0, 3);

		const name = (tk: string) => kind.get(tk)?.name ?? tk;
		const parts: string[] = [REASONS[solve.reason]];
		if (solve.reason !== 'start') {
			if (biggestBuys.length)
				parts.push(`I added to ${biggestBuys.map((b) => `${name(b.asset)} (+${pct(b.delta)})`).join(', ')}.`);
			if (biggestSells.length)
				parts.push(`I trimmed ${biggestSells.map((b) => `${name(b.asset)} (${pct(b.delta)})`).join(', ')}.`);
			if (!biggestBuys.length && !biggestSells.length) parts.push('Nothing needed to change.');
		} else {
			parts.push(
				`You now hold ${solve.n_holdings} positions: ${pct(stocks)} in stocks, ${pct(bonds)} in bonds and gold, ${pct(cash)} in cash.`
			);
		}
		parts.push(
			`Your loss limit is ${pct(solve.cvar_limit, 1)} a day, meaning on your worst days I expect you to lose no more than that on average` +
				(solve.years_left < result.profile.horizon_years - 0.5
					? `, and it tightens as your ${solve.years_left.toFixed(1)}-year horizon shrinks.`
					: '.')
		);
		if (solve.cost > 0) parts.push(`Trading cost you $${solve.cost.toFixed(0)} this time.`);

		return {
			date: solve.date,
			solve,
			title: monthYear(solve.date),
			body: parts.join(' '),
			stocks,
			bonds,
			cash,
			biggestBuys,
			biggestSells
		};
	});
}
