<script lang="ts">
	import { scaleLinear, scaleLog, scaleTime, line as d3line, curveStepAfter, curveLinear } from 'd3';
	import { spreadLabels, type Series } from './series';

	let {
		series,
		height = 320,
		log = false,
		fmt = (v: number) => v.toFixed(2),
		domain,
		zeroLine = false
	}: {
		series: Series[];
		height?: number;
		log?: boolean;
		fmt?: (v: number) => string;
		domain?: [number, number]; // fixed y domain, e.g. [min, 0] for drawdowns
		zeroLine?: boolean;
	} = $props();

	let width = $state(800);
	const m = { top: 14, right: 192, bottom: 26, left: 70 };

	const parsed = $derived(
		series.map((s) => ({ ...s, times: s.dates.map((d) => Date.parse(d)) }))
	);
	const tMin = $derived(Math.min(...parsed.map((s) => s.times[0] ?? Infinity)));
	const tMax = $derived(Math.max(...parsed.map((s) => s.times[s.times.length - 1] ?? -Infinity)));
	const x = $derived(scaleTime().domain([tMin, tMax]).range([m.left, width - m.right]));

	const allValues = $derived(parsed.flatMap((s) => s.values));
	const yDomain = $derived.by((): [number, number] => {
		if (domain) return domain;
		let lo = Math.min(...allValues),
			hi = Math.max(...allValues);
		if (log) return [lo * 0.95, hi * 1.05];
		const pad = (hi - lo) * 0.06 || 1;
		return [lo - pad, hi + pad];
	});
	const y = $derived(
		(log ? scaleLog() : scaleLinear()).domain(yDomain).range([height - m.bottom, m.top])
	);
	const ticks = $derived(log ? y.ticks(6).filter((_, i, a) => a.length <= 8 || i % 2 === 0) : y.ticks(5));

	const paths = $derived(
		parsed.map((s) => {
			const gen = d3line<number>()
				.x((_, i) => x(s.times[i]))
				.y((v) => y(v))
				.curve(s.step ? curveStepAfter : curveLinear);
			return { ...s, d: gen(s.values) ?? '' };
		})
	);
	const endLabels = $derived(
		spreadLabels(
			parsed
				.filter((s) => s.values.length)
				.map((s) => ({
					name: s.name,
					color: s.color,
					x: x(s.times[s.times.length - 1]),
					y: y(s.values[s.values.length - 1]),
					text: fmt(s.values[s.values.length - 1])
				})),
			12,
			m.top + 4,
			height - m.bottom - 4
		)
	);
	const years = $derived(x.ticks(Math.min(10, Math.max(2, Math.round(width / 90)))));
</script>

<div class="wrap" bind:clientWidth={width}>
	<svg {width} {height} role="img">
		{#each ticks as t (t)}
			<line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} class="grid" />
			<text x={m.left - 8} y={y(t)} dy="0.35em" text-anchor="end" class="tick mono">{fmt(t)}</text>
		{/each}
		{#if zeroLine}
			<line x1={m.left} x2={width - m.right} y1={y(0)} y2={y(0)} class="zero" />
		{/if}
		{#each years as t (t)}
			<text x={x(t)} y={height - 8} class="tick mono" text-anchor="middle">{new Date(t).getFullYear()}</text>
		{/each}
		{#each paths as s (s.name)}
			<path d={s.d} fill="none" stroke={s.color} stroke-width={s.dash ? 1.2 : 1.6} stroke-dasharray={s.dash ? '4 3' : undefined} opacity={s.dash ? 0.8 : 1} />
		{/each}
		{#each endLabels as l (l.name)}
			<line x1={l.x} x2={width - m.right + 4} y1={l.y} y2={l.y} stroke={l.color} opacity="0.4" />
			<text x={width - m.right + 6} y={l.y} dy="0.35em" class="label mono" fill={l.color}>
				{l.text} <tspan class="who">{l.name}</tspan>
			</text>
		{/each}
	</svg>
</div>

<style>
	.wrap {
		width: 100%;
	}
	.grid {
		stroke: currentColor;
		opacity: 0.1;
	}
	.zero {
		stroke: currentColor;
		opacity: 0.35;
	}
	.tick {
		font-size: 0.62rem;
		fill: currentColor;
		opacity: 0.6;
	}
	.label {
		font-size: 0.66rem;
	}
	.who {
		opacity: 0.7;
	}
</style>
