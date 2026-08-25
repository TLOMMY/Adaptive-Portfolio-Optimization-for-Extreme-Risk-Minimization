// Loaders and types for the JSON produced by the Python pipeline (src/portfolio/export.py).
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
	cvar_limit: number;
	exp_return_ann: number;
	cvar: number;
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
	horizon_years: number;
	cvar_start: number;
	cvar_end: number;
	max_holdings: number;
	w_max: number;
	cash_min: number;
	sector_cap: Record<string, number>;
	exclude: string[];
}

export interface ProfileResult {
	profile: ProfileMeta;
	dates: string[];
	value: number[]; // starts at 100,000
	benchmark: number[];
	weights: { dates: string[]; assets: string[]; rows: number[][] };
	solves: Solve[];
	trades: Trade[];
	metrics: Metrics;
	benchmark_metrics: Metrics;
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
export const loadProfile = (key: string) => getJson<ProfileResult>(`profiles/${key}.json`);
export const loadSummary = () => getJson<ProfileMeta[]>('summary.json');

export const PROFILE_KEYS = ['preserver', 'steady', 'builder', 'maverick', 'sprinter', 'ethical'];
export const loadProfileIndex = () => getJson<ProfileMeta[]>('profiles/index.json');
