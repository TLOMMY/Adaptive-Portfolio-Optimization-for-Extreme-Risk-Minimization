<script lang="ts">
	// The stock-listings table with an order slip per row. Used by the sector and funds pages.
	import type { ArchiveAsset, Asset } from '$lib/data';
	import { pct, signedPct } from '$lib/format';
	import Sparkline from '../Sparkline.svelte';

	let {
		title = 'Where the money could go',
		assets,
		assetStats,
		assetNotes,
		allocations,
		onallocate
	}: {
		title?: string;
		assets: Asset[];
		assetStats: Record<string, ArchiveAsset>;
		assetNotes: Record<string, string>;
		allocations: Record<string, number>;
		onallocate: (ticker: string, value: string) => void;
	} = $props();
</script>

<section class="gz-listings">
	<h3 class="gz-section-head"><span>Listings</span> {title}</h3>
	<table class="gz-stocks">
		<thead>
			<tr>
				<th class="tk">Sym.</th>
				<th>Company</th>
				<th class="num">2015</th>
				<th class="num">3 yrs</th>
				<th class="num">Worst fall</th>
				<th class="spark">2013–15</th>
				<th class="buy">Your order ($)</th>
			</tr>
		</thead>
		<tbody>
			{#each assets as a (a.ticker)}
				{@const st = assetStats[a.ticker]}
				<tr class:held={(allocations[a.ticker] ?? 0) > 0}>
					<td class="tk">{a.ticker}</td>
					<td class="co">
						<strong>{a.name}</strong>
						{#if assetNotes[a.ticker]}<span class="wire">{assetNotes[a.ticker]}</span>{/if}
					</td>
					<td class="num" class:gz-neg={st.return_2015 < 0}>{signedPct(st.return_2015)}</td>
					<td class="num" class:gz-neg={st.return_3y < 0}>{signedPct(st.return_3y)}</td>
					<td class="num gz-neg">{pct(st.drawdown_3y)}</td>
					<td class="spark"><Sparkline values={st.spark} width={96} height={26} /></td>
					<td class="buy">
						<label>
							<span>$</span>
							<input
								inputmode="numeric"
								value={allocations[a.ticker] ?? ''}
								placeholder="—"
								onchange={(e) => onallocate(a.ticker, (e.target as HTMLInputElement).value)}
								aria-label={`dollars in ${a.name}`}
							/>
						</label>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</section>
