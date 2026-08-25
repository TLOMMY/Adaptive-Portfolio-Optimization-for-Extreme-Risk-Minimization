<script lang="ts">
	import { go } from '$lib/state.svelte';
</script>

<section class="stage">
	<div class="card">
		<p class="eyebrow mono">Before you travel</p>
		<h1>This is a story, not advice.</h1>
		<p>
			Everything here uses real market prices from 2016 to 2025, but it is a university project about
			optimisation, built for curiosity. Nothing on this site is financial advice, and past returns say
			little about future ones.
		</p>
		<button class="btn" onclick={() => go('prologue')}>I understand</button>
	</div>
</section>

<style>
	.card {
		max-width: 34rem;
		border: 1px solid var(--rule);
		padding: 2.5rem;
		background: var(--paper);
	}
	.eyebrow {
		font-size: 0.7rem;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		color: var(--stamp);
		margin: 0 0 1rem;
	}
	h1 {
		font-size: 2rem;
	}
	p {
		margin: 0 0 1.5rem;
	}
</style>
