<script lang="ts">
	// Calendar-year returns for several series, as grouped bars.
	import { scaleBand, scaleLinear } from 'd3';
	import { pct } from '$lib/format';

	let {
		groups,
		height = 240
	}: { groups: { name: string; color: string; years: { year: number; value: number }[] }[]; height?: number } = $props();

	let width = $state(800);
	const m = { top: 14, right: 12, bottom: 24, left: 50 };
	const years = $derived([...new Set(groups.flatMap((g) => g.years.map((y) => y.year)))].sort());
	const x0 = $derived(scaleBand<number>().domain(years).range([m.left, width - m.right]).paddingInner(0.25));
	const x1 = $derived(scaleBand<string>().domain(groups.map((g) => g.name)).range([0, x0.bandwidth()]).padding(0.08));
	const values = $derived(groups.flatMap((g) => g.years.map((y) => y.value)));
	const lo = $derived(Math.min(0, ...values));
	const hi = $derived(Math.max(0, ...values));
	const y = $derived(scaleLinear().domain([lo * 1.1, hi * 1.1 || 0.1]).range([height - m.bottom, m.top]));
	const ticks = $derived(y.ticks(5));
</script>

<div class="wrap" bind:clientWidth={width}>
	<svg {width} {height} role="img">
		{#each ticks as t (t)}
			<line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} class="grid" class:zero={t === 0} />
			<text x={m.left - 8} y={y(t)} dy="0.35em" text-anchor="end" class="tick">{pct(t, 0)}</text>
		{/each}
		{#each years as yr (yr)}
			<text x={(x0(yr) ?? 0) + x0.bandwidth() / 2} y={height - 7} text-anchor="middle" class="tick">{yr}</text>
			{#each groups as g (g.name)}
				{@const v = g.years.find((d) => d.year === yr)?.value}
				{#if v !== undefined}
					<rect
						x={(x0(yr) ?? 0) + (x1(g.name) ?? 0)}
						y={Math.min(y(0), y(v))}
						width={x1.bandwidth()}
						height={Math.abs(y(v) - y(0))}
						fill={g.color}
						opacity="0.9"
					>
						<title>{g.name}, {yr}: {pct(v, 1)}</title>
					</rect>
				{/if}
			{/each}
		{/each}
	</svg>
	<ul class="legend">
		{#each groups as g (g.name)}<li><i style:background={g.color}></i>{g.name}</li>{/each}
	</ul>
</div>

<style>
	.wrap {
		width: 100%;
	}
	svg {
		font-family: var(--mono);
	}
	.grid {
		stroke: currentColor;
		opacity: 0.1;
	}
	.grid.zero {
		opacity: 0.4;
	}
	.tick {
		font-size: 0.62rem;
		fill: currentColor;
		opacity: 0.6;
	}
	.legend {
		list-style: none;
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem 1rem;
		padding: 0;
		margin: 0.3rem 0 0;
		font-family: var(--mono);
		font-size: 0.66rem;
		color: var(--dim);
	}
	.legend i {
		display: inline-block;
		width: 0.6rem;
		height: 0.6rem;
		margin-right: 0.35rem;
		vertical-align: middle;
	}
</style>
