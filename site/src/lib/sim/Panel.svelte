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
			<button class="hide" onclick={onhide} aria-label="Hide {title}" title="Hide this panel">×</button>
		</div>
	</header>
	{@render children()}
</section>

<style>
	.panel {
		border-top: 1px solid var(--line);
		padding: 1rem 0 1.4rem;
	}
	header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		margin-bottom: 0.7rem;
	}
	h2 {
		font-size: 0.95rem;
		font-weight: 600;
		letter-spacing: 0.01em;
		margin: 0 0 0.2rem;
	}
	.explain {
		margin: 0;
		font-size: 0.82rem;
		color: var(--dim);
		max-width: 68ch;
		line-height: 1.45;
	}
	.tools {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		flex-shrink: 0;
	}
	.hide {
		border: 1px solid var(--line);
		background: transparent;
		color: var(--dim);
		width: 1.6rem;
		height: 1.6rem;
		line-height: 1;
		border-radius: 3px;
		font: inherit;
	}
	.hide:hover {
		border-color: var(--fg);
		color: var(--fg);
	}
</style>
