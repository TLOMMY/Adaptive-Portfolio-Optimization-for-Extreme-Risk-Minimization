<script lang="ts">
	import { onMount } from 'svelte';
	import { app } from '$lib/state.svelte';
	import { loadEvents, loadPrices, loadUniverse, type MarketEvent, type Prices, type Universe } from '$lib/data';
	import Disclaimer from '$lib/components/Disclaimer.svelte';
	import Prologue from '$lib/components/Prologue.svelte';
	import Rewind from '$lib/components/Rewind.svelte';
	import Archive from '$lib/components/Archive.svelte';
	import Journey from '$lib/components/Journey.svelte';
	import Debrief from '$lib/components/Debrief.svelte';

	let universe = $state<Universe | null>(null);
	let prices = $state<Prices | null>(null);
	let events = $state<MarketEvent[]>([]);
	let error = $state<string | null>(null);

	onMount(async () => {
		// dev shortcut: /?stage=rewind jumps straight to a screen
		const wanted = new URLSearchParams(location.search).get('stage');
		if (wanted) app.stage = wanted as typeof app.stage;
		try {
			[universe, prices, events] = await Promise.all([loadUniverse(), loadPrices(), loadEvents()]);
		} catch (e) {
			error = String(e);
		}
	});

	const night = $derived(app.stage === 'rewind' || app.stage === 'journey' || app.stage === 'prologue');
	$effect(() => {
		document.body.dataset.world = night ? 'night' : 'paper';
	});
</script>

{#if error}
	<div class="stage"><p>Could not load data: {error}</p></div>
{:else if app.stage === 'disclaimer'}
	<Disclaimer />
{:else if app.stage === 'prologue'}
	<Prologue />
{:else if app.stage === 'rewind'}
	<Rewind {events} {prices} />
{:else if !universe || !prices}
	<div class="stage"><p class="muted">Opening the archive…</p></div>
{:else if app.stage === 'archive'}
	<Archive {universe} {prices} />
{:else if app.stage === 'journey'}
	<Journey {universe} {prices} {events} />
{:else}
	<Debrief {universe} {prices} />
{/if}
