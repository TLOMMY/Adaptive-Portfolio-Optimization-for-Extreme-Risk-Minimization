<script lang="ts">
	import type { RunResult } from '$lib/data';
	import { money, pct } from '$lib/format';
	import type { Chosen } from './store.svelte';

	let { rows, benchmark }: { rows: (Chosen & { run: RunResult })[]; benchmark: RunResult | null } = $props();

	const cols = [
		{ label: 'Final value', help: 'from $100,000', f: (r: RunResult) => money(r.metrics.end_value) },
		{ label: 'Return / year', help: 'CAGR', f: (r: RunResult) => pct(r.metrics.cagr) },
		{ label: 'Volatility', help: 'annualised', f: (r: RunResult) => pct(r.metrics.volatility) },
		{ label: 'Sharpe', help: 'return above cash per unit of volatility', f: (r: RunResult) => r.metrics.sharpe.toFixed(2) },
		{ label: 'Sortino', help: 'same, downside only', f: (r: RunResult) => r.metrics.sortino.toFixed(2) },
		{ label: 'Worst drawdown', help: 'largest fall from a peak', f: (r: RunResult) => pct(r.metrics.max_drawdown) },
		{ label: 'Daily CVaR', help: 'average loss on the worst 5% of days', f: (r: RunResult) => pct(r.metrics.cvar_95_daily, 2) }
	];
	const totalCost = (r: RunResult) => r.solves.reduce((s, x) => s + x.cost, 0);
	const years = (r: RunResult) => r.metrics.years.toFixed(1) + 'y';
</script>

<div class="scroll">
	<table class="mono">
		<thead>
			<tr>
				<th class="who">Run</th>
				<th class="num">Years</th>
				{#each cols as c (c.label)}
					<th class="num"><span>{c.label}</span><small>{c.help}</small></th>
				{/each}
				<th class="num"><span>Re-solves</span><small>decisions made</small></th>
				<th class="num"><span>Trading cost</span><small>total paid</small></th>
			</tr>
		</thead>
		<tbody>
			{#each rows as r (r.key)}
				<tr>
					<th class="who"><i style:background={r.color}></i>{r.run.profile.name} <span class="model">{r.run.model.name}</span></th>
					<td class="num">{years(r.run)}</td>
					{#each cols as c (c.label)}<td class="num">{c.f(r.run)}</td>{/each}
					<td class="num">{r.run.solves.length}</td>
					<td class="num">{money(totalCost(r.run))}</td>
				</tr>
			{/each}
			{#if benchmark}
				<tr class="bench">
					<th class="who"><i></i>S&amp;P 500 <span class="model">buy and hold, {years(benchmark)}</span></th>
					<td class="num">{years(benchmark)}</td>
					{#each cols as c (c.label)}
						<td class="num">{c.f({ ...benchmark, metrics: benchmark.benchmark_metrics })}</td>
					{/each}
					<td class="num">0</td>
					<td class="num">{money(0)}</td>
				</tr>
			{/if}
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
		font-size: 0.78rem;
	}
	th,
	td {
		padding: 0.55rem 0.6rem;
		border-bottom: 1px solid var(--rule);
		white-space: nowrap;
		vertical-align: bottom;
	}
	thead th {
		font-weight: 400;
		color: var(--ink-soft);
		border-bottom: 1px solid var(--ink);
	}
	thead th span {
		display: block;
	}
	thead th small {
		display: block;
		font-size: 0.6rem;
		opacity: 0.7;
		font-family: var(--serif);
		white-space: normal;
		max-width: 9rem;
	}
	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
	.who {
		text-align: left;
		font-family: var(--serif);
		font-weight: 400;
		font-size: 0.9rem;
	}
	.who i {
		display: inline-block;
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 50%;
		margin-right: 0.5rem;
		vertical-align: middle;
		background: var(--market);
	}
	.model {
		display: block;
		font-family: var(--mono);
		font-size: 0.65rem;
		color: var(--ink-soft);
		margin-left: 1.1rem;
	}
	.bench td,
	.bench th {
		color: var(--ink-soft);
	}
</style>
