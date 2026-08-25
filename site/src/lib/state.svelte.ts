// Global app state (Svelte 5 runes). One object, mutated in place.
export type Stage = 'disclaimer' | 'prologue' | 'rewind' | 'archive' | 'journey';

export const app = $state({
	stage: 'disclaimer' as Stage,
	amount: 10_000, // the wish
	allocations: {} as Record<string, number>, // ticker -> dollars invested on day 0
	adviser: 'builder', // profile key
	cursor: 0, // index into the journey's date array
	warp: false, // the wish has been made: the starfield is streaking
	starsLit: true, // the starfield is visible (fades out once the timeline has drawn)
	curtain: 0, // 0..1 opacity of the fade between stages
	curtainColor: '#0b0d12'
});

export const allocated = () => Object.values(app.allocations).reduce((s, v) => s + v, 0);
export const remaining = () => app.amount - allocated();

/** Change stage behind a short fade: darken (450 ms), switch, then lift the curtain. */
export function go(stage: Stage, opts: { curtain?: boolean } = {}) {
	if (typeof window === 'undefined' || opts.curtain === false) {
		app.stage = stage;
		if (typeof window !== 'undefined') window.scrollTo({ top: 0 });
		return;
	}
	app.curtainColor = stage === 'archive' ? '#1c1a17' : '#0b0d12';
	app.curtain = 1;
	setTimeout(() => {
		app.stage = stage;
		window.scrollTo({ top: 0 });
		requestAnimationFrame(() => requestAnimationFrame(() => (app.curtain = 0)));
	}, 450);
}
