<script lang="ts">
	// Monthly returns as a year × month grid. Losses are red, gains green, scaled to ±10%.
	import { interpolateRdYlGn, scaleDiverging } from 'd3';
	import { pct } from '$lib/format';

	let { cells }: { cells: { year: number; month: number; value: number }[] } = $props();
	const years = $derived([...new Set(cells.map((c) => c.year))].sort());
	const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const color = scaleDiverging(interpolateRdYlGn).domain([-0.1, 0, 0.1]);
	const at = (y: number, m: number) => cells.find((c) => c.year === y && c.month === m);
	const yearTotal = (y: number) => cells.filter((c) => c.year === y).reduce((acc, c) => acc * (1 + c.value), 1) - 1;
</script>

<div class="scroll">
	<table>
		<thead>
			<tr><th></th>{#each months as m (m)}<th>{m}</th>{/each}<th class="tot">Year</th></tr>
		</thead>
		<tbody>
			{#each years as y (y)}
				<tr>
					<th>{y}</th>
					{#each months as _, i (i)}
						{@const c = at(y, i + 1)}
						{#if c}
							<td style:background={color(c.value)} style:color={Math.abs(c.value) > 0.06 ? '#111' : '#222'} title={`${months[i]} ${y}: ${pct(c.value, 1)}`}>{pct(c.value, 1)}</td>
						{:else}
							<td class="empty"></td>
						{/if}
					{/each}
					<td class="tot" class:neg={yearTotal(y) < 0}>{pct(yearTotal(y), 1)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.scroll {
		overflow-x: auto;
	}
	table {
		border-collapse: separate;
		border-spacing: 2px;
		font-family: var(--mono);
		font-size: 0.68rem;
		width: 100%;
	}
	th {
		font-weight: 500;
		color: var(--dim);
		text-align: center;
		padding: 0.2rem 0.3rem;
	}
	tbody th {
		text-align: right;
	}
	td {
		text-align: right;
		padding: 0.35rem 0.4rem;
		font-variant-numeric: tabular-nums;
		border-radius: 2px;
	}
	td.empty {
		background: transparent;
	}
	td.tot {
		background: transparent;
		color: var(--fg);
		font-weight: 600;
		border-left: 1px solid var(--line);
	}
	td.tot.neg {
		color: var(--bad);
	}
</style>
