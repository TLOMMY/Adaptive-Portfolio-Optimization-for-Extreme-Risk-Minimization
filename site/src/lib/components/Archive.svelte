<script lang="ts">
	import { onMount } from 'svelte';
	import { app, allocated, go, remaining } from '$lib/state.svelte';
	import {
		loadArchive,
		loadIndex,
		loadNotes,
		type Archive,
		type Notes2015,
		type Prices,
		type ProfileMeta,
		type Universe
	} from '$lib/data';
	import { money, pct, signedPct } from '$lib/format';
	import Avatar from './Avatar.svelte';
	import Sparkline from './Sparkline.svelte';

	let { universe, prices }: { universe: Universe; prices: Prices } = $props();

	let advisers = $state<ProfileMeta[]>([]);
	let archive = $state<Archive | null>(null);
	let notes = $state<Notes2015 | null>(null);

	onMount(async () => {
		const [idx, a, n] = await Promise.all([loadIndex(), loadArchive(), loadNotes()]);
		advisers = idx.profiles;
		archive = a;
		notes = n;
		const wanted = Number(new URLSearchParams(location.search).get('step')); // dev shortcut: /?stage=archive&step=3
		if (wanted) step = Math.min(steps.length - 1, wanted);
	});

	// The walk-through: an overview of 2015, then one screen per sector, then the adviser.
	const pickable = $derived(universe.assets.filter((a) => a.kind !== 'cash'));
	const stockSectors = $derived([...new Set(pickable.filter((a) => a.kind === 'stock').map((a) => a.sector))]);
	const steps = $derived([
		{ kind: 'overview', title: 'Where things stand' },
		...stockSectors.map((s) => ({ kind: 'sector', title: s })),
		{ kind: 'funds', title: 'Bonds and gold' },
		{ kind: 'adviser', title: 'Your adviser' }
	]);
	let step = $state(0);
	const current = $derived(steps[step]);
	const sectorAssets = $derived(
		current.kind === 'sector'
			? pickable.filter((a) => a.sector === current.title)
			: current.kind === 'funds'
				? pickable.filter((a) => a.kind === 'etf')
				: []
	);
	const sectorNote = $derived(
		current.kind === 'sector' ? notes?.sectors[current.title] : null
	);
	const sectorStats = $derived(current.kind === 'sector' ? archive?.sectors[current.title] : null);

	function setDollars(ticker: string, v: string) {
		const n = Math.max(0, Number(v.replace(/[^0-9.]/g, '')) || 0);
		if (n === 0) delete app.allocations[ticker];
		else app.allocations[ticker] = n;
	}
	const over = $derived(remaining() < 0);
	const investedIn = (tickers: string[]) => tickers.reduce((s, t) => s + (app.allocations[t] ?? 0), 0);

	function goStep(i: number) {
		step = Math.max(0, Math.min(steps.length - 1, i));
		window.scrollTo({ top: 0 });
	}
	const name = (t: string) => universe.assets.find((a) => a.ticker === t)?.name ?? t;
</script>

