<script lang="ts">
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { loadIndex, loadUniverse, type RunIndex, type Universe } from '$lib/data';
	import { money, pct } from '$lib/format';
	import WeightsRibbon from '$lib/components/WeightsRibbon.svelte';
	import Picker from '$lib/lab/Picker.svelte';
	import Panel from '$lib/lab/Panel.svelte';
	import LineChart from '$lib/lab/LineChart.svelte';
	import MetricsTable from '$lib/lab/MetricsTable.svelte';
	import { cumulativeCost, drawdown, rollingReturn, rollingVol, type Series } from '$lib/lab/series';
	import { PANELS, addRun, hidePanel, initPanels, lab, loadedRuns, shortLabel, showPanel, type PanelId } from '$lib/lab/store.svelte';

	let index = $state<RunIndex | null>(null);
	let universe = $state<Universe | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		document.body.dataset.world = 'paper';
		initPanels();
		try {
			[index, universe] = await Promise.all([loadIndex(), loadUniverse()]);
		} catch (e) {
			error = String(e);
			return;
		}
		// /lab?runs=builder__cvar,builder__equal pre-selects runs, so a comparison is linkable;
		// &panels=all (or a comma list of panel ids) overrides the remembered panel set for that visit.
		const q = new URLSearchParams(location.search);
		const panels = q.get('panels');
		if (panels === 'all') lab.visible = PANELS.map((p) => p.id);
		else if (panels) lab.visible = PANELS.map((p) => p.id).filter((p) => panels.split(',').includes(p));
		const wanted = q.get('runs');
		if (wanted) {
			for (const key of wanted.split(',')) {
				const [profile, model] = key.split('__');
				if (index.runs.some((r) => r.profile === profile && r.model === model)) addRun(profile, model);
			}
		}
	});

	const rows = $derived(loadedRuns());
	const first = $derived(rows[0]?.run ?? null);
	const label = (r: (typeof rows)[number]) => shortLabel(r.run.profile.name, r.model);
	const fullLabel = (r: (typeof rows)[number]) => `${r.run.profile.name} · ${r.run.model.name}`;
	const marketColor = 'var(--market)';

	const valueSeries = $derived.by((): Series[] => {
		const s: Series[] = rows.map((r) => ({ name: label(r), color: r.color, dates: r.run.dates, values: r.run.value }));
		if (first) s.push({ name: 'S&P 500', color: marketColor, dates: first.dates, values: first.benchmark, dash: true });
		return s;
	});
	const ddSeries = $derived.by((): Series[] => {
		const s: Series[] = rows.map((r) => ({ name: label(r), color: r.color, dates: r.run.dates, values: drawdown(r.run.value) }));
		if (first) s.push({ name: 'S&P 500', color: marketColor, dates: first.dates, values: drawdown(first.benchmark), dash: true });
		return s;
	});
	const ddMin = $derived(Math.min(0, ...ddSeries.flatMap((s) => s.values)) * 1.05);
	const rollRet = $derived.by((): Series[] => {
		const s: Series[] = rows.map((r) => ({ name: label(r), color: r.color, ...rollingReturn(r.run.dates, r.run.value) }));
		if (first) s.push({ name: 'S&P 500', color: marketColor, ...rollingReturn(first.dates, first.benchmark), dash: true });
		return s.filter((x) => x.values.length);
	});
	const rollV = $derived.by((): Series[] => {
		const s: Series[] = rows.map((r) => ({ name: label(r), color: r.color, ...rollingVol(r.run.dates, r.run.value) }));
		if (first) s.push({ name: 'S&P 500', color: marketColor, ...rollingVol(first.dates, first.benchmark), dash: true });
		return s.filter((x) => x.values.length);
	});
	const riskSeries = $derived.by((): Series[] =>
		rows.flatMap((r) => {
			const dates = r.run.solves.map((s) => s.date);
			const last = r.run.dates[r.run.dates.length - 1];
			return [
				{ name: `${label(r)} promised`, color: r.color, dates: [...dates, last], values: [...r.run.solves.map((s) => s.cvar_limit), r.run.solves.at(-1)!.cvar_limit], dash: true, step: true },
				{ name: `${label(r)} realised`, color: r.color, dates: [...dates, last], values: [...r.run.solves.map((s) => s.cvar), r.run.solves.at(-1)!.cvar], step: true }
			];
		})
	);
	const costSeries = $derived.by((): Series[] =>
		rows.map((r) => ({ name: label(r), color: r.color, ...cumulativeCost(r.run), step: true }))
	);
	const ribbon = $derived(rows.find((r) => r.key === lab.ribbonKey) ?? rows[0] ?? null);
	const hidden = $derived(PANELS.filter((p) => !lab.visible.includes(p.id)));
	const fmtMoney = (v: number) => money(v);
	const fmtPct = (v: number) => pct(v, 0);
	const fmtPct1 = (v: number) => pct(v, 1);
	const fmtPct2 = (v: number) => pct(v, 2);
	let menuOpen = $state(false);
	function show(id: PanelId) {
		showPanel(id);
		menuOpen = false;
	}
</script>

<svelte:head>
	<title>The Lab · Yesterday's Portfolio</title>
</svelte:head>

