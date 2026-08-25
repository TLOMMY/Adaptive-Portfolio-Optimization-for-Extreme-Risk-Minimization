<script lang="ts">
	// The lab: the same simulator as the story's ten years, opened empty (or from a ?runs= link)
	// with the playback at the end, so any investor × method runs can be laid side by side.
	import { onMount } from 'svelte';
	import { loadEvents, loadIndex, loadPrices, loadUniverse, type MarketEvent, type Prices, type RunIndex, type Universe } from '$lib/data';
	import Simulator from '$lib/sim/Simulator.svelte';

	let index = $state<RunIndex | null>(null);
	let universe = $state<Universe | null>(null);
	let prices = $state<Prices | null>(null);
	let events = $state<MarketEvent[]>([]);
	let error = $state<string | null>(null);

	onMount(async () => {
		document.body.dataset.world = 'night';
		try {
			[index, universe, prices, events] = await Promise.all([loadIndex(), loadUniverse(), loadPrices(), loadEvents()]);
		} catch (e) {
			error = String(e);
		}
	});
</script>

<svelte:head>
	<title>The Lab · Yesterday's Portfolio</title>
</svelte:head>

{#if error}
	<div class="stage"><p class="muted">Could not load data: {error}</p></div>
{:else if !index || !universe || !prices}
	<div class="stage"><p class="muted">Opening the lab…</p></div>
{:else}
	<Simulator mode="lab" {index} {universe} {prices} {events} />
{/if}
