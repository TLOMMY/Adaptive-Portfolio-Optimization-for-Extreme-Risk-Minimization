<script lang="ts">
	// One sector as a page of The Archive Gazette: the sector note as lead story, the sector
	// figures in a markets box, and the companies as listings with order slips.
	import type { ArchiveAsset, ArchiveSector, Asset, Note2015 } from '$lib/data';
	import { pct, signedPct } from '$lib/format';
	import Gazette from './Gazette.svelte';
	import Listings from './Listings.svelte';
	import Story from './Story.svelte';

	let {
		sector,
		edition,
		editions,
		note,
		stats,
		assets,
		assetStats,
		assetNotes,
		allocations,
		onallocate
	}: {
		sector: string;
		edition: number;
		editions: number;
		note: Note2015;
		stats: ArchiveSector;
		assets: Asset[];
		assetStats: Record<string, ArchiveAsset>;
		assetNotes: Record<string, string>;
		allocations: Record<string, number>;
		onallocate: (ticker: string, value: string) => void;
	} = $props();

	const name = (t: string) => assets.find((a) => a.ticker === t)?.name ?? t;
	const roman = (n: number) => ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII', 'XIV'][n - 1] ?? String(n);
</script>

<Gazette
	label={`The Archive Gazette, ${sector} edition`}
	earLeft={`Sector edition ${roman(edition)} of ${roman(editions)}<br><em>${sector}</em>`}
	number={edition + 1}
	section={`Year-end review · ${sector}`}
	sources={note.sources}
>
	<section class="gz-lead">
		<Story headline={note.headline} body={note.body} />
		<aside class="gz-box">
			<h3>Markets · {sector}</h3>
			<table>
				<tbody>
					<tr><th>Average return, 2015</th><td class:gz-neg={stats.return_2015 < 0}>{signedPct(stats.return_2015)}</td></tr>
					<tr><th>Best of 2015</th><td>{name(stats.best_2015.ticker)}<br /><small class:gz-neg={stats.best_2015.return < 0}>{signedPct(stats.best_2015.return)}</small></td></tr>
					<tr><th>Worst of 2015</th><td>{name(stats.worst_2015.ticker)}<br /><small class:gz-neg={stats.worst_2015.return < 0}>{signedPct(stats.worst_2015.return)}</small></td></tr>
					<tr><th>Worst fall during 2015</th><td class="gz-neg">{pct(stats.drawdown_2015)}</td></tr>
					<tr><th>Average return, 2013–15</th><td class:gz-neg={stats.return_3y < 0}>{signedPct(stats.return_3y)}</td></tr>
				</tbody>
			</table>
			<p class="gz-fine">Returns include dividends. A "worst fall" is the largest drop from a previous high, known as the maximum drawdown.</p>
		</aside>
	</section>
	<Listings {assets} {assetStats} {assetNotes} {allocations} {onallocate} />
</Gazette>
