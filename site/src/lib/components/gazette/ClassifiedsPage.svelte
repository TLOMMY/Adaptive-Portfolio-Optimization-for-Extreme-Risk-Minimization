<script lang="ts">
	// "Situations wanted": the six advisers as classified advertisements. Choosing one stamps it HIRED.
	import type { ProfileMeta } from '$lib/data';
	import { money, pct } from '$lib/format';
	import Avatar from '../Avatar.svelte';
	import Gazette from './Gazette.svelte';

	let {
		advisers,
		chosen,
		onchoose,
		amount,
		number,
		nameOf
	}: {
		advisers: ProfileMeta[];
		chosen: string;
		onchoose: (key: string) => void;
		amount: number;
		number: number;
		nameOf: (ticker: string) => string;
	} = $props();

	const avoids = (p: ProfileMeta) => [
		...Object.entries(p.sector_cap).filter(([, v]) => v === 0).map(([k]) => k),
		...p.exclude.map(nameOf)
	];
	const caps = (p: ProfileMeta) => Object.entries(p.sector_cap).filter(([, v]) => v > 0);
</script>

<Gazette
	label="The Archive Gazette, situations wanted"
	earLeft={`Classified advertisements<br><em>Situations wanted</em>`}
	{number}
	section="Situations wanted · portfolio managers seeking a client"
>
	<h2 class="gz-headline">Six advisers, each with {money(amount)} to manage and a rule they will not break</h2>
	<p class="gz-deck">
		An adviser here is a set of rules rather than a person: how long the money is for, the largest average
		loss they accept on a bad day, how many holdings they keep, and what they refuse to own. The loss limit is
		the daily CVaR, the average loss on the worst 5% of days, and it tightens as the horizon shrinks.
	</p>
	<div class="gz-ads">
		{#each advisers as p (p.key)}
			<button class="gz-ad" class:chosen={chosen === p.key} onclick={() => onchoose(p.key)} aria-pressed={chosen === p.key}>
				<span class="who">
					<span class="portrait"><Avatar profileKey={p.key} size={58} /></span>
					<span>
						<span class="name">{p.name}</span><br />
						<span class="type">{p.archetype} · risk tolerance {p.risk_tolerance.toLowerCase()}</span>
					</span>
				</span>
				<p class="copy">“{p.personality}”</p>
				<table class="vitals">
					<tbody>
						<tr><th>Horizon</th><td>{p.horizon_years} years</td></tr>
						<tr><th>Loss limit</th><td>{pct(p.cvar_start)} a day → {pct(p.cvar_end)}</td></tr>
						<tr><th>Holdings</th><td>at most {p.max_holdings}</td></tr>
						<tr><th>Cash floor</th><td>{pct(p.cash_min, 0)}</td></tr>
						{#if avoids(p).length}<tr><th>Will not own</th><td>{avoids(p).join(', ')}</td></tr>{/if}
						{#if caps(p).length}<tr><th>Sector caps</th><td>{caps(p).map(([k, v]) => `${k} ${pct(v, 0)}`).join(', ')}</td></tr>{/if}
					</tbody>
				</table>
				<span class="stamp">{chosen === p.key ? 'Hired' : 'Hire'}</span>
			</button>
		{/each}
	</div>
</Gazette>
