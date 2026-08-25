<script lang="ts">
	// The simulator: a fixed control panel on the left (date, totals, playback, series, analyses) and
	// the analyses on the right, every one of them clipped to the playback date. Used for the story's
	// ten years (mode 'story') and for the lab (mode 'lab'); only the pre-loaded series differ.
	import { onMount, untrack } from 'svelte';
	import { base } from '$app/paths';
	import { app, go } from '$lib/state.svelte';
	import type { MarketEvent, Prices, RunIndex, Universe } from '$lib/data';
	import { buyAndHold, riskFree, series as priceSeries, summarise } from '$lib/sim';
	import { buildLetters } from '$lib/letters';
	import { longDate, money, pct, signedPct } from '$lib/format';
	import WeightsRibbon from '$lib/components/WeightsRibbon.svelte';
	import LineChart from './LineChart.svelte';
	import Panel from './Panel.svelte';
	import Heatmap from './Heatmap.svelte';
	import YearlyBars from './YearlyBars.svelte';
	import HowItWent, { type Row } from './HowItWent.svelte';
	import { cumulativeCost, drawdown, holdingsCount, monthlyReturns, rollingReturn, rollingVol, upTo, yearlyReturns, type Series } from './series';
	import { PANELS, addRun, addSpy, addYou, hidePanel, initPanels, removeEntry, reset, sim, togglePanel, type Entry, type PanelId } from './store.svelte';

	let {
		mode,
		universe,
		prices,
		events,
		index
	}: { mode: 'story' | 'lab'; universe: Universe; prices: Prices; events: MarketEvent[]; index: RunIndex } = $props();

	const profileName = (k: string) => index.profiles.find((p) => p.key === k)?.name ?? k;
	const modelName = (k: string) => index.models.find((m) => m.key === k)?.name ?? k;
	const add = (profile: string, model: string) => addRun(profile, model, { profile: profileName(profile), model: modelName(model) });
	const hasPicks = () => Object.values(app.allocations).some((v) => v > 0);

	let pickProfile = $state(untrack(() => app.adviser));
	let pickModel = $state(untrack(() => index.story_model));
	let heatKey = $state('');

	onMount(() => {
		const q = new URLSearchParams(location.search);
		initPanels(q.get('panels'));
		reset();
		if (mode === 'story') {
			addYou(); // even an investor who placed no orders made a choice: all cash
			add(app.adviser, index.story_model);
			addSpy();
			sim.cursor = 0;
			sim.playing = true;
		} else {
			const wanted = q.get('runs');
			if (wanted) {
				for (const key of wanted.split(',')) {
					const [profile, model] = key.split('__');
					if (index.runs.some((r) => r.profile === profile && r.model === model)) add(profile, model);
				}
			}
			if (hasPicks()) addYou();
			addSpy();
			sim.cursor = prices.dates.length - 1;
			sim.playing = false;
		}
	});

	// ---- the time axis: every series is clipped to the playback date -------------------------
	const n = $derived(prices.dates.length);
	const cursorDate = $derived(prices.dates[Math.min(sim.cursor, n - 1)]);
	const cursorTime = $derived(Date.parse(cursorDate));
	const xDomain = $derived([Date.parse(prices.dates[0]), Date.parse(prices.dates[n - 1])] as [number, number]);
	const amount = $derived(app.amount);
	const scale = $derived(amount / 100_000);
	const rf = $derived(riskFree(prices));

	interface Full extends Entry {
		dates: string[];
		values: number[]; // full series, in dollars from `amount`
	}
	const full = $derived.by((): Full[] =>
		sim.entries.flatMap((e): Full[] => {
			if (e.kind === 'you') return [{ ...e, dates: prices.dates, values: buyAndHold(prices, app.allocations, amount) }];
			if (e.kind === 'spy') return [{ ...e, dates: prices.dates, values: priceSeries(prices, 'SPY').map((v) => v * amount) }];
			const run = sim.runs[e.key];
			return run ? [{ ...e, dates: run.dates, values: run.value.map((v) => v * scale) }] : [];
		})
	);
	const clipped = $derived(full.map((f) => upTo(f, cursorDate)).filter((f) => f.values.length));
	const runs = $derived(clipped.filter((c) => c.kind === 'run').map((c) => ({ ...c, run: sim.runs[c.key] })));
	const focus = $derived(runs.find((r) => r.key === sim.focusKey) ?? runs[0] ?? null);
	const heat = $derived(clipped.find((c) => c.key === heatKey) ?? focus ?? clipped[0] ?? null);

	const toSeries = (c: (typeof clipped)[number], values = c.values, dates = c.dates): Series => ({
		name: c.label, color: c.color, dates, values, dash: c.kind === 'spy'
	});
	const valueSeries = $derived(clipped.map((c) => toSeries(c)));
	const ddSeries = $derived(clipped.map((c) => toSeries(c, drawdown(c.values))));
	const ddMin = $derived(Math.min(-0.02, ...ddSeries.flatMap((s) => s.values)) * 1.05);
	const rollRet = $derived(clipped.map((c) => ({ ...toSeries(c), ...rollingReturn(c.dates, c.values) })).filter((s) => s.values.length));
	const rollV = $derived(clipped.map((c) => ({ ...toSeries(c), ...rollingVol(c.dates, c.values) })).filter((s) => s.values.length));
	const riskSeries = $derived(
		runs.flatMap((r): Series[] => {
			const solves = r.run.solves.filter((s) => s.date <= cursorDate);
			if (!solves.length) return [];
			const dates = [...solves.map((s) => s.date), cursorDate];
			return [
				{ name: `${r.label} limit`, color: r.color, dates, values: [...solves.map((s) => s.cvar_limit), solves.at(-1)!.cvar_limit], dash: true, step: true },
				{ name: `${r.label} realised`, color: r.color, dates, values: [...solves.map((s) => s.cvar), solves.at(-1)!.cvar], step: true }
			];
		})
	);
	const holdSeries = $derived(runs.map((r) => ({ ...toSeries(r), ...upTo(holdingsCount(r.run), cursorDate), step: true })).filter((s) => s.values.length));
	const costSeries = $derived(runs.map((r) => ({ ...toSeries(r), ...upTo(cumulativeCost(r.run, scale), cursorDate), step: true })).filter((s) => s.values.length));
	const yearly = $derived(clipped.map((c) => ({ name: c.label, color: c.color, years: yearlyReturns(c.dates, c.values) })));
	const heatCells = $derived(heat ? monthlyReturns(heat.dates, heat.values) : []);
	const rows = $derived.by((): Row[] =>
		clipped
			.filter((c) => c.values.length > 2)
			.map((c) => {
				const run = c.kind === 'run' ? sim.runs[c.key] : null;
				const solves = run ? run.solves.filter((s) => s.date <= cursorDate) : null;
				return {
					key: c.key, full: c.full, color: c.color,
					metrics: summarise(c.dates, c.values, rf.slice(0, c.values.length - 1)),
					solves: solves ? solves.length : null,
					cost: solves ? solves.reduce((s, x) => s + x.cost * scale, 0) : null
				};
			})
	);
	const letter = $derived.by(() => {
		if (!focus) return null;
		const letters = buildLetters(focus.run, universe.assets);
		let last = null;
		for (const l of letters) {
			if (l.date <= cursorDate) last = l;
			else break;
		}
		return last;
	});
	const event = $derived(events.filter((e) => e.date <= cursorDate).at(-1) ?? null);
	const finished = $derived(sim.cursor >= n - 1);

	// ---- playback --------------------------------------------------------------------------
	$effect(() => {
		if (!sim.playing) return;
		let raf = 0;
		const tick = () => {
			if (sim.cursor >= n - 1) {
				sim.playing = false;
				return;
			}
			sim.cursor = Math.min(n - 1, sim.cursor + sim.speed);
			raf = requestAnimationFrame(tick);
		};
		raf = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(raf);
	});
	function replay() {
		sim.cursor = 0;
		sim.playing = true;
	}
	function playPause() {
		if (finished) replay();
		else sim.playing = !sim.playing;
	}

	const fmtMoney = (v: number) => money(v);
	const fmtPct0 = (v: number) => pct(v, 0);
	const fmtPct2 = (v: number) => pct(v, 2);
	const fmtInt = (v: number) => String(Math.round(v));
	const valueAt = (c: (typeof clipped)[number]) => c.values[c.values.length - 1];
