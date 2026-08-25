<script lang="ts">
	import { scaleLinear, scaleTime, line as d3line, extent, max } from 'd3';
	import type { MarketEvent } from '$lib/data';

	interface Series {
		name: string;
		color: string;
		values: number[];
	}
	let {
		dates,
		series,
		cursor,
		events = [],
		height = 360
	}: { dates: string[]; series: Series[]; cursor: number; events?: MarketEvent[]; height?: number } = $props();

	let width = $state(800);
	const m = { top: 16, right: 90, bottom: 28, left: 8 };

	const times = $derived(dates.map((d) => Date.parse(d)));
	const x = $derived(scaleTime().domain(extent(times) as [number, number]).range([m.left, width - m.right]));
	const yMax = $derived(max(series, (s) => max(s.values)) ?? 1);
	const yMin = $derived(Math.min(...series.map((s) => Math.min(...s.values))));
	const y = $derived(scaleLinear().domain([yMin * 0.9, yMax * 1.05]).range([height - m.bottom, m.top]));
	const path = $derived(
		d3line<number>()
			.x((_, i) => x(times[i]))
			.y((v) => y(v))
	);
	const years = $derived(x.ticks(10));
	const shown = $derived(events.filter((e) => Date.parse(e.date) <= times[Math.min(cursor, times.length - 1)]));
	const fmt = (v: number) => '$' + (v >= 1e6 ? (v / 1e6).toFixed(2) + 'm' : (v / 1e3).toFixed(0) + 'k');
</script>

<div class="wrap" bind:clientWidth={width}>
	<svg {width} {height}>
		{#each y.ticks(5) as t (t)}
			<line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} class="grid" />
			<text x={width - m.right + 6} y={y(t)} dy="0.35em" class="tick mono">{fmt(t)}</text>
		{/each}
		{#each years as t (t)}
			<text x={x(t)} y={height - 8} class="tick mono" text-anchor="middle">{new Date(t).getFullYear()}</text>
		{/each}
		{#each shown as e (e.date)}
			<line x1={x(Date.parse(e.date))} x2={x(Date.parse(e.date))} y1={m.top} y2={height - m.bottom} class="event" />
			<text x={x(Date.parse(e.date)) + 4} y={m.top + 10} class="event-label mono">{e.title}</text>
		{/each}
		{#each series as s (s.name)}
			<path d={path(s.values.slice(0, cursor + 1)) ?? ''} fill="none" stroke={s.color} stroke-width="1.8" />
			{#if cursor > 0}
				<circle cx={x(times[cursor])} cy={y(s.values[cursor])} r="3.5" fill={s.color} />
				<text x={x(times[cursor]) + 8} y={y(s.values[cursor])} dy="0.35em" class="label mono" fill={s.color}>
					{fmt(s.values[cursor])}
				</text>
			{/if}
		{/each}
	</svg>
</div>

<style>
	.wrap {
		width: 100%;
	}
	.grid {
		stroke: currentColor;
		opacity: 0.12;
	}
	.tick {
		font-size: 0.65rem;
		fill: currentColor;
		opacity: 0.6;
	}
	.event {
		stroke: currentColor;
		opacity: 0.25;
		stroke-dasharray: 2 3;
	}
	.event-label {
		font-size: 0.6rem;
		fill: currentColor;
		opacity: 0.55;
	}
	.label {
		font-size: 0.7rem;
	}
</style>
