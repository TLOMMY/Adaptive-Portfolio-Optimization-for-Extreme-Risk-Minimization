<script lang="ts">
	// The timeline. Vertical scroll drives horizontal travel: the camera slides
	// along the thread as you scroll, upstream from today to 1 Jan 2016.
	// Rendering lives in timeline3d.ts (Three.js); this component owns scroll,
	// data and the DOM portals, which are pinned to projected 3D anchors.
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { go } from '$lib/state.svelte';
	import type { MarketEvent, Prices } from '$lib/data';
	import type { Anchor } from './timeline3d';

	let { events, prices = null }: { events: MarketEvent[]; prices?: Prices | null } = $props();

	const T0 = Date.UTC(2016, 0, 1);
	const T1 = Date.UTC(2026, 0, 1);
	const UNITS_PER_YEAR = 400; // world units; ~1 screen-width per year
	const trackW = (UNITS_PER_YEAR * (T1 - T0)) / (365.25 * 864e5);
	const xOf = (ms: number) => ((ms - T0) / (T1 - T0)) * trackW;
	const xOfIso = (iso: string) => xOf(Date.parse(iso));
	const years = Array.from({ length: 11 }, (_, i) => 2016 + i);
	const yearXs = years.map((y) => xOf(Date.UTC(y, 0, 1)));

	let scrollY = $state(0);
	let vh = $state(800);
	let vw = $state(1200);
	let veil = $state(1);
	let hovered = $state<string | null>(null);
	let leaving = $state(0);
	let intro = $state(0);
	let anchors = $state<Record<string, Anchor>>({});
	let yearAnchors = $state<Anchor[]>([]);
	let canvas: HTMLCanvasElement;

	// --- volatility along the track (0..1) --------------------------------------------
	const rough = $derived.by(() => {
		const n = Math.ceil(trackW / 8) + 1;
		const out = new Float32Array(n).fill(0.25);
		if (!prices) return out;
		const col = prices.assets.indexOf('SPY');
		const r: number[] = [];
		for (let i = 1; i < prices.rows.length; i++) r.push(prices.rows[i][col] / prices.rows[i - 1][col] - 1);
		const vol: number[] = [];
		for (let i = 0; i < r.length; i++) {
			const w = r.slice(Math.max(0, i - 20), i + 1);
			const m = w.reduce((s, v) => s + v, 0) / w.length;
			vol.push(Math.sqrt(w.reduce((s, v) => s + (v - m) ** 2, 0) / w.length));
		}
		const lo = 0.004,
			hi = 0.03;
		let j = 0;
		for (let k = 0; k < n; k++) {
			const ms = T0 + ((k * 8) / trackW) * (T1 - T0);
			while (j < vol.length - 1 && Date.parse(prices.dates[j + 1]) <= ms) j++;
			out[k] = Math.max(0, Math.min(1, (vol[j] - lo) / (hi - lo)));
		}
		const s = new Float32Array(n);
		for (let k = 0; k < n; k++) {
			let acc = 0,
				c = 0;
			for (let d = -6; d <= 6; d++) {
				const kk = k + d;
				if (kk >= 0 && kk < n) {
					acc += out[kk];
					c++;
				}
			}
			s[k] = acc / c;
		}
		return s;
	});
	const roughAt = (x: number) => rough[Math.max(0, Math.min(rough.length - 1, Math.round(x / 8)))];

	const scrollLen = $derived(vh * 10);
	const progress = $derived(Math.max(0, Math.min(1, scrollY / scrollLen)));
	const centreX = $derived(trackW * (1 - progress));
	const nowMs = $derived(T0 + (centreX / trackW) * (T1 - T0));
	const label = $derived(new Date(nowMs).toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' }));
	const arrived = $derived(progress > 0.985);

	const PORTAL = $derived(Math.round(Math.max(96, Math.min(150, vh * 0.16))));

	interface Placed extends MarketEvent {
		x: number;
		side: 'above' | 'below';
		far: boolean;
	}
	// four lanes (near/far on each side); an event takes the first lane with room
	const placed = $derived.by((): Placed[] => {
		const sorted = [...events].sort((a, b) => a.date.localeCompare(b.date));
		const lastX: Record<string, number> = {};
		const minGap = 210; // world units within one lane
		return sorted.map((e) => {
			const x = xOfIso(e.date);
			const other = e.side === 'above' ? 'below' : 'above';
			const lanes: [typeof e.side, boolean][] = [
				[e.side, false],
				[other, false],
				[e.side, true],
				[other, true]
			];
			let pick = lanes[0];
			for (const l of lanes) {
				if (x - (lastX[l.join()] ?? -Infinity) >= minGap) {
					pick = l;
					break;
				}
			}
			lastX[pick.join()] = x;
			return { ...e, x, side: pick[0], far: pick[1] };
		});
	});

	function spark(date: string): { d: string; up: boolean } | null {
		if (!prices) return null;
		const i = prices.dates.findIndex((d) => d >= date);
		if (i < 0) return null;
		const col = prices.assets.indexOf('SPY');
		const lo = Math.max(0, i - 45),
			hi = Math.min(prices.rows.length - 1, i + 45);
		const vals = prices.rows.slice(lo, hi + 1).map((r) => r[col]);
		const min = Math.min(...vals),
			max = Math.max(...vals);
		const pts = vals.map((v, k) => `${(k / (vals.length - 1)) * 100},${100 - ((v - min) / (max - min || 1)) * 70 - 15}`);
		return { d: 'M' + pts.join('L'), up: vals[vals.length - 1] >= vals[0] };
	}

	// hovering freezes a portal in place (until the user scrolls again)
	let frozen: { id: string; a: Anchor; y: number } | null = null;
	function anchorOf(e: Placed): Anchor | undefined {
		const a = anchors[e.date];
		if (!a) return undefined;
		if (hovered === e.date && intro >= 1) {
			if (!frozen || frozen.id !== e.date || frozen.y !== scrollY) frozen = { id: e.date, a, y: scrollY };
			return frozen.a;
		}
		if (frozen?.id === e.date) frozen = null;
		return a;
	}

	function arrive() {
		if (leaving > 0) return;
		const t0 = performance.now();
		const DUR = 4600;
		const step = (t: number) => {
			leaving = Math.min(1, (t - t0) / DUR);
			if (leaving < 1) requestAnimationFrame(step);
			else go('archive');
		};
		requestAnimationFrame(step);
	}
	const wash = $derived(leaving > 0.82 ? ((leaving - 0.82) / 0.18) ** 1.5 : 0);

	onMount(() => {
		window.scrollTo({ top: 0 });
		const onScroll = () => (scrollY = window.scrollY);
		const onResize = () => {
			vh = window.innerHeight;
			vw = window.innerWidth;
		};
		onResize();
		window.addEventListener('scroll', onScroll, { passive: true });
		window.addEventListener('resize', onResize);
		setTimeout(() => (veil = 0), 100);
		const INTRO = 5200;
		const born = performance.now();

		let raf = 0;
		let tl: ReturnType<typeof import('./timeline3d').createTimeline> | undefined;
		let dead = false;
		import('./timeline3d').then(({ createTimeline }) => {
			if (dead) return;
			const vol = rough; // plain array snapshot: the build reads it ~100k times
			const t3 = createTimeline(canvas, {
				trackW,
				rough: (x) => vol[Math.max(0, Math.min(vol.length - 1, Math.round(x / 8)))],
				events: placed.map((e) => ({ id: e.date, x: e.x, side: e.side, far: e.far })),
				yearXs
			});
			tl = t3;
			const resize = () => t3.resize(window.innerWidth, window.innerHeight);
			resize();
			window.addEventListener('resize', resize);
			// dev: window.__tlo = { intro, leaving, progress } pins a state for screenshots
			const frame = (t: number) => {
				const o = import.meta.env.DEV ? (window as unknown as { __tlo?: { intro?: number; leaving?: number; progress?: number } }).__tlo : undefined;
				intro = o?.intro ?? Math.min(1, (t - born) / INTRO);
				if (o?.leaving !== undefined) leaving = o.leaving;
				if (o?.progress !== undefined) scrollY = o.progress * scrollLen;
				const out = t3.frame({ t, centreX, leaving, intro });
				anchors = Object.fromEntries(out.anchors);
				yearAnchors = out.years;
				raf = requestAnimationFrame(frame);
			};
			raf = requestAnimationFrame(frame);
		});
		return () => {
			dead = true;
			cancelAnimationFrame(raf);
			tl?.dispose();
			window.removeEventListener('scroll', onScroll);
			window.removeEventListener('resize', onResize);
		};
	});
</script>

<div class="track" style:height={`${scrollLen + vh}px`}>
	<div class="viewport">
		<canvas bind:this={canvas} class="river" style:width={`${vw}px`} style:height={`${vh}px`}></canvas>

		<header class="now" style:opacity={Math.min(1 - Math.min(1, leaving * 3), Math.max(0, (intro - 0.8) * 5))}>
			<p class="mono small">travelling back</p>
			<h1 class="mono">{label}</h1>
		</header>

		<div class="overlay" style:opacity={Math.min(1 - Math.min(1, leaving * 2.5), Math.max(0, (intro - 0.75) * 4))}>
			{#each years as y, i (y)}
				{@const a = yearAnchors[i]}
				{#if a?.visible}
					<div class="year mono" style:left={`${a.x}px`} style:top={`${a.y}px`} style:opacity={0.85 * Math.min(1, a.s)} style:font-size={`${Math.max(0.6, 0.72 * a.s)}rem`}>
						{y}
					</div>
				{/if}
			{/each}
			{#each placed as e (e.date)}
				{@const a = anchorOf(e)}
				{#if a?.visible}
					{@const dist = Math.abs(e.x - centreX) / UNITS_PER_YEAR}
					{@const near = dist < 0.25 || hovered === e.date}
					{@const sp = e.image ? null : spark(e.date)}
					{@const R = (PORTAL / 2) * (hovered === e.date ? Math.max(a.s, 0.95) * 1.04 : a.s)}
					<div
						class="event {e.side}"
						class:hovered={hovered === e.date}
						class:far={e.far}
						style:left={`${a.x}px`}
						style:top={`${a.y}px`}
						style:opacity={Math.max(0.25, 1 - dist * 0.7)}
						style:z-index={hovered === e.date ? 50 : Math.round(a.s * 10)}
						onmouseenter={() => (hovered = e.date)}
						onmouseleave={() => (hovered = null)}
						role="presentation"
					>
						<div class="portal" class:near style:transform={`scale(${hovered === e.date ? Math.max(a.s, 0.95) * 1.04 : a.s})`}>
							<div class="lens" style:width={`${PORTAL}px`} style:height={`${PORTAL}px`}>
								{#if e.image}
									<img src={`${base}/img/events/${e.image}`} alt={e.title} loading="lazy" />
								{:else if sp}
									<svg viewBox="0 0 100 100" preserveAspectRatio="none" class="spark" class:down={!sp.up}>
										<path d={sp.d} />
									</svg>
									<span class="mono sparklabel">S&amp;P 500 · 90 days</span>
								{/if}
								<span class="ring"></span>
							</div>
						</div>
						<!-- caption sits outside the scaled lens so text stays readable -->
						<div
							class="caption"
							style:top={e.far ? '0' : e.side === 'below' ? `${R - 2}px` : 'auto'}
							style:bottom={!e.far && e.side === 'above' ? `${R - 2}px` : 'auto'}
							style:left={e.far ? `${R + 8}px` : '0'}
						>
							<p class="mono when">{new Date(e.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</p>
							<h3>{e.title}</h3>
							<p class="blurb" style:opacity={near ? 1 : 0} style:max-height={near ? '6rem' : '0'}>{e.blurb}</p>
							{#if e.credit}<p class="credit" style:opacity={hovered === e.date ? 0.6 : 0}>{e.credit}</p>{/if}
						</div>
					</div>
				{/if}
			{/each}
		</div>

		<footer style:opacity={arrived && leaving === 0 ? 1 : 0} style:pointer-events={arrived && leaving === 0 ? 'auto' : 'none'}>
			<p class="mono small">1 January 2016</p>
			<button class="arrive" onclick={arrive}>Arrive</button>
		</footer>
		<p class="hint mono" style:opacity={progress < 0.02 && intro >= 1 ? 0.7 : 0}>scroll to travel</p>
		<div class="veil" style:opacity={veil}></div>
		<div class="wash" style:opacity={wash}></div>
	</div>
</div>

<style>
	.track {
		position: relative;
		background: #05081a;
		color: #ecebfa;
	}
	.viewport {
		position: sticky;
		top: 0;
		height: 100vh;
		overflow: hidden;
	}
	.river {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}
	.veil {
		position: absolute;
		inset: 0;
		background: #05030a;
		z-index: 6;
		pointer-events: none;
		transition: opacity 1.4s ease-out;
	}
	.wash {
		position: absolute;
		inset: 0;
		background: var(--paper);
		z-index: 7;
		pointer-events: none;
	}
	.now {
		position: absolute;
		top: 1.4rem;
		left: 1.8rem;
		z-index: 2;
		transition: opacity 0.4s;
	}
	.overlay {
		transition: opacity 0.3s;
	}
	.now h1 {
		font-size: clamp(1.1rem, 2vw, 1.5rem);
		font-weight: 400;
		margin: 0;
		color: #dcefff;
	}
	.small {
		font-size: 0.6rem;
		letter-spacing: 0.3em;
		text-transform: uppercase;
		opacity: 0.6;
		margin: 0 0 0.2rem;
	}
	.overlay {
		position: absolute;
		inset: 0;
	}
	.year {
		position: absolute;
		transform: translate(-50%, 0);
		letter-spacing: 0.2em;
		color: #cfe6ff;
		text-shadow: 0 0 8px rgba(120, 190, 255, 0.6);
		pointer-events: none;
	}
	.event {
		position: absolute;
		width: 0;
		height: 0;
	}
	.portal {
		position: absolute;
		left: 0;
		top: 0;
		width: 0;
		height: 0;
		transform-origin: 0 0;
		transition: transform 0.25s ease-out;
	}
	.lens {
		position: absolute;
		left: 0;
		top: 0;
		transform: translate(-50%, -50%);
		border-radius: 50%;
		overflow: hidden;
		background: #0b1a2a;
		box-shadow:
			inset 0 0 0 1px rgba(200, 230, 255, 0.6),
			0 0 50px -6px rgba(120, 190, 255, 0.55);
		transition: box-shadow 0.3s;
	}
	.event.hovered .lens {
		box-shadow:
			inset 0 0 0 1px rgba(235, 248, 255, 0.95),
			0 0 90px -4px rgba(140, 200, 255, 0.85);
	}
	.lens img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		filter: saturate(0.5) contrast(1.05) brightness(0.85);
		transition: filter 0.4s;
	}
	.portal.near .lens img {
		filter: none;
	}
	.ring {
		position: absolute;
		inset: 6px;
		border-radius: 50%;
		border: 1px solid rgba(4, 8, 16, 0.6);
		pointer-events: none;
	}
	.spark {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}
	.spark path {
		fill: none;
		stroke: #bfe3ff;
		stroke-width: 1.6;
		vector-effect: non-scaling-stroke;
	}
	.spark.down path {
		stroke: #ff9fd6;
	}
	.sparklabel {
		position: absolute;
		bottom: 18%;
		left: 0;
		right: 0;
		text-align: center;
		font-size: 0.55rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
		opacity: 0.55;
	}
	.caption {
		position: absolute;
		width: 15rem;
		transform: translateX(-50%);
		text-align: center;
		padding: 0.6rem 0.4rem;
	}
	.event.far .caption {
		width: 11rem;
		transform: translateY(-50%);
		text-align: left;
		padding: 0.2rem 0.4rem;
	}
	.event.far h3 {
		font-size: 0.95rem;
	}
	.event.far .blurb {
		font-size: 0.75rem;
	}
	.when {
		font-size: 0.65rem;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		opacity: 0.7;
		margin: 0 0 0.2rem;
	}
	h3 {
		font-size: 1.1rem;
		margin: 0 0 0.3rem;
		font-weight: 500;
		text-shadow: 0 0 12px rgba(120, 190, 255, 0.5);
	}
	.blurb {
		font-size: 0.82rem;
		line-height: 1.45;
		margin: 0;
		overflow: hidden;
		opacity: 0.9;
		transition:
			opacity 0.4s,
			max-height 0.4s;
	}
	.credit {
		font-size: 0.55rem;
		margin: 0.3rem 0 0;
		transition: opacity 0.4s;
	}
	footer {
		position: absolute;
		bottom: 2.2rem;
		right: 2rem;
		text-align: right;
		transition: opacity 0.8s;
		z-index: 3;
	}
	.arrive {
		padding: 0.8rem 2.2rem;
		border: 1px solid #dcefff;
		background: #dcefff;
		color: #06101a;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		font-size: 0.75rem;
		border-radius: 999px;
	}
	.arrive:hover {
		background: transparent;
		color: #dcefff;
	}
	.hint {
		position: absolute;
		bottom: 1.2rem;
		left: 50%;
		transform: translateX(-50%);
		font-size: 0.65rem;
		letter-spacing: 0.3em;
		text-transform: uppercase;
		transition: opacity 0.6s;
	}
</style>
