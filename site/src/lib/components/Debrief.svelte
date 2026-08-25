<script lang="ts">
	import { onMount } from 'svelte';
	import { app, go } from '$lib/state.svelte';
	import { loadIndex, loadRun, type Metrics, type Prices, type RunResult, type Universe } from '$lib/data';
	import { base } from '$app/paths';
	import { buyAndHold, riskFree, series, summarise } from '$lib/sim';
	import { money, pct, signedPct } from '$lib/format';

	let { universe, prices }: { universe: Universe; prices: Prices } = $props();
	let result = $state<RunResult | null>(null);
	onMount(async () => {
		const idx = await loadIndex();
		result = await loadRun(app.adviser, idx.story_model);
	});

	const n = $derived(result ? result.dates.length : prices.dates.length);
	const dates = $derived(prices.dates.slice(0, n));
	const rf = $derived(riskFree(prices));
	const you = $derived(summarise(dates, buyAndHold(prices, app.allocations, app.amount).slice(0, n), rf));
	const market = $derived(summarise(dates, series(prices, 'SPY').slice(0, n).map((v) => v * app.amount), rf));
	const adviser = $derived.by((): Metrics | null => {
		if (!result) return null;
		const s = app.amount / 100_000;
		return { ...result.metrics, start_value: result.metrics.start_value * s, end_value: result.metrics.end_value * s };
	});

	const rows: { key: keyof Metrics; label: string; fmt: (v: number) => string; help: string }[] = [
		{ key: 'end_value', label: 'Final value', fmt: (v) => money(v), help: 'What the money became.' },
		{ key: 'total_return', label: 'Total return', fmt: signedPct, help: 'Growth over the whole period.' },
		{ key: 'cagr', label: 'Return per year', fmt: pct, help: 'Compound annual growth rate.' },
		{ key: 'volatility', label: 'Volatility', fmt: pct, help: 'How bumpy the ride was (annualised standard deviation of daily returns).' },
		{ key: 'sharpe', label: 'Sharpe ratio', fmt: (v) => v.toFixed(2), help: 'Return above cash, per unit of volatility. Higher is better.' },
		{ key: 'max_drawdown', label: 'Worst drawdown', fmt: pct, help: 'Largest fall from a previous peak.' },
		{ key: 'worst_month', label: 'Worst month', fmt: pct, help: 'The single worst calendar month.' },
		{ key: 'cvar_95_daily', label: 'Daily CVaR (95%)', fmt: pct, help: 'Average loss on the worst 5% of days.' }
	];
</script>

<section class="debrief">
	<p class="eyebrow mono">31 December 2025 · Debrief</p>
	<h1>How it went.</h1>
	{#if adviser && result}
		<table class="mono">
			<thead>
				<tr>
					<th></th>
					<th style:color="var(--you)">You</th>
					<th style:color="var(--adviser)">{result.profile.name}</th>
					<th style:color="var(--market)">S&amp;P 500</th>
				</tr>
			</thead>
			<tbody>
				{#each rows as r (r.key)}
					<tr>
						<th><span>{r.label}</span><small class="muted">{r.help}</small></th>
						<td>{r.fmt(you[r.key] as number)}</td>
						<td>{r.fmt(adviser[r.key] as number)}</td>
						<td>{r.fmt(market[r.key] as number)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		<p class="muted">
			Your adviser re-solved its portfolio {result.solves.length} times over {result.metrics.years.toFixed(1)} years and
			paid {money(result.solves.reduce((s, x) => s + x.cost, 0) * (app.amount / 100_000))} in trading costs.
		</p>
	{/if}
	{#if result}
		<p class="muted">
			{result.profile.name} used the {result.model.name} model. The same investor can be run under other methods,
			and other investors under this one, in the <a href="{base}/lab?runs={app.adviser}__{result.model.key}">comparison lab</a>.
		</p>
	{/if}
	<footer>
		<button class="btn" onclick={() => go('archive')}>Travel again</button>
		<a class="btn" href="{base}/lab?runs={app.adviser}__{result?.model.key ?? 'cvar'}">Open the lab</a>
	</footer>
</section>

<style>
	.debrief {
		max-width: 56rem;
		margin: 0 auto;
		padding: 3rem 1.5rem 5rem;
	}
	.eyebrow {
		font-size: 0.7rem;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		color: var(--stamp);
	}
	h1 {
		font-size: 2.2rem;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		margin: 2rem 0 1rem;
		font-size: 0.9rem;
	}
	th,
	td {
		text-align: right;
		padding: 0.6rem 0.5rem;
		border-bottom: 1px solid var(--rule);
	}
	tbody th {
		text-align: left;
		font-weight: 400;
		font-family: var(--serif);
	}
	tbody th small {
		display: block;
		font-size: 0.7rem;
	}
	footer {
		margin-top: 3rem;
		display: flex;
		justify-content: center;
		gap: 1rem;
		flex-wrap: wrap;
	}
	a.btn {
		text-decoration: none;
		display: inline-block;
	}
</style>
