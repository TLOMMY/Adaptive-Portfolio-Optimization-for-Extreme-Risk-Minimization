<script lang="ts">
	// The debrief as a panel: one row per series, every number computed up to the playback date.
	import type { Metrics } from '$lib/data';
	import { money, pct, signedPct } from '$lib/format';

	export interface Row {
		key: string;
		full: string;
		color: string;
		metrics: Metrics;
		solves: number | null; // null for series that never re-solve (You, S&P 500)
		cost: number | null;
	}
	let { rows, cursorDate }: { rows: Row[]; cursorDate: string } = $props();

	const cols = $derived.by((): { label: string; help: string; f: (r: Row) => string; neg?: (r: Row) => boolean }[] => [
		{ label: 'Value', help: 'at the playback date', f: (r) => money(r.metrics.end_value) },
		{ label: 'Total return', help: 'since day one', f: (r) => signedPct(r.metrics.total_return), neg: (r) => r.metrics.total_return < 0 },
		{ label: 'Return / year', help: 'CAGR', f: (r) => pct(r.metrics.cagr), neg: (r) => r.metrics.cagr < 0 },
		{ label: 'Volatility', help: 'annualised', f: (r) => pct(r.metrics.volatility) },
		{ label: 'Sharpe', help: 'return above cash per unit of volatility', f: (r) => r.metrics.sharpe.toFixed(2) },
		{ label: 'Sortino', help: 'same, downside only', f: (r) => r.metrics.sortino.toFixed(2) },
		{ label: 'Worst drawdown', help: 'largest fall from a peak', f: (r) => pct(r.metrics.max_drawdown), neg: () => true },
		{ label: 'Worst month', help: 'single calendar month', f: (r) => pct(r.metrics.worst_month), neg: () => true },
		{ label: 'Daily CVaR', help: 'average loss on the worst 5% of days', f: (r) => pct(r.metrics.cvar_95_daily, 2) },
		{ label: 'Re-solves', help: 'decisions made', f: (r) => (r.solves === null ? '—' : String(r.solves)) },
		{ label: 'Trading cost', help: 'total paid', f: (r) => (r.cost === null ? '—' : money(r.cost)) }
	]);
</script>

<div class="scroll">
	<table>
		<thead>
			<tr>
				<th class="who">Series</th>
				{#each cols as c (c.label)}
					<th class="num"><span>{c.label}</span><small>{c.help}</small></th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each rows as r (r.key)}
				<tr>
					<th class="who"><i style:background={r.color}></i>{r.full}</th>
					{#each cols as c (c.label)}
						<td class="num" class:neg={c.neg?.(r)}>{c.f(r)}</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.scroll {
		overflow-x: auto;
	}
	table {
		border-collapse: collapse;
		width: 100%;
		font-family: var(--mono);
		font-size: 0.74rem;
	}
	th,
	td {
		padding: 0.5rem 0.55rem;
		border-bottom: 1px solid var(--line);
		white-space: nowrap;
		vertical-align: bottom;
	}
	thead th {
		font-weight: 500;
		color: var(--dim);
		border-bottom: 1px solid var(--fg);
	}
	thead th span {
		display: block;
	}
	thead th small {
		display: block;
		font-size: 0.58rem;
		opacity: 0.7;
		font-family: var(--sans);
		white-space: normal;
		max-width: 8rem;
		font-weight: 400;
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.num.neg {
		color: var(--bad);
	}
	.who {
		text-align: left;
		font-family: var(--sans);
		font-weight: 500;
		font-size: 0.82rem;
	}
	.who i {
		display: inline-block;
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 50%;
		margin-right: 0.5rem;
		vertical-align: middle;
	}
</style>
