<script lang="ts">
	// A headline, optional deck, byline and justified story, always in one column so every page of the
	// paper reads the same way. (Two balanced columns also misplace the floated drop cap when the story
	// is only a few words long.) Long stories still get the first sentence pulled out as the deck.
	let {
		headline,
		body,
		byline = 'From our markets desk',
		small = false
	}: { headline: string; body: string; byline?: string; small?: boolean } = $props();

	const split = $derived.by(() => {
		const m = body.match(/^(.+?[.!?])\s+(.*)$/s);
		if (m && m[2].length >= 260) return { deck: m[1], story: m[2] };
		return { deck: '', story: body };
	});
</script>

<div class="story">
	<h2 class="gz-headline" class:small>{headline}</h2>
	{#if split.deck}<p class="gz-deck">{split.deck}</p>{/if}
	<p class="gz-byline">{byline}</p>
	<div class="gz-columns single">
		<p class="gz-body dropcap">{split.story}</p>
	</div>
</div>
