<script lang="ts">
	import { onMount } from 'svelte';
	import { app, go } from '$lib/state.svelte';
	import { loadProfile, type MarketEvent, type Prices, type ProfileResult, type Universe } from '$lib/data';
	import { buyAndHold, series } from '$lib/sim';
	import { buildLetters, type Letter } from '$lib/letters';
	import { longDate, money, signedPct } from '$lib/format';
	import ValueChart from './ValueChart.svelte';
	import WeightsRibbon from './WeightsRibbon.svelte';

	let { universe, prices, events }: { universe: Universe; prices: Prices; events: MarketEvent[] } = $props();

	let result = $state<ProfileResult | null>(null);
	let playing = $state(false);
	let speed = $state(6); // trading days per frame
	let narrate = $state(false);

	onMount(async () => {
		result = await loadProfile(app.adviser);
		app.cursor = 0;
		playing = true;
	});

	const n = $derived(result ? result.dates.length : 0);
	const scale = $derived(app.amount / 100_000);
	const you = $derived(buyAndHold(prices, app.allocations, app.amount).slice(0, n));
	const adviser = $derived(result ? result.value.map((v) => v * scale) : []);
	const market = $derived(series(prices, 'SPY').slice(0, n).map((v) => v * app.amount));
	const letters = $derived(result ? buildLetters(result, universe.assets) : []);
	const cursorDate = $derived(result ? result.dates[app.cursor] : prices.dates[0]);
	const currentLetter = $derived.by((): Letter | null => {
		let last: Letter | null = null;
		for (const l of letters) {
			if (l.date <= cursorDate) last = l;
			else break;
		}
		return last;
	});
	const lastEvent = $derived(events.filter((e) => e.date <= cursorDate).at(-1) ?? null);

	// playback
	$effect(() => {
		if (!playing || !result) return;
		let raf = 0;
		const tick = () => {
			if (app.cursor >= n - 1) {
				playing = false;
				return;
			}
			app.cursor = Math.min(n - 1, app.cursor + speed);
			raf = requestAnimationFrame(tick);
		};
		raf = requestAnimationFrame(tick);
		return () => cancelAnimationFrame(raf);
	});

	// narration via the browser's speech engine
	let spoken = $state<string | null>(null);
	$effect(() => {
		if (!narrate || !currentLetter || currentLetter.date === spoken) return;
		spoken = currentLetter.date;
		if ('speechSynthesis' in window) {
			speechSynthesis.cancel();
			const u = new SpeechSynthesisUtterance(`${currentLetter.title}. ${currentLetter.body}`);
			u.rate = 1.05;
			speechSynthesis.speak(u);
		}
	});
	onMount(() => () => 'speechSynthesis' in window && speechSynthesis.cancel());
</script>

{#if !result}
	<div class="stage"><p class="muted">Your adviser is preparing…</p></div>
{:else}
	<section class="journey">
		<header>
			<div>
				<p class="eyebrow mono">{longDate(cursorDate)}</p>
				<h1>Ten years, replayed.</h1>
			</div>
			<div class="controls mono">
				<button class="btn" onclick={() => (playing = !playing)}>{playing ? 'Pause' : app.cursor >= n - 1 ? 'Replay' : 'Play'}</button>
				<label>speed <input type="range" min="1" max="20" bind:value={speed} /></label>
				<label><input type="checkbox" bind:checked={narrate} /> narrate</label>
			</div>
		</header>

		<div class="totals mono">
			<div style:color="var(--you)">
				<span>You</span><strong>{money(you[app.cursor])}</strong><em>{signedPct(you[app.cursor] / app.amount - 1)}</em>
			</div>
			<div style:color="var(--adviser)">
				<span>{result.profile.name}</span><strong>{money(adviser[app.cursor])}</strong><em>{signedPct(adviser[app.cursor] / app.amount - 1)}</em>
			</div>
			<div style:color="var(--market)">
				<span>S&amp;P 500</span><strong>{money(market[app.cursor])}</strong><em>{signedPct(market[app.cursor] / app.amount - 1)}</em>
			</div>
		</div>

		<ValueChart
			dates={result.dates}
			cursor={app.cursor}
			events={events.filter((e) => e.kind !== 'world')}
			series={[
				{ name: 'You', color: 'var(--you)', values: you },
				{ name: result.profile.name, color: 'var(--adviser)', values: adviser },
				{ name: 'S&P 500', color: 'var(--market)', values: market }
			]}
		/>
		<input
			class="scrub"
			type="range"
			min="0"
			max={n - 1}
			bind:value={app.cursor}
			oninput={() => (playing = false)}
			aria-label="timeline"
		/>

		<h3 class="sub mono">What {result.profile.name} holds</h3>
		<WeightsRibbon weights={result.weights} assets={universe.assets} {cursorDate} />

		<div class="panels">
			<article class="letter">
				<p class="eyebrow mono">A letter from your adviser</p>
				{#if currentLetter}
					<h3>{currentLetter.title}</h3>
					<p>{currentLetter.body}</p>
				{/if}
			</article>
			<article class="event">
				<p class="eyebrow mono">Meanwhile, in the world</p>
				{#if lastEvent}
					<h3>{lastEvent.title}</h3>
					<p>{lastEvent.blurb}</p>
				{:else}
					<p class="muted">Quiet so far.</p>
				{/if}
			</article>
		</div>

		{#if app.cursor >= n - 1}
			<footer><button class="btn" onclick={() => go('debrief')}>See the debrief</button></footer>
		{/if}
	</section>
{/if}

<style>
	.journey {
		max-width: 72rem;
		margin: 0 auto;
		padding: 2rem 1.5rem 4rem;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 1rem;
		flex-wrap: wrap;
		margin-bottom: 1rem;
	}
	.eyebrow {
		font-size: 0.7rem;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		opacity: 0.7;
		margin: 0 0 0.3rem;
	}
	h1 {
		font-size: 1.8rem;
		margin: 0;
	}
	.controls {
		display: flex;
		gap: 1rem;
		align-items: center;
		font-size: 0.75rem;
	}
	.totals {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1rem;
		margin: 1rem 0;
	}
	.totals div {
		display: flex;
		flex-direction: column;
		border-top: 1px solid currentColor;
		padding-top: 0.4rem;
	}
	.totals span {
		font-size: 0.7rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}
	.totals strong {
		font-size: 1.6rem;
		font-weight: 500;
	}
	.totals em {
		font-style: normal;
		font-size: 0.8rem;
		opacity: 0.8;
	}
	.scrub {
		width: 100%;
		margin: 0.5rem 0 1.5rem;
	}
	.sub {
		font-size: 0.7rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		opacity: 0.7;
	}
	.panels {
		display: grid;
		grid-template-columns: 3fr 2fr;
		gap: 1.5rem;
		margin-top: 2rem;
	}
	@media (max-width: 40rem) {
		.panels {
			grid-template-columns: 1fr;
		}
	}
	article {
		border: 1px solid rgba(255, 255, 255, 0.15);
		padding: 1.2rem 1.4rem;
		background: var(--night-2);
	}
	article h3 {
		margin: 0 0 0.4rem;
	}
	article p {
		margin: 0;
	}
	footer {
		text-align: center;
		margin-top: 2.5rem;
	}
</style>
