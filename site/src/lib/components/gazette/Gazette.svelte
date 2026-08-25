<script lang="ts">
	// The shell of every page of The Archive Gazette: newsprint, masthead, dateline, colophon.
	// Page components render their content into the `children` snippet.
	import type { Snippet } from 'svelte';

	let {
		earLeft,
		earRight = 'Price: your attention',
		number,
		section,
		sources = [],
		label,
		children
	}: {
		earLeft: string;
		earRight?: string;
		number: number;
		section: string;
		sources?: string[];
		label: string;
		children: Snippet;
	} = $props();
</script>

<article class="gz-paper" aria-label={label}>
	<svg class="gz-grain" aria-hidden="true">
		<filter id="newsprint"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" /><feColorMatrix type="saturate" values="0" /></filter>
		<rect width="100%" height="100%" filter="url(#newsprint)" />
	</svg>

	<header class="gz-masthead">
		<!-- ears sit either side of the title, as on a printed masthead; on narrow paper they move above it -->
		<div class="gz-top">
			<span class="gz-ear">{@html earLeft}</span>
			<h1 class="gz-title">The Archive Gazette</h1>
			<span class="gz-ear right">Vol. I · No. {number}<br /><em>{earRight}</em></span>
		</div>
		<p class="gz-motto">All the numbers that were fit to print, as they stood on the last day of 2015</p>
		<div class="gz-dateline">
			<span>Friday, 1 January 2016</span>
			<span>{section}</span>
			<span>Late edition</span>
		</div>
	</header>

	{@render children()}

	<footer class="gz-colophon">
		{#if sources.length}
			<details>
				<summary>Sources for this page</summary>
				<ul>{#each sources as s (s)}<li><a href={s} target="_blank" rel="noreferrer">{s}</a></li>{/each}</ul>
			</details>
		{/if}
		<p>The Archive Gazette is an invented title. Every statement in it was published on or before 31 December 2015 and checked against the source listed.</p>
	</footer>
</article>
