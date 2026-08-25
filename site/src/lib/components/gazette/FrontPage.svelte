<script lang="ts">
	// The New Year's Day front page: the year in review, the market figures, and a notice
	// explaining how to use the paper (the site's own instructions, printed in its voice).
	import type { Archive, Note2015 } from '$lib/data';
	import { money, pct, signedPct } from '$lib/format';
	import Gazette from './Gazette.svelte';
	import Story from './Story.svelte';

	let { note, archive, amount, editions }: { note: Note2015; archive: Archive; amount: number; editions: number } = $props();
	const spy = $derived(archive.assets.SPY);
</script>

<Gazette
	label="The Archive Gazette, front page"
	earLeft={`New Year's Day edition<br><em>Where things stand</em>`}
	number={1}
	section="The year 2015 in review"
	sources={note.sources}
>
	<section class="gz-lead">
		<Story headline={note.headline} body={note.body} byline="From our markets desk · 31 December 2015" />
		<aside class="gz-box">
			<h3>Markets · 2015</h3>
			<table>
				<tbody>
					<tr><th>S&amp;P 500, 2015</th><td class:gz-neg={spy.return_2015 < 0}>{signedPct(spy.return_2015)}</td></tr>
					<tr><th>Worst fall during 2015</th><td class="gz-neg">{pct(spy.drawdown_2015)}</td></tr>
					<tr><th>S&amp;P 500, 2013–15</th><td>{signedPct(spy.return_3y)}</td></tr>
					<tr><th>US bonds (AGG), 2015</th><td class:gz-neg={archive.assets.AGG.return_2015 < 0}>{signedPct(archive.assets.AGG.return_2015)}</td></tr>
					<tr><th>Gold (GLD), 2015</th><td class:gz-neg={archive.assets.GLD.return_2015 < 0}>{signedPct(archive.assets.GLD.return_2015)}</td></tr>
					<tr><th>Cash (3-month T-bill)</th><td>{pct(archive.tbill_rate_annual, 2)} a year</td></tr>
				</tbody>
			</table>
			<p class="gz-fine">Returns include dividends. A "worst fall" is the largest drop from a previous high, known as the maximum drawdown.</p>
		</aside>
	</section>

	<aside class="gz-notice">
		<h3>To our reader, who has {money(amount)} to place</h3>
		<p>
			This paper was printed on the last day of 2015 and knows nothing after it. Read it the way an investor
			would have: one edition per sector, {editions} in all, each with the year's story, the figures, and the
			listings.
		</p>
		<ol>
			<li>Write an order in the margin of any listing you like: the dollars you want in that company or fund. Whatever you do not place stays in cash at the Treasury-bill rate.</li>
			<li>Your orders are filled once, on Monday 4 January 2016, and held for ten years untouched.</li>
			<li>At the back of the paper, under Situations Wanted, hire an adviser. They receive the same {money(amount)} and manage it by their own rules, so you can watch the two side by side.</li>
		</ol>
	</aside>
</Gazette>
