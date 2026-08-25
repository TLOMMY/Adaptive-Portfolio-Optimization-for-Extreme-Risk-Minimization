<script lang="ts">
	import { onMount } from 'svelte';
	import { app, go } from '$lib/state.svelte';
	import { loadEvents, loadIndex, loadPrices, loadUniverse, type MarketEvent, type Prices, type RunIndex, type Universe } from '$lib/data';
	import Disclaimer from '$lib/components/Disclaimer.svelte';
	import Prologue from '$lib/components/Prologue.svelte';
	import Rewind from '$lib/components/Rewind.svelte';
	import Archive from '$lib/components/Archive.svelte';
	import Simulator from '$lib/sim/Simulator.svelte';
	import Starfield from '$lib/components/Starfield.svelte';

	let universe = $state<Universe | null>(null);
	let index = $state<RunIndex | null>(null);
	let prices = $state<Prices | null>(null);
	let events = $state<MarketEvent[]>([]);
	let error = $state<string | null>(null);
	let starsGone = $state(false); // the starfield is unmounted once its fade-out has finished

	onMount(async () => {
		// dev shortcut: /?stage=rewind jumps straight to a screen
		const wanted = new URLSearchParams(location.search).get('stage');
		if (wanted) app.stage = wanted as typeof app.stage;
		try {
			[universe, prices, events, index] = await Promise.all([loadUniverse(), loadPrices(), loadEvents(), loadIndex()]);
		} catch (e) {
			error = String(e);
		}
	});

	const night = $derived(app.stage === 'disclaimer' || app.stage === 'prologue' || app.stage === 'rewind' || app.stage === 'journey');
	$effect(() => {
		document.body.dataset.world = night ? 'night' : app.stage === 'archive' ? 'desk' : 'paper';
	});
</script>

<div class="curtain" style:opacity={app.curtain} style:background={app.curtainColor} aria-hidden="true"></div>

<!-- one starfield spans the prologue and the timeline's opening, so the warp streaks never restart -->
{#if app.stage === 'prologue' || (app.stage === 'rewind' && !starsGone)}
	<div class="stars" class:over={app.stage === 'rewind'} style:opacity={app.starsLit ? 1 : 0} aria-hidden="true">
		<Starfield warp={app.warp} ondark={() => go('rewind', { curtain: false })} />
	</div>
{/if}

{#if error}
	<div class="stage"><p>Could not load data: {error}</p></div>
{:else if app.stage === 'disclaimer'}
	<Disclaimer />
{:else if app.stage === 'prologue'}
	<Prologue />
{:else if app.stage === 'rewind'}
	<Rewind
		{events}
		{prices}
		onlit={() => {
			setTimeout(() => (app.starsLit = false), 250);
			setTimeout(() => (starsGone = true), 2800);
		}}
	/>
{:else if !universe || !prices || !index}
	<div class="stage"><p class="muted">Opening the archive…</p></div>
{:else if app.stage === 'archive'}
	<Archive {universe} {prices} />
{:else}
	<Simulator mode="story" {index} {universe} {prices} {events} />
{/if}

<style>
	.curtain {
		position: fixed;
		inset: 0;
		z-index: 1000;
		pointer-events: none;
		transition: opacity 0.45s ease-in;
	}
	.stars {
		position: fixed;
		inset: 0;
		z-index: 0;
		pointer-events: none;
		transition: opacity 2.2s ease-in-out;
	}
	.stars.over {
		z-index: 20; /* above the timeline canvas while it fades in underneath */
	}
</style>
