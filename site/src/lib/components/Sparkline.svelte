<script lang="ts">
	// A tiny line of normalised month-end prices; the baseline marks the starting level.
	let { values, width = 120, height = 32 }: { values: number[]; width?: number; height?: number } = $props();
	const lo = $derived(Math.min(...values, 1));
	const hi = $derived(Math.max(...values, 1));
	const y = (v: number) => height - 2 - ((v - lo) / (hi - lo || 1)) * (height - 4);
	const x = (i: number) => (i / Math.max(1, values.length - 1)) * width;
	const d = $derived(values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(''));
	const up = $derived(values[values.length - 1] >= 1);
</script>

<svg {width} {height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
	<line x1="0" x2={width} y1={y(1)} y2={y(1)} class="base" />
	<path {d} fill="none" class:up class="line" />
</svg>

<style>
	.base {
		stroke: currentColor;
		opacity: 0.25;
		stroke-dasharray: 2 2;
	}
	.line {
		stroke: var(--stamp);
		stroke-width: 1.4;
	}
	.line.up {
		stroke: var(--ink);
	}
</style>
