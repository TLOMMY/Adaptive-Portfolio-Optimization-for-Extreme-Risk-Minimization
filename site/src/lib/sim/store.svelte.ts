// State for the simulator: which series are shown, which analyses are open, and where the playback is.
// The same store drives the story's ten years and the lab; the story pre-loads it, the lab starts empty.
import { schemeTableau10 } from 'd3';
import { loadRun, runKey, type RunResult } from '$lib/data';

export type Kind = 'you' | 'run' | 'spy';

export interface Entry {
	key: string; // 'you', 'spy', or profile__model
	kind: Kind;
	label: string; // short, for chart labels
	full: string; // long, for lists and tables
	color: string;
	profile?: string;
	model?: string;
}

export const PANELS = [
	{ id: 'value', title: 'Value', default: true, explain: 'How the money grew, day by day. With the logarithmic axis on, equal vertical distances mean equal percentage changes, so a doubling looks the same at $10,000 and $30,000.' },
	{ id: 'howitwent', title: 'How it went', default: true, explain: 'The numbers so far, one row per series and computed up to the playback date. CAGR (compound annual growth rate) is the single yearly return that would produce the same value; volatility is how widely daily returns scatter, annualised; Sharpe is return above cash per unit of volatility, and higher is better.' },
	{ id: 'drawdown', title: 'Drawdown', default: true, explain: 'How far each series sits below the highest value it has reached so far. Zero means a new high; the deepest point is the worst loss an investor would have lived through.' },
	{ id: 'letter', title: 'A letter from the adviser', default: true, explain: 'What the chosen adviser did at its latest decision before the playback date, in its own words, built from the solve log.' },
	{ id: 'world', title: 'Meanwhile, in the world', default: true, explain: 'The latest market or world event before the playback date.' },
	{ id: 'weights', title: 'What one run held', default: false, explain: 'The share of one run in each sector, week by week, up to the playback date. Bonds, gold and cash are shown separately from stocks.' },
	{ id: 'yearly', title: 'Returns by year', default: false, explain: 'Each calendar year\'s return for every series, side by side, so you can see which years made the difference.' },
	{ id: 'heatmap', title: 'Returns by month', default: false, explain: 'Every calendar month\'s return for one chosen series, laid out as a year-by-month grid. Red is a losing month, green a winning one.' },
	{ id: 'rollret', title: 'Rolling one-year return', default: false, explain: 'On each day, the return over the previous 252 trading days (about one year). It shows when a series was ahead or behind rather than only where it ended.' },
	{ id: 'rollvol', title: 'Rolling one-year volatility', default: false, explain: 'The annualised standard deviation of daily returns over the previous 252 trading days. Higher means a bumpier ride.' },
	{ id: 'risk', title: 'Realised loss against the promise', default: false, explain: 'Each adviser has a loss limit: the average loss allowed on the worst 5% of days (daily CVaR at 95%), which tightens as the horizon shrinks. Dashed is the limit at each decision; solid is what the chosen portfolio would have lost on the worst days of the three years the model could see.' },
	{ id: 'holdings', title: 'Positions held', default: false, explain: 'How many different stocks and funds each run held after each decision.' },
	{ id: 'cost', title: 'Trading costs', default: false, explain: 'Every trade costs 0.1% of the amount traded. This is the running total each run paid, in dollars, scaled to your starting amount.' }
] as const;
export type PanelId = (typeof PANELS)[number]['id'];

const STORAGE = 'sim.panels';

export const MODEL_SHORT: Record<string, string> = {
	cvar: 'CVaR',
	markowitz: 'MV',
	markowitz_lw: 'MV+LW',
	robust: 'Robust',
	equal: '1/N'
};

export const sim = $state({
	entries: [] as Entry[],
	runs: {} as Record<string, RunResult>,
	loading: {} as Record<string, boolean>,
	visible: [] as PanelId[],
	cursor: 0,
	playing: false,
	speed: 6, // trading days per animation frame
	log: false,
	focusKey: '' // the run the letter, ribbon and heatmap panels look at
});

export function initPanels(override?: string | null) {
	if (override === 'all') {
		sim.visible = PANELS.map((p) => p.id);
		return;
	}
	if (override) {
		sim.visible = PANELS.map((p) => p.id).filter((p) => override.split(',').includes(p));
		return;
	}
	try {
		const raw = localStorage.getItem(STORAGE);
		if (raw) {
			const ids = JSON.parse(raw) as string[];
			sim.visible = PANELS.filter((p) => ids.includes(p.id)).map((p) => p.id);
			return;
		}
	} catch {
		/* storage unavailable */
	}
	sim.visible = PANELS.filter((p) => p.default).map((p) => p.id);
}
function savePanels() {
	try {
		localStorage.setItem(STORAGE, JSON.stringify(sim.visible));
	} catch {
		/* ignore */
	}
}
export function togglePanel(id: PanelId) {
	if (sim.visible.includes(id)) sim.visible = sim.visible.filter((p) => p !== id);
	else sim.visible = PANELS.map((p) => p.id).filter((p) => p === id || sim.visible.includes(p));
	savePanels();
}
export function hidePanel(id: PanelId) {
	sim.visible = sim.visible.filter((p) => p !== id);
	savePanels();
}

function nextColor(): string {
	const used = new Set(sim.entries.map((c) => c.color));
	return schemeTableau10.find((c) => !used.has(c) && c !== '#e15759') ?? schemeTableau10[sim.entries.length % 10];
}

export function addYou() {
	if (!sim.entries.some((e) => e.kind === 'you')) sim.entries = [{ key: 'you', kind: 'you', label: 'You', full: 'You · bought once, held ten years', color: 'var(--you)' }, ...sim.entries];
}
export function addSpy() {
	if (!sim.entries.some((e) => e.kind === 'spy')) sim.entries = [...sim.entries, { key: 'spy', kind: 'spy', label: 'S&P 500', full: 'S&P 500 · bought once, held', color: 'var(--market)' }];
}
export async function addRun(profile: string, model: string, names: { profile: string; model: string }) {
	const key = runKey(profile, model);
	if (sim.entries.some((c) => c.key === key)) return;
	const entry: Entry = {
		key,
		kind: 'run',
		label: `${names.profile.replace(/^The /, '')} · ${MODEL_SHORT[model] ?? model}`,
		full: `${names.profile} · ${names.model}`,
		color: nextColor(),
		profile,
		model
	};
	// runs go before the S&P 500 so the benchmark stays last
	const spy = sim.entries.find((e) => e.kind === 'spy');
	sim.entries = [...sim.entries.filter((e) => e.kind !== 'spy'), entry, ...(spy ? [spy] : [])];
	if (!sim.focusKey) sim.focusKey = key;
	if (!sim.runs[key] && !sim.loading[key]) {
		sim.loading[key] = true;
		try {
			sim.runs[key] = await loadRun(profile, model);
		} finally {
			sim.loading[key] = false;
		}
	}
}
export function removeEntry(key: string) {
	sim.entries = sim.entries.filter((c) => c.key !== key);
	if (sim.focusKey === key) sim.focusKey = sim.entries.find((e) => e.kind === 'run')?.key ?? '';
}
export function reset() {
	sim.entries = [];
	sim.focusKey = '';
	sim.cursor = 0;
	sim.playing = false;
}
