<script lang="ts">
	// Bonds, gold and cash: the places to hide, as a page of the Gazette with two short stories.
	import type { Archive, ArchiveAsset, Asset, Note2015 } from '$lib/data';
	import { pct, signedPct } from '$lib/format';
	import Gazette from './Gazette.svelte';
	import Listings from './Listings.svelte';
	import Story from './Story.svelte';

	let {
		bonds,
		gold,
		archive,
		assets,
		assetStats,
		assetNotes,
		allocations,
		onallocate,
		number
	}: {
		bonds: Note2015;
		gold: Note2015;
		archive: Archive;
		assets: Asset[];
		assetStats: Record<string, ArchiveAsset>;
		assetNotes: Record<string, string>;
		allocations: Record<string, number>;
		onallocate: (ticker: string, value: string) => void;
		number: number;
	} = $props();
</script>

<Gazette
	label="The Archive Gazette, bonds and gold"
	earLeft={`Commodities &amp; bonds<br><em>Somewhere to hide</em>`}
	{number}
	section="Beyond stocks · bonds, gold and cash"
	sources={[...bonds.sources, ...gold.sources]}
>
	<section class="gz-lead">
		<div class="two">
			<Story headline={bonds.headline} body={bonds.body} small byline="Bonds" />
			<Story headline={gold.headline} body={gold.body} small byline="Gold" />
		</div>
		<aside class="gz-box">
			<h3>Markets · beyond stocks</h3>
			<table>
				<tbody>
					<tr><th>US bonds (AGG), 2015</th><td class:gz-neg={archive.assets.AGG.return_2015 < 0}>{signedPct(archive.assets.AGG.return_2015)}</td></tr>
					<tr><th>US bonds, 2013–15</th><td class:gz-neg={archive.assets.AGG.return_3y < 0}>{signedPct(archive.assets.AGG.return_3y)}</td></tr>
					<tr><th>Gold (GLD), 2015</th><td class:gz-neg={archive.assets.GLD.return_2015 < 0}>{signedPct(archive.assets.GLD.return_2015)}</td></tr>
					<tr><th>Gold, 2013–15</th><td class:gz-neg={archive.assets.GLD.return_3y < 0}>{signedPct(archive.assets.GLD.return_3y)}</td></tr>
					<tr><th>Cash (3-month T-bill)</th><td>{pct(archive.tbill_rate_annual, 2)} a year</td></tr>
				</tbody>
			</table>
			<p class="gz-fine">Anything you do not place stays in cash at the Treasury-bill rate, which is what "cash" earns throughout the ten years.</p>
		</aside>
	</section>
	<Listings title="Funds that are not stocks" {assets} {assetStats} {assetNotes} {allocations} {onallocate} />
</Gazette>

<style>
	.two {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1.6rem;
		min-width: 0;
	}
	.two :global(.gz-columns) {
		column-count: 1;
	}
	@media (max-width: 48rem) {
		.two {
			grid-template-columns: 1fr;
		}
	}
</style>