<section class="lab">
	<header class="top">
		<div>
			<p class="eyebrow mono">The Lab</p>
			<h1>Same decade, different methods.</h1>
			<p class="lede">
				Every investor profile was run through every portfolio method over the same ten years from 4 January 2016,
				each starting with $100,000. A <em>run</em> is one investor under one method. Choose runs to lay them side by
				side; the S&amp;P 500, bought once and held, is always drawn for comparison.
			</p>
		</div>
		<a class="btn back" href="{base}/">Back to the story</a>
	</header>

	{#if error}
		<p class="muted">Could not load data: {error}</p>
	{:else if !index}
		<p class="muted">Opening the lab…</p>
	{:else}
		<Picker profiles={index.profiles} models={index.models} />

		{#if rows.length === 0}
			<p class="muted empty">Choose at least one run to see the charts.</p>
		{:else}
			{#each lab.visible as id (id)}
				{#if id === 'value'}
					<Panel title="Value of $100,000" explain="How the money grew. The vertical axis is logarithmic, so equal vertical distances mean equal percentage changes and a doubling looks the same whether it happens at $100,000 or $300,000." onhide={() => hidePanel('value')}>
						<LineChart series={valueSeries} log fmt={fmtMoney} height={360} />
					</Panel>
				{:else if id === 'drawdown'}
					<Panel title="Drawdown" explain="A drawdown is how far the portfolio sits below the highest value it has reached so far. Zero means it is at a new high; the deepest point is the worst loss an investor would have lived through." onhide={() => hidePanel('drawdown')}>
						<LineChart series={ddSeries} fmt={fmtPct} domain={[ddMin, 0]} height={240} />
					</Panel>
				{:else if id === 'table'}
					<Panel title="The numbers" explain="One row per run. CAGR (compound annual growth rate) is the single yearly return that would produce the same final value; volatility is how widely daily returns scatter, annualised; Sharpe is return above cash per unit of volatility, and higher is better." onhide={() => hidePanel('table')}>
						<MetricsTable {rows} benchmark={first} />
					</Panel>
				{:else if id === 'rollret'}
					<Panel title="Rolling one-year return" explain="On each day, the return over the previous 252 trading days (about one year). It shows when a method was ahead or behind rather than only where it ended." onhide={() => hidePanel('rollret')}>
						<LineChart series={rollRet} fmt={fmtPct} zeroLine height={260} />
					</Panel>
				{:else if id === 'rollvol'}
					<Panel title="Rolling one-year volatility" explain="The annualised standard deviation of daily returns over the previous 252 trading days. Higher means a bumpier ride; every method spikes in March 2020." onhide={() => hidePanel('rollvol')}>
						<LineChart series={rollV} fmt={fmtPct} height={260} />
					</Panel>
				{:else if id === 'risk'}
					<Panel title="Realised loss against the promise" explain="Each investor has a loss limit: the average loss allowed on the worst 5% of days (daily CVaR at 95%), which tightens as the horizon shrinks. The dashed line is the limit on each decision date; the solid line is what the chosen portfolio would have lost on the worst days of the three years the model could see." onhide={() => hidePanel('risk')}>
						<LineChart series={riskSeries} fmt={fmtPct2} height={260} />
					</Panel>
				{:else if id === 'cost'}
					<Panel title="Trading costs" explain="Every trade costs 0.1% of the amount traded. This is the running total paid, in dollars from the $100,000 start; each step is one re-solve." onhide={() => hidePanel('cost')}>
						<LineChart series={costSeries} fmt={fmtMoney} height={220} />
					</Panel>
				{:else if id === 'weights'}
					<Panel title="What one run held" explain="The share of the portfolio in each sector, week by week, for one chosen run. Bonds, gold and cash are shown separately from stocks." onhide={() => hidePanel('weights')}>
						{#snippet aside()}
							<select class="mono" bind:value={lab.ribbonKey} aria-label="Run to show">
								{#each rows as r (r.key)}<option value={r.key}>{fullLabel(r)}</option>{/each}
							</select>
						{/snippet}
						{#if ribbon && universe}
							<WeightsRibbon weights={ribbon.run.weights} assets={universe.assets} cursorDate={ribbon.run.dates[ribbon.run.dates.length - 1]} />
						{/if}
					</Panel>
				{/if}
			{/each}

			<div class="addpanel">
				{#if hidden.length}
					<button class="btn" onclick={() => (menuOpen = !menuOpen)}>+ Add a panel</button>
					{#if menuOpen}
						<ul class="menu mono">
							{#each hidden as p (p.id)}
								<li><button onclick={() => show(p.id)}>{p.title}</button></li>
							{/each}
						</ul>
					{/if}
				{:else}
					<p class="muted mono">Every panel is shown.</p>
				{/if}
			</div>
		{/if}
	{/if}
</section>

<style>
	.lab {
		max-width: 72rem;
		margin: 0 auto;
		padding: 3rem 1.5rem 5rem;
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 2rem;
		flex-wrap: wrap;
	}
	.eyebrow {
		font-size: 0.7rem;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		color: var(--stamp);
		margin: 0 0 0.5rem;
	}
	h1 {
		font-size: 2.2rem;
	}
	.lede {
		max-width: 60ch;
		margin: 0;
		color: var(--ink-soft);
	}
	.back {
		text-decoration: none;
		margin-top: 0.4rem;
		white-space: nowrap;
	}
	.empty {
		padding: 2rem 0;
	}
	.addpanel {
		position: relative;
		border-top: 1px solid var(--rule);
		padding-top: 1.2rem;
	}
	.menu {
		list-style: none;
		padding: 0.3rem 0;
		margin: 0.5rem 0 0;
		border: 1px solid var(--rule);
		background: var(--paper);
		display: inline-block;
		min-width: 18rem;
	}
	.menu button {
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		padding: 0.5rem 0.9rem;
		font-size: 0.75rem;
		color: inherit;
	}
	.menu button:hover {
		background: var(--paper-deep);
	}
	select {
		font-size: 0.7rem;
		background: var(--paper);
		color: inherit;
		border: 1px solid var(--rule);
		padding: 0.3rem 0.4rem;
		max-width: 16rem;
	}
</style>
