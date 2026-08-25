<script lang="ts">
	// A multi-series time chart. Each series carries its own dates; the x domain is fixed by the caller
	// so a line grows across a still axis as the playback cursor moves.
	import { scaleLinear, scaleLog, scaleTime, line as d3line, curveStepAfter, curveLinear } from 'd3';
	import { spreadLabels, type Series } from './series';

	let {
		series,
		xDomain,
		cursorTime,
		height = 300,
		log = false,
		fmt = (v: number) => v.toFixed(2),
		domain,
		zeroLine = false
	}: {
		series: Series[];
		xDomain: [number, number];
		cursorTime?: number;
		height?: number;
		log?: boolean;
		fmt?: (v: number) => string;
		domain?: [number, number];
		zeroLine?: boolean;
	} = $props();

	let width = $state(800);
	// the right gutter holds the end labels; widen it for long series names
	const longest = $derived(Math.max(8, ...series.map((s) => s.name.length + 9)));
	const m = $derived({ top: 12, right: Math.min(260, 60 + longest * 6.2), bottom: 24, left: 62 });
	const parsed = $derived(series.map((s) => ({ ...s, times: s.dates.map((d) => Date.parse(d)) })));
	const x = $derived(scaleTime().domain(xDomain).range([m.left, width - m.right]));
	const allValues = $derived(parsed.flatMap((s) => s.values).filter((v) => Number.isFinite(v) && (!log || v > 0)));
	const yDomain = $derived.by((): [number, number] => {
		if (domain) return domain;
		if (!allValues.length) return log ? [1, 10] : [0, 1];
		const lo = Math.min(...allValues),
			hi = Math.max(...allValues);
		if (log) return [lo * 0.95, hi * 1.05];
		const pad = (hi - lo) * 0.06 || Math.abs(hi) * 0.1 || 1;
		return [lo - pad, hi + pad];
	});
	const y = $derived((log ? scaleLog() : scaleLinear()).domain(yDomain).range([height - m.bottom, m.top]));
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
			<text x={m.left - 8} y={y(t)} dy="0.35em" text-anchor="end" class="tick">{fmt(t)}</text>
		{/each}
		{#if zeroLine}
			<line x1={m.left} x2={width - m.right} y1={y(0)} y2={y(0)} class="zero" />
		{/if}
		{#each years as t (t)}
			<text x={x(t)} y={height - 7} class="tick" text-anchor="middle">{new Date(t).getFullYear()}</text>
		{/each}
		{#if cursorTime !== undefined}
			<line x1={x(cursorTime)} x2={x(cursorTime)} y1={m.top} y2={height - m.bottom} class="cursor" />
		{/if}
		{#each paths as s (s.name)}
			<path d={s.d} fill="none" stroke={s.color} stroke-width={s.dash ? 1.2 : 1.7} stroke-dasharray={s.dash ? '4 3' : undefined} opacity={s.dash ? 0.85 : 1} />
		{/each}
		{#each endLabels as l (l.name)}
			<circle cx={l.x} cy={y(parsed.find((s) => s.name === l.name)!.values.at(-1)!)} r="3" fill={l.color} />
			<text x={width - m.right + 8} y={l.y} dy="0.35em" class="label" fill={l.color}>
				{l.text} <tspan class="who">{l.name}</tspan>
			</text>
		{/each}
	</svg>
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
	.zero {
		stroke: currentColor;
		opacity: 0.35;
	}
	.cursor {
		stroke: currentColor;
		opacity: 0.25;
		stroke-dasharray: 2 3;
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
