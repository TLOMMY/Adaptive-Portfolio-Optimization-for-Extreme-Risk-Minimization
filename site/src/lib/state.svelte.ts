// Global app state (Svelte 5 runes). One object, mutated in place.
export type Stage = 'disclaimer' | 'prologue' | 'rewind' | 'archive' | 'journey' | 'debrief';

export const app = $state({
	stage: 'disclaimer' as Stage,
	amount: 10_000, // the wish
	allocations: {} as Record<string, number>, // ticker -> dollars invested on day 0
	adviser: 'builder', // profile key
	cursor: 0 // index into the journey's date array
});

export const allocated = () => Object.values(app.allocations).reduce((s, v) => s + v, 0);
export const remaining = () => app.amount - allocated();

export function go(stage: Stage) {
	app.stage = stage;
	if (typeof window !== 'undefined') window.scrollTo({ top: 0 });
}