</script>

<div class="sim">
	<aside class="panel">
		<p class="eyebrow">{mode === 'story' ? 'Ten years, replayed' : 'The lab'}</p>
		<p class="date">{longDate(cursorDate)}</p>

		<ul class="totals">
			{#each clipped as c (c.key)}
				<li style:--c={c.color}>
					<span class="name"><i></i>{c.label}</span>
					<strong>{money(valueAt(c))}</strong>
					<em class:neg={valueAt(c) < amount}>{signedPct(valueAt(c) / amount - 1)}</em>
				</li>
			{/each}
		</ul>

		<div class="playback">
			<input class="scrub" type="range" min="0" max={n - 1} bind:value={sim.cursor} oninput={() => (sim.playing = false)} aria-label="Playback date" />
			<div class="buttons">
				<button class="btn" onclick={playPause}>{sim.playing ? 'Pause' : finished ? 'Replay' : 'Play'}</button>
				<button class="btn ghost" onclick={() => { sim.playing = false; sim.cursor = n - 1; }} disabled={finished}>To the end</button>
				<label class="speed">Speed <input type="range" min="1" max="20" bind:value={sim.speed} aria-label="Playback speed" /></label>
			</div>
		</div>

		<section>
			<p class="label">Series</p>
			<ul class="entries">
				{#each sim.entries as e (e.key)}
					<li style:--c={e.color}>
						<i></i>
						<span>{e.full}{#if sim.loading[e.key]} <small>loading…</small>{/if}</span>
						<button class="x" onclick={() => removeEntry(e.key)} aria-label="Remove {e.full}">×</button>
					</li>
				{/each}
			</ul>
			<div class="adder">
				<select bind:value={pickProfile} aria-label="Investor">
					{#each index.profiles as p (p.key)}<option value={p.key}>{p.name}</option>{/each}
				</select>
				<select bind:value={pickModel} aria-label="Method">
					{#each index.models as m (m.key)}<option value={m.key}>{m.name}</option>{/each}
				</select>
				<button class="btn small" onclick={() => add(pickProfile, pickModel)}>Add run</button>
			</div>
			<div class="quick">
				<button class="link" onclick={() => index.models.forEach((m) => add(pickProfile, m.key))}>every method for {profileName(pickProfile)}</button>
				<button class="link" onclick={() => index.profiles.forEach((p) => add(p.key, pickModel))}>every investor under {modelName(pickModel)}</button>
				{#if !sim.entries.some((e) => e.kind === 'you')}<button class="link" onclick={addYou}>show your own picks</button>{/if}
				{#if !sim.entries.some((e) => e.kind === 'spy')}<button class="link" onclick={addSpy}>show the S&amp;P 500</button>{/if}
			</div>
		</section>

		<section>
			<p class="label">Analyses</p>
			<ul class="checks">
				{#each PANELS as p (p.id)}
					<li><label><input type="checkbox" checked={sim.visible.includes(p.id)} onchange={() => togglePanel(p.id)} /> {p.title}</label></li>
				{/each}
			</ul>
		</section>

		<div class="foot">
			{#if mode === 'story'}
				<button class="btn ghost" onclick={() => go('archive')}>Travel again</button>
			{:else}
				<a class="btn ghost" href="{base}/">Back to the story</a>
			{/if}
		</div>
	</aside>

	<main class="analyses">
		{#if !clipped.length}
			<p class="dim empty">Add a run on the left to begin.</p>
		{/if}
		{#each sim.visible as id (id)}
			{@const meta = PANELS.find((p) => p.id === id)!}
			{#if id === 'value' && clipped.length}
				<Panel title={`Value of ${money(amount)}`} explain={meta.explain} onhide={() => hidePanel(id)}>
					{#snippet aside()}<label class="toggle"><input type="checkbox" bind:checked={sim.log} /> log axis</label>{/snippet}
					<LineChart series={valueSeries} {xDomain} {cursorTime} log={sim.log} fmt={fmtMoney} height={340} />
				</Panel>
			{:else if id === 'howitwent' && rows.length}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					<HowItWent {rows} {cursorDate} />
				</Panel>
			{:else if id === 'drawdown' && clipped.length}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					<LineChart series={ddSeries} {xDomain} {cursorTime} fmt={fmtPct0} domain={[ddMin, 0]} height={220} />
				</Panel>
			{:else if id === 'letter' && runs.length}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					{#snippet aside()}
						<select bind:value={sim.focusKey} aria-label="Adviser to read">{#each runs as r (r.key)}<option value={r.key}>{r.full}</option>{/each}</select>
					{/snippet}
					{#if letter}
						<article class="letter"><h3>{letter.title}</h3><p>{letter.body}</p></article>
					{:else}
						<p class="dim">No decision yet.</p>
					{/if}
				</Panel>
			{:else if id === 'world'}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					{#if event}
						<article class="letter"><h3>{event.title} <small>{longDate(event.date)}</small></h3><p>{event.blurb}</p></article>
					{:else}
						<p class="dim">Quiet so far.</p>
					{/if}
				</Panel>
			{:else if id === 'weights' && focus}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					{#snippet aside()}
						<select bind:value={sim.focusKey} aria-label="Run to show">{#each runs as r (r.key)}<option value={r.key}>{r.full}</option>{/each}</select>
					{/snippet}
					<WeightsRibbon weights={focus.run.weights} assets={universe.assets} {cursorDate} />
				</Panel>
			{:else if id === 'yearly' && clipped.length}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					<YearlyBars groups={yearly} />
				</Panel>
			{:else if id === 'heatmap' && heat}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					{#snippet aside()}
						<select bind:value={heatKey} aria-label="Series to show">{#each clipped as c (c.key)}<option value={c.key}>{c.full}</option>{/each}</select>
					{/snippet}
					<Heatmap cells={heatCells} />
				</Panel>
			{:else if id === 'rollret' && rollRet.length}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					<LineChart series={rollRet} {xDomain} {cursorTime} fmt={fmtPct0} zeroLine height={240} />
				</Panel>
			{:else if id === 'rollvol' && rollV.length}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					<LineChart series={rollV} {xDomain} {cursorTime} fmt={fmtPct0} height={240} />
				</Panel>
			{:else if id === 'risk' && riskSeries.length}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					<LineChart series={riskSeries} {xDomain} {cursorTime} fmt={fmtPct2} height={240} />
				</Panel>
			{:else if id === 'holdings' && holdSeries.length}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					<LineChart series={holdSeries} {xDomain} {cursorTime} fmt={fmtInt} height={200} />
				</Panel>
			{:else if id === 'cost' && costSeries.length}
				<Panel title={meta.title} explain={meta.explain} onhide={() => hidePanel(id)}>
					<LineChart series={costSeries} {xDomain} {cursorTime} fmt={fmtMoney} height={200} />
				</Panel>
			{/if}
		{/each}
	</main>
</div>

<style>
	.sim {
		/* the screen world: night palette, interface faces */
		--fg: #e8e4da;
		--dim: #9aa0ad;
		--line: rgba(232, 228, 218, 0.14);
		--bad: #e08a7a;
		--surface: #141821;
		--sans: 'IBM Plex Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
		--mono: 'IBM Plex Mono', 'SF Mono', Menlo, Consolas, monospace;
		font-family: var(--sans);
		color: var(--fg);
		display: grid;
		grid-template-columns: 18rem minmax(0, 1fr);
		gap: 2rem;
		max-width: 90rem;
		margin: 0 auto;
		padding: 1.5rem 1.5rem 4rem;
	}
	@media (max-width: 64rem) {
		.sim {
			grid-template-columns: 1fr;
		}
	}
	.panel {
		position: sticky;
		top: 1rem;
		align-self: start;
		max-height: calc(100vh - 2rem);
		overflow-y: auto;
		scrollbar-width: thin;
		scrollbar-color: var(--line) transparent;
		padding-right: 0.6rem;
		display: flex;
		flex-direction: column;
		gap: 1.1rem;
		font-size: 0.85rem;
	}
	@media (max-width: 64rem) {
		.panel {
			position: static;
			max-height: none;
		}
	}
	.eyebrow,
	.label {
		font-family: var(--mono);
		font-size: 0.62rem;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--dim);
		margin: 0;
	}
	.date {
		font-size: 1.3rem;
		font-weight: 600;
		margin: -0.8rem 0 0;
		letter-spacing: -0.01em;
	}
	.totals {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.totals li {
		display: grid;
		grid-template-columns: 1fr auto;
		grid-template-rows: auto auto;
		border-top: 1px solid var(--line);
		padding-top: 0.3rem;
	}
	.totals .name {
		grid-column: 1 / -1;
		font-size: 0.72rem;
		color: var(--dim);
	}
	.totals i,
	.entries i {
		display: inline-block;
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 50%;
		background: var(--c);
		margin-right: 0.4rem;
		vertical-align: middle;
	}
	.totals strong {
		font-family: var(--mono);
		font-weight: 500;
		font-size: 1.15rem;
		font-variant-numeric: tabular-nums;
	}
	.totals em {
		font-style: normal;
		font-family: var(--mono);
		font-size: 0.78rem;
		color: var(--adviser);
		align-self: end;
	}
	.totals em.neg {
		color: var(--bad);
	}
	.playback {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.scrub {
		width: 100%;
		accent-color: var(--fg);
	}
	.buttons {
		display: flex;
		gap: 0.4rem;
		align-items: center;
		flex-wrap: wrap;
	}
	.speed {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-family: var(--mono);
		font-size: 0.65rem;
		color: var(--dim);
		margin-left: auto;
	}
	.speed input {
		width: 4.5rem;
		accent-color: var(--fg);
	}
	.btn {
		border: 1px solid var(--fg);
		background: transparent;
		color: var(--fg);
		padding: 0.45rem 0.9rem;
		border-radius: 3px;
		font: inherit;
		font-size: 0.78rem;
		font-weight: 500;
		letter-spacing: 0.02em;
		text-decoration: none;
		cursor: pointer;
		text-align: center;
	}
	.btn:hover {
		background: var(--fg);
		color: var(--night);
	}
	.btn.ghost {
		border-color: var(--line);
		color: var(--dim);
	}
	.btn.ghost:hover {
		border-color: var(--fg);
		color: var(--fg);
		background: transparent;
	}
	.btn:disabled {
		opacity: 0.35;
		cursor: default;
	}
	.btn.small {
		padding: 0.35rem 0.7rem;
	}
	.entries {
		list-style: none;
		margin: 0.3rem 0 0.5rem;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	.entries li {
		display: flex;
		align-items: center;
		gap: 0.2rem;
		border-left: 2px solid var(--c);
		padding: 0.2rem 0.4rem;
		background: rgba(255, 255, 255, 0.03);
	}
	.entries li span {
		flex: 1;
	}
	.entries small {
		color: var(--dim);
	}
	.x {
		border: none;
		background: none;
		color: var(--dim);
		font: inherit;
		font-size: 1rem;
		line-height: 1;
		padding: 0 0.2rem;
		cursor: pointer;
	}
	.x:hover {
		color: var(--fg);
	}
	.adder {
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.35rem;
	}
	select {
		font: inherit;
		font-size: 0.78rem;
		background: var(--surface);
		color: var(--fg);
		border: 1px solid var(--line);
		border-radius: 3px;
		padding: 0.35rem 0.5rem;
		max-width: 100%;
	}
	.quick {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		margin-top: 0.4rem;
	}
	.link {
		background: none;
		border: none;
		padding: 0;
		font: inherit;
		font-size: 0.72rem;
		color: var(--dim);
		text-decoration: underline;
		text-underline-offset: 0.2em;
		text-align: left;
		cursor: pointer;
	}
	.link:hover {
		color: var(--fg);
	}
	.checks {
		list-style: none;
		margin: 0.3rem 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.checks label {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		font-size: 0.8rem;
		cursor: pointer;
	}
	.checks input {
		accent-color: var(--fg);
	}
	.foot {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		margin-top: 0.4rem;
	}
	.analyses {
		min-width: 0;
	}
	.empty {
		padding: 3rem 0;
	}
	.dim {
		color: var(--dim);
	}
	.toggle {
		font-family: var(--mono);
		font-size: 0.65rem;
		color: var(--dim);
		display: flex;
		gap: 0.3rem;
		align-items: center;
	}
	.toggle input {
		accent-color: var(--fg);
	}
	.letter {
		border: 1px solid var(--line);
		background: var(--surface);
		padding: 1rem 1.2rem;
		max-width: 70ch;
	}
	.letter h3 {
		margin: 0 0 0.4rem;
		font-size: 1rem;
		font-weight: 600;
	}
	.letter h3 small {
		font-family: var(--mono);
		font-weight: 400;
		font-size: 0.65rem;
		color: var(--dim);
		margin-left: 0.5rem;
	}
	.letter p {
		margin: 0;
		line-height: 1.5;
		font-size: 0.92rem;
	}
</style>
