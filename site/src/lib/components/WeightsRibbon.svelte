<script lang="ts">
	import { scaleLinear, scaleTime, area as d3area, stack, extent, scaleOrdinal, schemeTableau10 } from 'd3';
	import type { Asset } from '$lib/data';

	let {
		weights,
		assets,
		cursorDate,
		height = 140
	}: {
		weights: { dates: string[]; assets: string[]; rows: number[][] };
		assets: Asset[];
		cursorDate: string;
		height?: number;
	} = $props();

	let width = $state(800);
	const m = { top: 4, right: 90, bottom: 4, left: 8 };
	const kind = $derived(new Map(assets.map((a) => [a.ticker, a])));

	// Group into stocks (by sector), bonds & gold, cash — sectors are legible, 50 tickers are not.
	const groups = $derived.by(() => {
		const g = new Map<string, number[]>();
		weights.assets.forEach((t, j) => {
			const a = kind.get(t);
			const key = !a ? t : a.kind === 'cash' ? 'Cash' : a.sector;
			if (!g.has(key)) g.set(key, new Array(weights.rows.length).fill(0));
			const col = g.get(key)!;
			weights.rows.forEach((row, i) => (col[i] += row[j]));
		});
		return [...g.entries()].sort((a, b) => a[0].localeCompare(b[0]));
	});
	const keys = $derived(groups.map(([k]) => k));
	const data = $derived(weights.rows.map((_, i) => Object.fromEntries(groups.map(([k, col]) => [k, col[i]]))));
	const stacked = $derived(stack<Record<string, number>>().keys(keys)(data));
	const times = $derived(weights.dates.map((d) => Date.parse(d)));
	const cutoff = $derived(times.filter((t) => t <= Date.parse(cursorDate)).length);
	const x = $derived(scaleTime().domain(extent(times) as [number, number]).range([m.left, width - m.right]));
	const y = $derived(scaleLinear().domain([0, 1]).range([height - m.bottom, m.top]));
	const color = $derived(scaleOrdinal<string>().domain(keys).range([...schemeTableau10, '#c9c2b0', '#7d7a72']));
	const areaGen = $derived(
		d3area<[number, number]>()
			.x((_, i) => x(times[i]))
			.y0((d) => y(d[0]))
			.y1((d) => y(d[1]))
	);
</script>

<div class="wrap" bind:clientWidth={width}>
	<svg {width} {height}>
		{#each stacked as layer (layer.key)}
			<path d={areaGen(layer.slice(0, cutoff) as unknown as [number, number][]) ?? ''} fill={color(layer.key)} opacity="0.85">
				<title>{layer.key}</title>
			</path>
		{/each}
	</svg>
	<ul class="legend mono">
		{#each keys as k (k)}
			<li><span style:background={color(k)}></span>{k}</li>
		{/each}
	</ul>
</div>

<style>
	.wrap {
		width: 100%;
	}
	.legend {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem 0.9rem;
		padding: 0;
		margin: 0.3rem 0 0;
		font-size: 0.6rem;
		opacity: 0.8;
	}
	.legend span {
		display: inline-block;
		width: 0.6rem;
		height: 0.6rem;
		margin-right: 0.3rem;
		vertical-align: middle;
	}
</style>
