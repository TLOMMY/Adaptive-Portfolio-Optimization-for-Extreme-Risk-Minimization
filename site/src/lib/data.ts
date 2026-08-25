// Loaders and types for the JSON produced by the Python pipeline (src/portfolio/export.py).
// Every field name here matches a key written by export.py; if one is renamed there, rename it here.
import { base } from '$app/paths';

export interface Asset {
	ticker: string;
	name: string;
	sector: string;
	kind: 'stock' | 'etf' | 'cash';
}

export interface Universe {
	assets: Asset[];
	benchmark: string;
	start: string;
	end: string;
}

export interface Prices {
	dates: string[];
	assets: string[];
	rows: number[][]; // normalised to 1.0 on the first date
}

export interface Solve {
	date: string;
	reason: 'start' | 'calendar' | 'drift' | 'volatility';
	years_left: number;
	cvar_limit: number; // the investor's promise on that day
	exp_return_ann: number;
	cvar: number; // realised CVaR of the chosen weights over the scenarios (all models)
	risk: number; // the model's own risk measure: CVaR for cvar, daily volatility for the others
	turnover: number;
	cost: number;
	n_holdings: number;
	solve_time: number;
}

export interface Trade {
	date: string;
	asset: string;
	from: number;
	to: number;
}

export interface Metrics {
	start_value: number;
	end_value: number;
	total_return: number;
	cagr: number;
	volatility: number;
	sharpe: number;
	sortino: number;
	max_drawdown: number;
	max_drawdown_date: string;
	worst_month: number;
	best_month: number;
	cvar_95_daily: number;
	years: number;
}

export interface ProfileMeta {
	key: string;
	name: string;
	tagline: string;
	archetype: string; // e.g. "Growth", "Capital preservation"
	personality: string; // one sentence in the adviser's voice
	risk_tolerance: 'Low' | 'Moderate' | 'High' | 'Very high';
	horizon_years: number;
	cvar_start: number;
	cvar_end: number;
	max_holdings: number;
	w_max: number;
	cash_min: number;
	sector_cap: Record<string, number>;
	exclude: string[];
}

export interface ModelMeta {
	key: string; // 'cvar' | 'markowitz' | 'markowitz_lw' | 'robust' | 'equal'
	name: string;
	blurb: string;
	solver: string | null;
}

export interface Weights {
	dates: string[]; // weekly (Fridays)
	assets: string[]; // only assets ever held
	rows: number[][];
}

/** One backtest: one profile under one model. File: runs/<profile>__<model>.json */
export interface RunResult {
	profile: ProfileMeta;
	model: ModelMeta;
	dates: string[];
	value: number[]; // starts at 100,000 minus the first day's trading cost
	benchmark: number[]; // SPY from 100,000 over the same dates
	weights: Weights;
	solves: Solve[];
	trades: Trade[];
	metrics: Metrics;
	benchmark_metrics: Metrics;
}

export type SummaryMetrics = Pick<
	Metrics,
	'cagr' | 'volatility' | 'sharpe' | 'sortino' | 'max_drawdown' | 'cvar_95_daily' | 'end_value'
>;

export interface RunSummary {
	profile: string;
	model: string;
	file: string;
	solves: number;
	total_cost: number;
	avg_cvar_limit: number;
	metrics: SummaryMetrics;
	benchmark_metrics: SummaryMetrics;
}

/** index.json: the table of contents for everything the pipeline exported. */
export interface RunIndex {
	start: string;
	end: string;
	benchmark: string;
	story_model: string; // the model the narrative runs on
	profiles: ProfileMeta[];
	models: ModelMeta[];
	runs: RunSummary[];
}

export interface ArchiveAsset {
	return_2015: number;
	drawdown_2015: number;
	return_3y: number;
	drawdown_3y: number;
	spark: number[]; // month-end price / first month-end, 2013-2015
}

export interface ArchiveSector {
	tickers: string[];
	return_2015: number; // average of members
	worst_2015: { ticker: string; return: number };
	best_2015: { ticker: string; return: number };
	drawdown_2015: number; // of the equal-weight basket
	return_3y: number;
}

/** archive.json: what an investor could see on 31 December 2015. Nothing later. */
export interface Archive {
	as_of: string;
	spark_dates: string[];
	tbill_rate_annual: number;
	assets: Record<string, ArchiveAsset>;
	sectors: Record<string, ArchiveSector>;
}

export interface Note2015 {
	headline: string;
	body: string;
	sources: string[];
}

/** notes2015.json: hand-written, source-checked context as of 31 December 2015. */
export interface Notes2015 {
	as_of: string;
	year: Note2015;
	sectors: Record<string, Note2015>;
	assets: Record<string, string>;
}

export interface MarketEvent {
	date: string;
	title: string;
	blurb: string;
	side: 'above' | 'below';
	kind?: 'market' | 'world';
	image?: string; // file under static/img/events/
	credit?: string; // attribution for the image
}

const cache = new Map<string, Promise<unknown>>();

async function getJson<T>(path: string): Promise<T> {
	if (!cache.has(path)) {
		cache.set(
			path,
			fetch(`${base}/data/${path}`).then((r) => {
				if (!r.ok) throw new Error(`failed to load ${path}: ${r.status}`);
				return r.json();
			})
		);
	}
	return cache.get(path) as Promise<T>;
}

export const loadUniverse = () => getJson<Universe>('universe.json');
export const loadPrices = () => getJson<Prices>('prices.json');
export const loadEvents = () => getJson<MarketEvent[]>('events.json');
export const loadIndex = () => getJson<RunIndex>('index.json');
export const loadArchive = () => getJson<Archive>('archive.json');
export const loadNotes = () => getJson<Notes2015>('notes2015.json');
export const runKey = (profile: string, model: string) => `${profile}__${model}`;
export const loadRun = (profile: string, model: string) =>
	getJson<RunResult>(`runs/${runKey(profile, model)}.json`);
