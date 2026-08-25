// State for the lab: which runs are being compared and which panels are shown.
import { schemeTableau10 } from 'd3';
import { loadRun, runKey, type RunResult } from '$lib/data';

export interface Chosen {
	key: string; // profile__model
	profile: string;
	model: string;
	color: string;
}

export const PANELS = [
	{ id: 'value', title: 'Value of $100,000', default: true },
	{ id: 'drawdown', title: 'Drawdown', default: true },
	{ id: 'table', title: 'The numbers', default: true },
	{ id: 'rollret', title: 'Rolling one-year return', default: false },
	{ id: 'rollvol', title: 'Rolling one-year volatility', default: false },
	{ id: 'risk', title: 'Realised loss against the promise', default: false },
	{ id: 'cost', title: 'Trading costs', default: false },
	{ id: 'weights', title: 'What one run held', default: false }
] as const;
export type PanelId = (typeof PANELS)[number]['id'];

const STORAGE = 'lab.panels';

/** Short names for chart labels, where the full names would not fit. */
export const MODEL_SHORT: Record<string, string> = {
	cvar: 'CVaR',
	markowitz: 'MV',
	markowitz_lw: 'MV+LW',
	robust: 'Robust',
	equal: '1/N'
};
export const shortLabel = (profileName: string, modelKey: string) =>
	`${profileName.replace(/^The /, '')} · ${MODEL_SHORT[modelKey] ?? modelKey}`;

function readPanels(): PanelId[] {
	try {
		const raw = localStorage.getItem(STORAGE);
		if (raw) {
			const ids = JSON.parse(raw) as string[];
			return PANELS.filter((p) => ids.includes(p.id)).map((p) => p.id);
		}
	} catch {
		/* storage unavailable: fall through */
	}
	return PANELS.filter((p) => p.default).map((p) => p.id);
}

export const lab = $state({
	chosen: [] as Chosen[],
	runs: {} as Record<string, RunResult>, // loaded run files by key
	loading: {} as Record<string, boolean>,
	visible: [] as PanelId[],
	ribbonKey: '' as string // which chosen run the weights ribbon shows
});

export function initPanels() {
	lab.visible = readPanels();
}

function savePanels() {
	try {
		localStorage.setItem(STORAGE, JSON.stringify(lab.visible));
	} catch {
		/* ignore */
	}
}

export function showPanel(id: PanelId) {
	if (!lab.visible.includes(id)) {
		// keep canonical order
		lab.visible = PANELS.map((p) => p.id).filter((p) => p === id || lab.visible.includes(p));
		savePanels();
	}
}

export function hidePanel(id: PanelId) {
	lab.visible = lab.visible.filter((p) => p !== id);
	savePanels();
}

function nextColor(): string {
	const used = new Set(lab.chosen.map((c) => c.color));
	return schemeTableau10.find((c) => !used.has(c)) ?? schemeTableau10[lab.chosen.length % 10];
}

export async function addRun(profile: string, model: string) {
	const key = runKey(profile, model);
	if (lab.chosen.some((c) => c.key === key)) return;
	lab.chosen = [...lab.chosen, { key, profile, model, color: nextColor() }];
	if (!lab.ribbonKey) lab.ribbonKey = key;
	if (!lab.runs[key] && !lab.loading[key]) {
		lab.loading[key] = true;
		try {
			lab.runs[key] = await loadRun(profile, model);
		} finally {
			lab.loading[key] = false;
		}
	}
}

export function removeRun(key: string) {
	lab.chosen = lab.chosen.filter((c) => c.key !== key);
	if (lab.ribbonKey === key) lab.ribbonKey = lab.chosen[0]?.key ?? '';
}

export function clearRuns() {
	lab.chosen = [];
	lab.ribbonKey = '';
}

/** The chosen runs whose files have arrived, in the order they were added. */
export function loadedRuns(): (Chosen & { run: RunResult })[] {
	return lab.chosen.filter((c) => lab.runs[c.key]).map((c) => ({ ...c, run: lab.runs[c.key] }));
}
