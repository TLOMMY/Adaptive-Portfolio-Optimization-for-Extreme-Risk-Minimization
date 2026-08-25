<script lang="ts">
	import { go } from '$lib/state.svelte';
</script>

<section class="stage">
	<div class="notice">
		<p class="eyebrow">Before you travel</p>
		<h1>This is a story, not advice.</h1>
		<p>
			Everything here uses real market prices from 2016 to 2025, but it is a university project about
			optimisation, built for curiosity. Nothing on this site is financial advice, and past returns say
			little about future ones.
		</p>
		<button class="go" onclick={() => go('prologue')}>I understand</button>
	</div>
</section>

<style>
	.stage {
		--fg: #e8e4da;
		--dim: #9aa0ad;
		--line: rgba(232, 228, 218, 0.16);
		font-family: 'IBM Plex Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
		color: var(--fg);
	}
	.notice {
		max-width: 32rem;
		border: 1px solid var(--line);
		padding: 2.4rem 2.6rem;
		background: rgba(255, 255, 255, 0.025);
	}
	.eyebrow {
		font-family: 'IBM Plex Mono', 'SF Mono', Menlo, Consolas, monospace;
		font-size: 0.62rem;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		color: var(--dim);
		margin: 0 0 1rem;
	}
	h1 {
		font-size: 1.8rem;
		font-weight: 600;
		letter-spacing: -0.01em;
		margin: 0 0 0.9rem;
	}
	p {
		margin: 0 0 1.6rem;
		line-height: 1.55;
		font-size: 0.98rem;
		color: var(--fg);
	}
	.go {
		border: 1px solid var(--fg);
		background: transparent;
		color: var(--fg);
		padding: 0.6rem 1.4rem;
		border-radius: 3px;
		font: inherit;
		font-size: 0.82rem;
		font-weight: 500;
		letter-spacing: 0.04em;
		cursor: pointer;
	}
	.go:hover {
		background: var(--fg);
		color: var(--night);
	}
</style>
