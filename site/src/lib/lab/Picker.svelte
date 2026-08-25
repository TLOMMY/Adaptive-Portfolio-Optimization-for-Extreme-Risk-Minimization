<script lang="ts">
	import { untrack } from 'svelte';
	import type { ModelMeta, ProfileMeta } from '$lib/data';
	import { addRun, clearRuns, lab, removeRun } from './store.svelte';

	let { profiles, models }: { profiles: ProfileMeta[]; models: ModelMeta[] } = $props();
	let profile = $state(untrack(() => profiles[0]?.key ?? ''));
	let model = $state(untrack(() => models[0]?.key ?? ''));

	const profileName = (k: string) => profiles.find((p) => p.key === k)?.name ?? k;
	const modelName = (k: string) => models.find((m) => m.key === k)?.name ?? k;
	const blurb = $derived(models.find((m) => m.key === model)?.blurb ?? '');
	const persona = $derived(profiles.find((p) => p.key === profile));
</script>

<div class="picker">
	<div class="choose">
		<label>
			<span class="eyebrow mono">Investor</span>
			<select bind:value={profile}>
				{#each profiles as p (p.key)}<option value={p.key}>{p.name} · {p.archetype}</option>{/each}
			</select>
			{#if persona}<small class="muted">{persona.tagline}</small>{/if}
		</label>
		<label>
			<span class="eyebrow mono">Method</span>
			<select bind:value={model}>
				{#each models as m (m.key)}<option value={m.key}>{m.name}</option>{/each}
			</select>
			<small class="muted">{blurb}</small>
		</label>
		<div class="actions">
			<button class="btn" onclick={() => addRun(profile, model)}>Add to comparison</button>
			<button class="link mono" onclick={() => models.forEach((m) => addRun(profile, m.key))}>
				every method for {profileName(profile)}
			</button>
			<button class="link mono" onclick={() => profiles.forEach((p) => addRun(p.key, model))}>
				every investor under {modelName(model)}
			</button>
		</div>
	</div>

	<div class="chips">
		{#if lab.chosen.length === 0}
			<p class="muted">Nothing chosen yet. Add a run above, or pick a whole row or column of the grid.</p>
		{/if}
		{#each lab.chosen as c (c.key)}
			<span class="chip mono" style:--c={c.color}>
				<i></i>
				{profileName(c.profile)} · {modelName(c.model)}
				{#if lab.loading[c.key]}<em>loading</em>{/if}
				<button onclick={() => removeRun(c.key)} aria-label="Remove">×</button>
			</span>
		{/each}
		{#if lab.chosen.length > 1}
			<button class="link mono" onclick={clearRuns}>clear all</button>
		{/if}
	</div>
</div>

<style>
	.picker {
		border: 1px solid var(--rule);
		background: var(--paper-deep);
		padding: 1.2rem 1.4rem;
		margin: 1.5rem 0;
	}
	.choose {
		display: grid;
		grid-template-columns: 1fr 1fr auto;
		gap: 1.2rem;
		align-items: start;
	}
	@media (max-width: 52rem) {
		.choose {
			grid-template-columns: 1fr;
		}
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.eyebrow {
		font-size: 0.65rem;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		color: var(--stamp);
	}
	select {
		font: inherit;
		background: var(--paper);
		color: inherit;
		border: 1px solid var(--rule);
		padding: 0.45rem 0.6rem;
		border-radius: 2px;
	}
	small {
		font-size: 0.8rem;
		line-height: 1.35;
	}
	.actions {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		align-items: flex-start;
		padding-top: 1.1rem;
	}
	.link {
		background: none;
		border: none;
		padding: 0;
		font-size: 0.7rem;
		color: var(--ink-soft);
		text-decoration: underline;
		text-underline-offset: 0.2em;
		text-align: left;
	}
	.link:hover {
		color: var(--ink);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: center;
		margin-top: 1.1rem;
		min-height: 1.8rem;
	}
	.chips p {
		margin: 0;
		font-size: 0.85rem;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		font-size: 0.7rem;
		border: 1px solid var(--rule);
		border-left: 3px solid var(--c);
		background: var(--paper);
		padding: 0.3rem 0.4rem 0.3rem 0.6rem;
	}
	.chip i {
		width: 0.55rem;
		height: 0.55rem;
		background: var(--c);
		border-radius: 50%;
	}
	.chip em {
		font-style: normal;
		opacity: 0.5;
	}
	.chip button {
		border: none;
		background: none;
		color: var(--ink-soft);
		padding: 0 0.2rem;
		font-size: 0.9rem;
		line-height: 1;
	}
	.chip button:hover {
		color: var(--stamp);
	}
</style>