<section class="archive">
	<header>
		<p class="eyebrow mono">1 January 2016 · The Archive</p>
		<h1>You have {money(app.amount)}. Where does it go?</h1>
		<p class="muted lede">
			Read the year that has just ended, sector by sector, and put money into any company or fund you like.
			Whatever you leave over sits in cash earning the Treasury-bill rate. Your picks are bought once and held
			for ten years. Then choose an adviser whose portfolio will run alongside yours from the same {money(app.amount)}.
			Everything on these pages was known on 31 December 2015 and nothing later.
		</p>
	</header>

	<div class="ledger mono" class:over>
		<span>Invested {money(allocated())}</span>
		<span>Cash {money(remaining())}</span>
		<span class="steps">Step {step + 1} of {steps.length}</span>
	</div>

	<nav class="rail mono" aria-label="Sections">
		{#each steps as s, i (s.title)}
			<button class:active={i === step} class:done={i < step} onclick={() => goStep(i)}>
				{s.title}
				{#if s.kind === 'sector' || s.kind === 'funds'}
					{@const inv = investedIn(
						s.kind === 'sector' ? pickable.filter((a) => a.sector === s.title).map((a) => a.ticker) : pickable.filter((a) => a.kind === 'etf').map((a) => a.ticker)
					)}
					{#if inv > 0}<em>{money(inv)}</em>{/if}
				{/if}
			</button>
		{/each}
	</nav>

	{#if !archive || !notes}
		<p class="muted">Opening the year-end papers…</p>
	{:else if current.kind === 'overview'}
		<article class="paper">
			<p class="eyebrow mono">The year 2015, as it stood on 31 December</p>
			<h2>{notes.year.headline}</h2>
			<p class="body">{notes.year.body}</p>
			<div class="figures mono">
				<div><span>S&amp;P 500, 2015</span><strong>{signedPct(archive.assets.SPY.return_2015)}</strong></div>
				<div><span>Worst fall during 2015</span><strong>{pct(archive.assets.SPY.drawdown_2015)}</strong></div>
				<div><span>US bonds (AGG), 2015</span><strong>{signedPct(archive.assets.AGG.return_2015)}</strong></div>
				<div><span>Gold (GLD), 2015</span><strong>{signedPct(archive.assets.GLD.return_2015)}</strong></div>
				<div><span>Cash rate (3-month T-bill)</span><strong>{pct(archive.tbill_rate_annual, 2)} a year</strong></div>
				<div><span>S&amp;P 500, 2013–2015</span><strong>{signedPct(archive.assets.SPY.return_3y)}</strong></div>
			</div>
			<details class="sources"><summary class="mono">Sources</summary>
				<ul>{#each notes.year.sources as s (s)}<li><a href={s} target="_blank" rel="noreferrer">{s}</a></li>{/each}</ul>
			</details>
			<p class="muted small">Returns include dividends. "Worst fall" is the largest drop from a previous high during the year, a measure called the maximum drawdown.</p>
		</article>
	{:else if current.kind === 'sector' || current.kind === 'funds'}
		<article class="paper">
			<p class="eyebrow mono">{current.kind === 'sector' ? 'Sector' : 'Beyond stocks'} · {sectorAssets.length} choices</p>
			{#if current.kind === 'sector' && sectorNote && sectorStats}
				<h2>{sectorNote.headline}</h2>
				<p class="body">{sectorNote.body}</p>
				<div class="figures mono">
					<div><span>Average return, 2015</span><strong>{signedPct(sectorStats.return_2015)}</strong></div>
					<div><span>Best in 2015</span><strong>{name(sectorStats.best_2015.ticker)} {signedPct(sectorStats.best_2015.return)}</strong></div>
					<div><span>Worst in 2015</span><strong>{name(sectorStats.worst_2015.ticker)} {signedPct(sectorStats.worst_2015.return)}</strong></div>
					<div><span>Average return, 2013–2015</span><strong>{signedPct(sectorStats.return_3y)}</strong></div>
				</div>
				<details class="sources"><summary class="mono">Sources</summary>
					<ul>{#each sectorNote.sources as s (s)}<li><a href={s} target="_blank" rel="noreferrer">{s}</a></li>{/each}</ul>
				</details>
			{:else if current.kind === 'funds'}
				<h2>Somewhere to hide</h2>
				<p class="body">
					{notes.sectors.Bonds.body} {notes.sectors.Gold.body} Anything you do not invest stays in cash at
					{pct(archive.tbill_rate_annual, 2)} a year.
				</p>
			{/if}
		</article>

		<div class="cards">
			{#each sectorAssets as a (a.ticker)}
				{@const st = archive.assets[a.ticker]}
				<label class="card" class:held={(app.allocations[a.ticker] ?? 0) > 0}>
					<span class="top">
						<span class="ticker mono">{a.ticker}</span>
						<Sparkline values={st.spark} />
					</span>
					<span class="name">{a.name}</span>
					{#if notes.assets[a.ticker]}<span class="note">{notes.assets[a.ticker]}</span>{/if}
					<span class="stats mono">
						<span>2015 <strong class:neg={st.return_2015 < 0}>{signedPct(st.return_2015)}</strong></span>
						<span>3 yrs <strong class:neg={st.return_3y < 0}>{signedPct(st.return_3y)}</strong></span>
						<span>worst fall <strong>{pct(st.drawdown_3y)}</strong></span>
					</span>
					<span class="field mono">
						$<input
							inputmode="numeric"
							value={app.allocations[a.ticker] ?? ''}
							placeholder="0"
							onchange={(e) => setDollars(a.ticker, (e.target as HTMLInputElement).value)}
						/>
					</span>
				</label>
			{/each}
		</div>
	{:else}
		<article class="paper">
			<p class="eyebrow mono">Hire an adviser</p>
			<h2>Who manages the other {money(app.amount)}?</h2>
			<p class="body">
				Each adviser is a set of rules, not a person: how long the money is for, the largest average loss they
				will accept on a bad day, how many holdings they keep, and what they refuse to own. The loss limit is the
				daily CVaR, the average loss on the worst 5% of days, and it tightens as the horizon shrinks.
			</p>
		</article>
		<div class="cards advisers">
			{#each advisers as p (p.key)}
				{@const avoids = [...Object.entries(p.sector_cap).filter(([, v]) => v === 0).map(([k]) => k), ...p.exclude.map(name)]}
				{@const caps = Object.entries(p.sector_cap).filter(([, v]) => v > 0)}
				<button class="card adviser" class:chosen={app.adviser === p.key} onclick={() => (app.adviser = p.key)}>
					<span class="who">
						<Avatar profileKey={p.key} />
						<span>
							<span class="name">{p.name}</span>
							<span class="type mono">{p.archetype} · risk tolerance {p.risk_tolerance.toLowerCase()}</span>
						</span>
					</span>
					<span class="tagline">“{p.personality}”</span>
					<span class="rules mono">
						<span>horizon <strong>{p.horizon_years} years</strong></span>
						<span>loss limit <strong>{pct(p.cvar_start)} → {pct(p.cvar_end)}</strong> a day</span>
						<span>holdings <strong>≤ {p.max_holdings}</strong></span>
						<span>cash <strong>≥ {pct(p.cash_min, 0)}</strong></span>
						{#if avoids.length}<span>avoids <strong>{avoids.join(', ')}</strong></span>{/if}
						{#if caps.length}<span>sector caps <strong>{caps.map(([k, v]) => `${k} ≤ ${pct(v, 0)}`).join(', ')}</strong></span>{/if}
					</span>
				</button>
			{/each}
		</div>
	{/if}

	<footer>
		{#if step > 0}<button class="btn ghost" onclick={() => goStep(step - 1)}>Back</button>{/if}
		{#if current.kind === 'adviser'}
			<button class="btn" disabled={over} onclick={() => go('journey')}>Begin the ten years</button>
		{:else}
			<button class="btn" onclick={() => goStep(step + 1)}>
				{current.kind === 'overview' ? 'Start choosing' : step === steps.length - 2 ? 'Choose an adviser' : 'Next sector'}
			</button>
		{/if}
		{#if over}<p class="muted">You have allocated more than you have.</p>{/if}
	</footer>
</section>

<style>
	.archive {
		max-width: 64rem;
		margin: 0 auto;
		padding: 3rem 1.5rem 5rem;
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
	h2 {
		font-size: 1.6rem;
		margin: 0.2rem 0 0.6rem;
	}
	.lede {
		max-width: 46rem;
	}
	.ledger {
		position: sticky;
		top: 0;
		display: flex;
		gap: 2rem;
		padding: 0.6rem 0;
		background: var(--paper);
		border-top: 1px solid var(--rule);
		border-bottom: 1px solid var(--rule);
		margin: 1.5rem 0 1rem;
		z-index: 2;
		font-size: 0.85rem;
	}
	.ledger .steps {
		margin-left: auto;
		color: var(--ink-soft);
	}
	.ledger.over {
		color: var(--stamp);
	}
	.rail {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin-bottom: 1.5rem;
	}
	.rail button {
		border: 1px solid var(--rule);
		background: transparent;
		color: var(--ink-soft);
		font-size: 0.62rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		padding: 0.3rem 0.6rem;
		border-radius: 2px;
	}
	.rail button.done {
		color: var(--ink);
	}
	.rail button.active {
		background: var(--ink);
		color: var(--paper);
		border-color: var(--ink);
	}
	.rail em {
		font-style: normal;
		margin-left: 0.4rem;
		opacity: 0.8;
	}
	.paper {
		border: 1px solid var(--rule);
		background: var(--paper-deep);
		padding: 1.4rem 1.6rem;
		margin-bottom: 1.2rem;
	}
	.body {
		max-width: 60ch;
		margin: 0 0 1rem;
	}
	.figures {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
		gap: 0.6rem 1.2rem;
		font-size: 0.78rem;
		margin: 0.8rem 0;
	}
	.figures div {
		display: flex;
		flex-direction: column;
		border-top: 1px solid var(--rule);
		padding-top: 0.35rem;
	}
	.figures span {
		font-size: 0.62rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-soft);
	}
	.figures strong {
		font-weight: 500;
		font-size: 1rem;
	}
	.sources {
		font-size: 0.75rem;
		margin-top: 0.6rem;
	}
	.sources summary {
		cursor: pointer;
		color: var(--ink-soft);
		font-size: 0.62rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}
	.sources ul {
		padding-left: 1.2rem;
		margin: 0.4rem 0 0;
		word-break: break-all;
	}
	.sources a {
		color: var(--ink-soft);
	}
	.small {
		font-size: 0.8rem;
	}
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: 0.7rem;
	}
	.card {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		border: 1px solid var(--rule);
		background: var(--paper-deep);
		padding: 0.8rem 0.9rem;
		text-align: left;
		color: inherit;
	}
	.card.held {
		border-color: var(--ink);
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.ticker {
		font-size: 0.7rem;
		color: var(--ink-soft);
	}
	.name {
		font-size: 1.05rem;
	}
	.note {
		font-size: 0.82rem;
		color: var(--ink-soft);
		font-style: italic;
	}
	.stats {
		display: flex;
		gap: 0.8rem;
		flex-wrap: wrap;
		font-size: 0.62rem;
		color: var(--ink-soft);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		margin-top: 0.2rem;
	}
	.stats strong {
		font-weight: 500;
		color: var(--ink);
		text-transform: none;
		letter-spacing: 0;
		font-size: 0.78rem;
	}
	.stats strong.neg {
		color: var(--stamp);
	}
	.field {
		margin-top: 0.4rem;
		display: flex;
		align-items: baseline;
		gap: 0.2rem;
	}
	.field input {
		width: 100%;
		border: none;
		border-bottom: 1px solid var(--rule);
		background: transparent;
		font: inherit;
		outline: none;
	}
	.advisers {
		grid-template-columns: repeat(auto-fill, minmax(20rem, 1fr));
	}
	.adviser {
		cursor: pointer;
		gap: 0.7rem;
	}
	.adviser.chosen {
		outline: 2px solid var(--stamp);
	}
	.who {
		display: flex;
		gap: 0.8rem;
		align-items: center;
	}
	.who > span {
		display: flex;
		flex-direction: column;
	}
	.type {
		font-size: 0.62rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--ink-soft);
	}
	.tagline {
		font-style: italic;
		font-size: 0.95rem;
	}
	.rules {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.25rem 0.8rem;
		font-size: 0.62rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--ink-soft);
	}
	.rules strong {
		font-weight: 500;
		color: var(--ink);
		text-transform: none;
		letter-spacing: 0;
		font-size: 0.75rem;
	}
	footer {
		margin-top: 2.5rem;
		display: flex;
		justify-content: center;
		gap: 1rem;
		flex-wrap: wrap;
	}
	.btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	.btn.ghost {
		opacity: 0.7;
	}
</style>
