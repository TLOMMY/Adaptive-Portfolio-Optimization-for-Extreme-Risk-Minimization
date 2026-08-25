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
	import { money } from '$lib/format';
	import FrontPage from './gazette/FrontPage.svelte';
	import SectorPage from './gazette/SectorPage.svelte';
	import FundsPage from './gazette/FundsPage.svelte';
	import ClassifiedsPage from './gazette/ClassifiedsPage.svelte';

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

	let nav: HTMLOListElement;
	function goStep(i: number) {
		step = Math.max(0, Math.min(steps.length - 1, i));
		window.scrollTo({ top: 0 });
		// on phones the editions are a horizontal strip: keep the current one in view
		nav?.querySelector('.active')?.scrollIntoView({ inline: 'center', block: 'nearest' });
	}
	const name = (t: string) => universe.assets.find((a) => a.ticker === t)?.name ?? t;
</script>

<section class="archive">
	<aside class="panel">
		<p class="deskline">1 January 2016 · The Archive</p>
		<div class="money" class:over>
			<div><span>Invested</span><strong>{money(allocated())}</strong></div>
			<div><span>Cash left</span><strong>{money(remaining())}</strong></div>
			<div class="bar"><i style:width={`${Math.min(100, Math.max(0, (allocated() / app.amount) * 100))}%`}></i></div>
			{#if over}<p class="warn">You have allocated more than you have.</p>{/if}
			{#if allocated() > 0}
				<button class="clear" onclick={() => { for (const k of Object.keys(app.allocations)) delete app.allocations[k]; }}>Clear all orders</button>
			{/if}
		</div>
		<nav aria-label="Editions">
			<p class="label">Editions · {step + 1} of {steps.length}</p>
			<ol bind:this={nav}>
				{#each steps as s, i (s.title)}
					{@const inv = investedIn(
						s.kind === 'sector' ? pickable.filter((a) => a.sector === s.title).map((a) => a.ticker) : s.kind === 'funds' ? pickable.filter((a) => a.kind === 'etf').map((a) => a.ticker) : []
					)}
					<li>
						<button class:active={i === step} class:done={i < step} onclick={() => goStep(i)}>
							<span class="n">{i + 1}</span>
							<span class="t">{s.kind === 'overview' ? 'Where things stand' : s.kind === 'adviser' ? 'Your adviser' : s.title === 'Telecommunication Services' ? 'Telecommunications' : s.title}</span>
							{#if inv > 0}<span class="inv">{money(inv)}</span>{/if}
						</button>
					</li>
				{/each}
			</ol>
		</nav>
		<div class="steps">
			{#if step > 0}<button class="btn ghost" onclick={() => goStep(step - 1)}>Back</button>{/if}
			{#if current.kind === 'adviser'}
				<button class="btn" disabled={over} onclick={() => go('journey')}>Begin the ten years</button>
			{:else}
				<button class="btn" onclick={() => goStep(step + 1)}>
					{current.kind === 'overview' ? 'Start choosing' : step === steps.length - 2 ? 'Choose an adviser' : 'Next edition'}
				</button>
			{/if}
		</div>
	</aside>

	<div class="page">
	{#if !archive || !notes}
		<p class="muted">Opening the year-end papers…</p>
	{:else if current.kind === 'overview'}
		<FrontPage note={notes.year} {archive} amount={app.amount} editions={stockSectors.length} />
	{:else if current.kind === 'sector' && sectorNote && sectorStats}
		<SectorPage
			sector={current.title}
			edition={step}
			editions={stockSectors.length}
			note={sectorNote}
			stats={sectorStats}
			assets={sectorAssets}
			assetStats={archive.assets}
			assetNotes={notes.assets}
			allocations={app.allocations}
			onallocate={setDollars}
		/>
	{:else if current.kind === 'funds'}
		<FundsPage
			bonds={notes.sectors.Bonds}
			gold={notes.sectors.Gold}
			{archive}
			assets={sectorAssets}
			assetStats={archive.assets}
			assetNotes={notes.assets}
			allocations={app.allocations}
			onallocate={setDollars}
			number={step + 1}
		/>
	{:else}
		<ClassifiedsPage
			{advisers}
			chosen={app.adviser}
			onchoose={(k) => (app.adviser = k)}
			amount={app.amount}
			number={step + 1}
			nameOf={name}
		/>
	{/if}
	</div>
</section>

<style>
	.archive {
		display: grid;
		grid-template-columns: 15rem minmax(0, 1fr);
		gap: 2rem;
		max-width: 82rem;
		margin: 0 auto;
		padding: 1.5rem 1.5rem 5rem;
	}
	.money {
		border: 1px solid rgba(233, 223, 204, 0.3);
		padding: 0.8rem 0.9rem;
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.4rem 0.8rem;
	}
	.money > div:not(.bar) {
		display: flex;
		flex-direction: column;
	}
	.money span {
		font-family: var(--news-cond);
		font-size: 0.66rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--desk-ink-soft);
	}
	.money strong {
		font-family: var(--news-cond);
		font-weight: 500;
		font-size: 1.45rem;
		letter-spacing: 0.01em;
		color: var(--desk-ink);
		font-variant-numeric: tabular-nums;
	}
	.money.over strong {
		color: var(--desk-accent);
	}
	.bar {
		grid-column: 1 / -1;
		height: 4px;
		background: rgba(233, 223, 204, 0.15);
	}
	.bar i {
		display: block;
		height: 100%;
		background: var(--desk-accent);
	}
	.clear {
		grid-column: 1 / -1;
		justify-self: start;
		background: none;
		border: none;
		padding: 0;
		font-family: var(--news-cond);
		font-size: 0.68rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--desk-ink-soft);
		text-decoration: underline;
		text-underline-offset: 0.2em;
		cursor: pointer;
	}
	.clear:hover {
		color: var(--desk-accent);
	}
	.warn {
		grid-column: 1 / -1;
		margin: 0;
		font-family: var(--news-serif);
		font-size: 0.82rem;
		color: var(--desk-accent);
	}
	.panel .label {
		font-family: var(--news-cond);
		font-size: 0.66rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--desk-ink-soft);
		margin: 0 0 0.3rem;
	}
	.panel ol {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.panel li button {
		width: 100%;
		display: grid;
		grid-template-columns: 1.4rem 1fr auto;
		gap: 0.5rem;
		align-items: baseline;
		border: none;
		border-left: 2px solid rgba(233, 223, 204, 0.15);
		background: transparent;
		color: var(--desk-ink-soft);
		text-align: left;
		padding: 0.3rem 0.5rem;
		font-family: var(--news-serif);
		font-size: 0.95rem;
	}
	.panel li button:hover {
		color: var(--desk-ink);
		border-left-color: rgba(233, 223, 204, 0.5);
	}
	.panel li button.done {
		color: var(--desk-ink);
	}
	.panel li button.active {
		color: var(--desk-ink);
		background: rgba(233, 223, 204, 0.1);
		border-left-color: var(--desk-accent);
	}
	.panel .n {
		font-family: var(--news-cond);
		font-size: 0.72rem;
		color: var(--desk-ink-soft);
	}
	.panel .inv {
		font-family: var(--news-cond);
		font-size: 0.78rem;
		color: var(--desk-accent);
	}
	.steps {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.steps .btn {
		width: 100%;
		white-space: nowrap;
		font-family: var(--news-cond);
		font-size: 0.82rem;
		letter-spacing: 0.12em;
	}
	.deskline {
		font-family: var(--news-cond);
		font-size: 0.72rem;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--desk-accent);
		margin: 0;
		white-space: nowrap;
	}
	.btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	.btn.ghost {
		opacity: 0.7;
	}
	@media (max-width: 60rem) {
		.archive {
			grid-template-columns: 1fr;
		}
	}
	.page {
		min-width: 0;
	}
	.panel {
		position: sticky;
		top: 1rem;
		align-self: start;
		display: flex;
		flex-direction: column;
		gap: 1.2rem;
		max-height: calc(100vh - 2rem);
		overflow-y: auto;
	}
	@media (max-width: 60rem) {
		.archive {
			padding: 1rem 0.75rem 4rem;
			gap: 1.2rem;
		}
		.panel {
			position: static;
			max-height: none;
			overflow: visible;
			gap: 0.8rem;
		}
		/* the fourteen editions become one scrollable strip so the paper starts above the fold */
		.panel ol {
			display: flex;
			gap: 0.25rem;
			overflow-x: auto;
			scrollbar-width: none;
		}
		.panel ol::-webkit-scrollbar {
			display: none;
		}
		.panel li {
			flex: none;
		}
		.panel li button {
			grid-template-columns: auto auto auto;
			white-space: nowrap;
			border-left: 0;
			border-bottom: 2px solid rgba(233, 223, 204, 0.15);
			padding: 0.3rem 0.6rem;
			font-size: 0.88rem;
		}
		.panel li button.active {
			border-bottom-color: var(--desk-accent);
		}
		.steps {
			flex-direction: row;
		}
		.steps .btn {
			flex: 1;
			width: auto;
		}
	}
</style>
