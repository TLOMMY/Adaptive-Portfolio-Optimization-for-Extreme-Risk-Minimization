<script lang="ts">
	import { onMount } from 'svelte';
	import { app, allocated, go, remaining } from '$lib/state.svelte';
	import { loadProfileIndex, type Prices, type ProfileMeta, type Universe } from '$lib/data';
	import { money, pct } from '$lib/format';

	let { universe, prices }: { universe: Universe; prices: Prices } = $props();
	let advisers = $state<ProfileMeta[]>([]);
	onMount(async () => {
		advisers = await loadProfileIndex();
	});

	const pickable = $derived(universe.assets.filter((a) => a.kind !== 'cash'));
	const sectors = $derived([...new Set(pickable.map((a) => a.sector))]);

	function setDollars(ticker: string, v: string) {
		const n = Math.max(0, Number(v.replace(/[^0-9.]/g, '')) || 0);
		if (n === 0) delete app.allocations[ticker];
		else app.allocations[ticker] = n;
	}
	const over = $derived(remaining() < 0);
</script>

<section class="archive">
	<header>
		<p class="eyebrow mono">1 January 2016 · The Archive</p>
		<h1>You have {money(app.amount)}. Where does it go?</h1>
		<p class="muted">
			Put money into any of the {pickable.length} companies and funds below; whatever you leave over sits
			in cash earning the T-bill rate. Your picks are bought once and held for ten years. Then choose an
			adviser whose portfolio will run alongside yours from the same {money(app.amount)}.
		</p>
	</header>

	<div class="ledger mono" class:over>
		<span>Invested {money(allocated())}</span>
		<span>Cash {money(remaining())}</span>
	</div>

	{#each sectors as sector (sector)}
		<h2 class="sector">{sector}</h2>
		<div class="cards">
			{#each pickable.filter((a) => a.sector === sector) as a (a.ticker)}
				<label class="card">
					<span class="ticker mono">{a.ticker}</span>
					<span class="name">{a.name}</span>
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
	{/each}

	<h2 class="sector">Hire an adviser</h2>
	<div class="cards advisers">
		{#each advisers as p (p.key)}
			<button class="card adviser" class:chosen={app.adviser === p.key} onclick={() => (app.adviser = p.key)}>
				<span class="name">{p.name}</span>
				<span class="tagline">{p.tagline}</span>
				<span class="rules mono muted">
					horizon {p.horizon_years}y · loss limit {pct(p.cvar_start)}→{pct(p.cvar_end)}/day · ≤{p.max_holdings}
					holdings · cash ≥ {pct(p.cash_min, 0)}
				</span>
			</button>
		{/each}
	</div>

	<footer>
		<button class="btn" disabled={over} onclick={() => go('journey')}>Begin the ten years</button>
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
	}
	h1 {
		font-size: 2.2rem;
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
		margin: 1.5rem 0;
		z-index: 2;
	}
	.ledger.over {
		color: var(--stamp);
	}
	.sector {
		font-size: 0.8rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		margin: 2rem 0 0.6rem;
		color: var(--ink-soft);
	}
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
		gap: 0.6rem;
	}
	.card {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		border: 1px solid var(--rule);
		background: var(--paper-deep);
		padding: 0.7rem 0.8rem;
		text-align: left;
		color: inherit;
	}
	.ticker {
		font-size: 0.7rem;
		color: var(--ink-soft);
	}
	.name {
		font-size: 1rem;
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
		grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
	}
	.adviser {
		cursor: pointer;
	}
	.adviser.chosen {
		outline: 2px solid var(--stamp);
	}
	.tagline {
		font-style: italic;
	}
	.rules {
		font-size: 0.7rem;
		margin-top: 0.4rem;
	}
	footer {
		margin-top: 3rem;
		text-align: center;
	}
	.btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
</style>
