<script lang="ts">
	import type { Snippet } from 'svelte';
	let {
		title,
		explain,
		onhide,
		children,
		aside
	}: { title: string; explain: string; onhide: () => void; children: Snippet; aside?: Snippet } = $props();
</script>

<section class="panel">
	<header>
		<div>
			<h2>{title}</h2>
			<p class="explain">{explain}</p>
		</div>
		<div class="tools">
			{#if aside}{@render aside()}{/if}
			<button class="hide mono" onclick={onhide} aria-label="Hide {title}" title="Hide this panel">×</button>
		</div>
	</header>
	{@render children()}
</section>

<style>
	.panel {
		border-top: 1px solid var(--rule);
		padding: 1.2rem 0 1.6rem;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		margin-bottom: 0.8rem;
	}
	h2 {
		font-size: 1.15rem;
		margin: 0 0 0.2rem;
	}
	.explain {
		margin: 0;
		font-size: 0.9rem;
		color: var(--ink-soft);
		max-width: 60ch;
	}
	.tools {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		flex-shrink: 0;
	}
	.hide {
		border: 1px solid var(--rule);
		background: transparent;
		color: var(--ink-soft);
		width: 1.7rem;
		height: 1.7rem;
		line-height: 1;
		border-radius: 2px;
	}
	.hide:hover {
		border-color: var(--ink);
		color: var(--ink);
	}
</style>
