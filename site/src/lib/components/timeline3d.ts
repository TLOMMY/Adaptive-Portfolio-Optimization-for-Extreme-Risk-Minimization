// Three.js renderer for the timeline. The trunk is a dense bundle of additive
// fibres (hot white core, lavender / blue / pink outer strands) whose spread
// follows market volatility. Lightning-like frayed branches leave it all along
// its length; each event owns one and the portal hangs at its tip. A bloom pass
// gives the light-through-haze look, linear fog gives depth. On arrival a big
// branch grows out of the trunk and the camera flies along it.
//
// Loaded lazily by Rewind.svelte (browser only).

import * as THREE from 'three';
import { LineSegments2 } from 'three/examples/jsm/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/examples/jsm/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { AfterimagePass } from 'three/examples/jsm/postprocessing/AfterimagePass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';

export interface EventSpec {
	id: string;
	x: number; // world x (time)
	side: 'above' | 'below';
	far?: boolean; // second lane: longer branch, portal further from the trunk
}
export interface TimelineOpts {
	trackW: number;
	rough: (x: number) => number; // 0..1 volatility at world x
	events: EventSpec[];
	yearXs: number[];
}
/** Measured facts about the DOM portals, supplied every frame; the branch layout is derived from them. */
export interface UiMetrics {
	vh: number; // viewport height, px
	portalPx: number; // lens diameter at scale 1, px
	captions: Record<string, number>; // measured caption height per event id, px
	marginPx: number; // keep-out band at the top and bottom edges
	footPx?: number; // extra keep-out at the bottom (the Arrive footer on small screens)
	gapPx: number; // between the thread and the nearest portal edge
	nearLane: number; // preferred distance from the thread to a near-lane tip, px
	farLane: number; // and to a far-lane tip
}
export interface Anchor {
	x: number; // screen px
	y: number;
	s: number; // scale relative to the trunk at the traveller
	visible: boolean;
}
export interface Frame {
	t: number; // ms
	centreX: number; // world x under the traveller
	leaving: number; // 0..1 arrival sequence
	intro: number; // 0..1 opening flight: along the line, then swing out to the side
	ui: UiMetrics;
}

type V3 = THREE.Vector3;
const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);

// deterministic random (mulberry32)
function rng(seed: number) {
	let a = seed >>> 0;
	return () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let t = a;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}
const smooth = (a: number, b: number, x: number) => {
	const u = Math.max(0, Math.min(1, (x - a) / (b - a)));
	return u * u * (3 - 2 * u);
};
const easeInOut = (u: number) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);

// --- trunk geometry -------------------------------------------------------------
export function centre(x: number): V3 {
	return V(x, 22 * Math.sin(x / 620 + 0.4) + 8 * Math.sin(x / 190 + 2), 18 * Math.sin(x / 480 + 1.3) + 7 * Math.sin(x / 150));
}
// the same wobble runs on the GPU (see WOBBLE_GLSL); t in seconds
export function wobble(p: V3, t: number): V3 {
	p.y += 4 * Math.sin(p.x * 0.011 + t * 0.9) + 2.2 * Math.sin(p.x * 0.031 - t * 1.7);
	p.z += 3 * Math.sin(p.x * 0.014 + t * 0.7 + 1);
	return p;
}
const WOBBLE_GLSL = /* glsl */ `
uniform float uTime;
vec3 wob(vec3 p) {
	p.y += 4.0 * sin(p.x * 0.011 + uTime * 0.9) + 2.2 * sin(p.x * 0.031 - uTime * 1.7);
	p.z += 3.0 * sin(p.x * 0.014 + uTime * 0.7 + 1.0);
	return p;
}`;

type RGB = [number, number, number];
const TINT = {
	white: [0.95, 0.93, 1.0] as RGB,
	lavender: [0.78, 0.7, 1.0] as RGB,
	blue: [0.45, 0.68, 1.0] as RGB,
	pink: [1.0, 0.5, 0.74] as RGB
};

// a bag of line segments with per-vertex colour
interface Sink {
	polyline(pts: V3[], cols: RGB[]): void;
}
class Bag implements Sink {
	pos: number[] = [];
	col: number[] = [];
	segment(a: V3, b: V3, ca: RGB, cb: RGB) {
		this.pos.push(a.x, a.y, a.z, b.x, b.y, b.z);
		this.col.push(ca[0], ca[1], ca[2], cb[0], cb[1], cb[2]);
	}
	polyline(pts: V3[], cols: RGB[]) {
		for (let i = 0; i < pts.length - 1; i++) {
			this.segment(pts[i], pts[i + 1], cols[Math.min(i, cols.length - 1)], cols[Math.min(i + 1, cols.length - 1)]);
		}
	}
	segments(): number {
		return this.pos.length / 6;
	}
	geometry(): LineSegmentsGeometry {
		const g = new LineSegmentsGeometry();
		g.setPositions(new Float32Array(this.pos));
		g.setColors(new Float32Array(this.col));
		return g;
	}
}
// The same, but each segment lands in a bag for its slice of x. Every slice becomes its own object
// with a bounding sphere, so the renderer skips the slices outside the view: only the part of the
// ten-year thread that is actually on screen is drawn. Nothing about what is drawn changes.
class ChunkedBag implements Sink {
	bags: Bag[];
	constructor(
		private x0: number,
		private size: number,
		n: number
	) {
		this.bags = Array.from({ length: n }, () => new Bag());
	}
	polyline(pts: V3[], cols: RGB[]) {
		for (let i = 0; i < pts.length - 1; i++) {
			const a = pts[i],
				b = pts[i + 1];
			const k = Math.max(0, Math.min(this.bags.length - 1, Math.floor(((a.x + b.x) / 2 - this.x0) / this.size)));
			this.bags[k].segment(a, b, cols[Math.min(i, cols.length - 1)], cols[Math.min(i + 1, cols.length - 1)]);
		}
	}
	// one culled object per non-empty slice
	objects(mat: LineMaterial): LineSegments2[] {
		return this.bags
			.filter((b) => b.segments() > 0)
			.map((b) => {
				const g = b.geometry();
				g.computeBoundingSphere();
				// the GPU wobble moves vertices by up to ~9 units, and a fat line is a few pixels wide
				g.boundingSphere!.radius += 16;
				const o = new LineSegments2(g, mat);
				o.frustumCulled = true;
				return o;
			});
	}
}

const scaled = (c: RGB, k: number): RGB => [c[0] * k, c[1] * k, c[2] * k];

function perpendiculars(dir: V3): [V3, V3] {
	const helper = Math.abs(dir.y) < 0.9 ? V(0, 1, 0) : V(1, 0, 0);
	const p1 = V().crossVectors(dir, helper).normalize();
	const p2 = V().crossVectors(dir, p1).normalize();
	return [p1, p2];
}

// a frayed, lightning-like branch. Returns the tip. With `target` the tip lands exactly there
// (the bend is applied sideways, perpendicular to the chord, so it cannot move the tip).
function growBranch(bag: Sink, origin: V3, dir: V3, away: V3, len: number, level: number, bright: number, r: () => number, target?: V3): V3 {
	const n = level === 0 ? 26 : level === 1 ? 14 : 8;
	if (target) {
		dir = V().subVectors(target, origin).normalize();
		len = target.distanceTo(origin);
	}
	const [p1, p2] = perpendiculars(dir);
	const bend = target
		? V()
				.addScaledVector(p1, (r() - 0.5) * 0.6)
				.addScaledVector(p2, (r() - 0.5) * 0.6)
				.normalize()
				.multiplyScalar(0.22)
		: V()
				.copy(away)
				.multiplyScalar(0.55)
				.addScaledVector(p1, (r() - 0.5) * 0.6)
				.addScaledVector(p2, (r() - 0.5) * 0.6)
				.normalize()
				.multiplyScalar(0.38);
	const ph = r() * 6.28,
		ph2 = r() * 6.28;
	// the sideways bend rises and falls (u(1-u)) when a target is set, so it is zero at both ends
	const bendAt = (u: number) => (target ? 4 * u * (1 - u) : u * u);
	const base = (u: number) =>
		V()
			.copy(origin)
			.addScaledVector(dir, u * len)
			.addScaledVector(bend, bendAt(u) * len)
			.addScaledVector(p1, len * 0.03 * Math.sin(u * 7 + ph) * (target ? Math.sin(u * Math.PI) : 1))
			.addScaledVector(p2, len * 0.03 * Math.sin(u * 5 + ph2) * (target ? Math.sin(u * Math.PI) : 1));
	const nf = level === 0 ? 5 : level === 1 ? 3 : 1;
	for (let f = 0; f < nf; f++) {
		const pf = r() * 6.28,
			pf2 = r() * 6.28;
		const w = (1.2 + 2.6 * (level === 0 ? 1 : 0.6)) * (f === 0 ? 0.3 : 1);
		const tint = r() < 0.22 ? TINT.pink : r() < 0.6 ? TINT.blue : TINT.white;
		const pts: V3[] = [],
			cols: RGB[] = [];
		for (let k = 0; k <= n; k++) {
			const u = k / n;
			const p = base(u)
				.addScaledVector(p1, Math.sin(u * 9 + pf) * w * (0.4 + u))
				.addScaledVector(p2, Math.cos(u * 7 + pf2) * w * (0.4 + u));
			pts.push(p);
			cols.push(scaled(tint, bright * (1 - 0.72 * u) * (f === 0 ? 1 : 0.5)));
		}
		bag.polyline(pts, cols);
	}
	if (level < 2) {
		for (const u0 of [0.32, 0.56, 0.78]) {
			if (r() < (level === 0 ? 0.85 : 0.5)) {
				const nd = V()
					.copy(dir)
					.multiplyScalar(0.7)
					.addScaledVector(p1, (r() - 0.5) * 1.2)
					.addScaledVector(p2, (r() - 0.5) * 1.2)
					.addScaledVector(away, 0.25)
					.normalize();
				growBranch(bag, base(u0), nd, away, len * (0.3 + 0.25 * r()), level + 1, bright * 0.7, r);
			}
		}
	}
	// crackle at the tip
	const tip = base(1);
	for (let c = 0; c < 3; c++) {
		const pts = [tip.clone()],
			cols: RGB[] = [scaled(TINT.blue, bright * 0.35)];
		let p = tip.clone();
		const d = V()
			.copy(dir)
			.addScaledVector(p1, (r() - 0.5) * 1.4)
			.addScaledVector(p2, (r() - 0.5) * 1.4)
			.normalize();
		for (let k = 1; k <= 4; k++) {
			p = p
				.clone()
				.addScaledVector(d, len * 0.04)
				.addScaledVector(p1, (r() - 0.5) * len * 0.05)
				.addScaledVector(p2, (r() - 0.5) * len * 0.05);
			pts.push(p);
			cols.push(scaled(TINT.blue, bright * 0.35 * (1 - k / 4)));
		}
		bag.polyline(pts, cols);
	}
	return tip;
}

// --- the arrival branch: a bezier leaving the trunk toward the camera ----------------
// Control points are relative to the trunk's centre line at x = 0 (1 January 2016), so the
// root sits inside the bundle rather than at the world origin ~23 units away from it.
const ARRIVE = {
	p0: V(0, 0, 0),
	p1: V(-150, 28, 70),
	p2: V(-270, 95, 400),
	p3: V(-320, 130, 950)
};
const C0 = centre(0);
function bez(u: number, out = V()): V3 {
	const { p0, p1, p2, p3 } = ARRIVE;
	const v = 1 - u;
	out.set(0, 0, 0);
	out.addScaledVector(p0, v * v * v);
	out.addScaledVector(p1, 3 * v * v * u);
	out.addScaledVector(p2, 3 * v * u * u);
	out.addScaledVector(p3, u * u * u);
	out.add(C0);
	return out;
}

const BG_FRAG = /* glsl */ `
uniform float uTime;
varying vec2 vUv;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
	vec2 i = floor(p), f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p) {
	float v = 0.0, a = 0.5;
	for (int i = 0; i < 5; i++) { v += a * noise(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; }
	return v;
}
void main() {
	vec2 uv = vUv;
	// colours in sRGB, converted to linear at the end
	vec3 deep = vec3(0.016, 0.03, 0.09);
	vec3 mid = vec3(0.06, 0.12, 0.28);
	float band = exp(-pow((uv.y - 0.5) * 2.4, 2.0));
	vec3 c = mix(deep, mid, band);
	float n = fbm(vec2(uv.x * 3.0 + uTime * 0.006, uv.y * 5.0 + uTime * 0.003));
	float streak = fbm(vec2(uv.x * 1.6 - uTime * 0.008, uv.y * 13.0));
	c += (n - 0.5) * 0.10 * vec3(0.45, 0.65, 1.0);
	c -= (streak - 0.5) * 0.07;
	float v = smoothstep(1.25, 0.3, length((uv - 0.5) * vec2(1.5, 1.25)));
	c *= 0.5 + 0.5 * v;
	c = max(c, 0.0);
	gl_FragColor = vec4(pow(c, vec3(2.2)), 1.0);
}`;

// camera pose while travelling: behind-left of the traveller, looking at it
const CAM = V(-240, 50, 690);
const FOV = 40;

export function createTimeline(canvas: HTMLCanvasElement, opts: TimelineOpts) {
	const { trackW, rough, events, yearXs } = opts;
	const r = rng(7);

	const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
	renderer.toneMapping = THREE.ACESFilmicToneMapping;
	renderer.toneMappingExposure = 1.05;
	const scene = new THREE.Scene();
	const fogColor = new THREE.Color('#0a1633');
	scene.fog = new THREE.Fog(fogColor, 700, 1900);
	const camera = new THREE.PerspectiveCamera(FOV, 1, 1, 6000);
	scene.add(camera);

	// backdrop, attached to the camera
	const bgMat = new THREE.ShaderMaterial({
		uniforms: { uTime: { value: 0 } },
		vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
		fragmentShader: BG_FRAG,
		depthWrite: false,
		depthTest: false
	});
	const bg = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), bgMat);
	bg.position.z = -2600;
	bg.renderOrder = -1;
	camera.add(bg);

	// materials
	const uTime = { value: 0 };
	const uGain = { value: 0.035 };
	const uGainA = { value: 0.035 };
	const lineMat = (width: number, gain = uGain, worldUnits = false) => {
		const m = new LineMaterial({
			vertexColors: true,
			linewidth: width,
			worldUnits,
			blending: THREE.AdditiveBlending,
			transparent: true,
			depthWrite: false,
			depthTest: false
		});
		m.fog = true;
		m.onBeforeCompile = (sh) => {
			sh.uniforms.uTime = uTime;
			sh.uniforms.uGain = gain;
			sh.fragmentShader = sh.fragmentShader
				.replace('uniform float linewidth;', 'uniform float linewidth;\nuniform float uGain;')
				.replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.rgb *= uGain;');
			sh.vertexShader = sh.vertexShader
				.replace(/\/\/ endcaps\s*if \( position\.y < 0\.0 \) \{\s*offset \+= - dir;\s*\} else if \( position\.y > 1\.0 \) \{\s*offset \+= dir;\s*\}/, '')
				.replace('uniform float linewidth;', 'uniform float linewidth;\n' + WOBBLE_GLSL)
				.replace('vec4 start = modelViewMatrix * vec4( instanceStart, 1.0 );', 'vec4 start = modelViewMatrix * vec4( wob(instanceStart), 1.0 );')
				.replace('vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );', 'vec4 end = modelViewMatrix * vec4( wob(instanceEnd), 1.0 );');
		};
		return m;
	};
	const coreMat = lineMat(2.4);
	const fineMat = lineMat(1.1);
	const twigMat = lineMat(0.9);
	const arriveMat = lineMat(2.2, uGainA);
	const mats = [coreMat, fineMat, twigMat, arriveMat];

	// --- trunk ---
	const X0 = -420,
		X1 = trackW + 4200, // the thread runs on into the future: the opening flight races in along it
		DX = 6;
	const CHUNK = 300; // world units per culled slice (about nine months)
	const nChunks = Math.ceil((X1 - X0) / CHUNK) + 1;
	const core = new ChunkedBag(X0, CHUNK, nChunks),
		fine = new ChunkedBag(X0, CHUNK, nChunks);
	const endFade = (x: number) => smooth(X0, X0 + 260, x) * smooth(X1, X1 - 260, x);
	const NS = 96;
	for (let i = 0; i < NS; i++) {
		const isCore = i < 8;
		const rr = isCore ? r() * 0.25 : 0.15 + Math.pow(r(), 1.5) * 0.85;
		const th = r() * 6.28,
			k1 = 260 + r() * 500,
			k2 = 110 + r() * 220,
			ph = r() * 6.28,
			ph2 = r() * 6.28,
			ph3 = r() * 6.28;
		const tr = r();
		const tint = isCore ? TINT.white : tr < 0.45 ? TINT.white : tr < 0.7 ? TINT.lavender : tr < 0.87 ? TINT.blue : TINT.pink;
		const b = isCore ? 0.9 + 0.3 * r() : 0.55 + 0.45 * (1 - rr);
		const pts: V3[] = [],
			cols: RGB[] = [];
		for (let x = X0; x <= X1; x += DX) {
			const sp = 5 + 18 * rough(Math.max(0, Math.min(trackW, x)));
			const a = th + 0.9 * Math.sin(x / k1 + ph);
			const rad = rr * (1 + 0.35 * Math.sin(x / k2 + ph2)) * sp;
			const p = centre(x);
			p.y += rad * Math.cos(a);
			p.z += rad * Math.sin(a);
			pts.push(p);
			cols.push(scaled(tint, b * endFade(x) * (1 + 0.2 * Math.sin(x / 90 + ph3))));
		}
		(isCore ? core : fine).polyline(pts, cols);
	}

	// --- branches ---
	// Each event's branch is a unit-length geometry (origin to (0, 100, 0)) in its own object. Every
	// frame the portal's screen position is chosen from measured DOM sizes, unprojected to the
	// thread's depth, and the object is rotated and scaled to land its tip there. So the layout is
	// done in screen space and the 3D branch follows it, whatever the viewport or perspective.
	const UNIT = 100;
	const branches = events.map((e, i) => {
		const rr = rng(11 + i);
		const bag = new Bag();
		growBranch(bag, V(0, 0, 0), V(0, 1, 0), V(0, 1, 0), UNIT, 0, 2.6, rr, V(0, UNIT, 0));
		const obj = new LineSegments2(bag.geometry(), twigMat);
		obj.frustumCulled = false;
		return { e, obj, s: e.side === 'above' ? 1 : -1, far: !!e.far };
	});
	const twigs = new ChunkedBag(X0, CHUNK, nChunks);
	for (let i = 0; i < 46; i++) {
		const x = r() * trackW;
		const s = r() < 0.5 ? 1 : -1;
		const dir = V((r() < 0.7 ? 1 : -1) * (0.5 + 0.4 * r()), (0.4 + 0.5 * r()) * s, (r() - 0.5) * 0.8).normalize();
		growBranch(twigs, centre(x), dir, V(0, s, 0), 30 + 70 * r(), 1, 1.6, r);
	}
	for (let i = 0; i < 140; i++) {
		const x = X0 + r() * (X1 - X0);
		const a = r() * 6.28;
		const dir = V(0.6 * (r() - 0.5), Math.cos(a), Math.sin(a)).normalize();
		const origin = centre(x).addScaledVector(dir, 3 + 14 * rough(Math.max(0, Math.min(trackW, x))));
		growBranch(twigs, origin, dir, dir, 8 + 16 * r(), 2, 1.3, r);
	}
	// year ticks
	for (const x of yearXs) {
		const c = centre(x);
		const sp = 8 + 18 * rough(x);
		twigs.polyline([V(c.x, c.y - sp - 8, c.z), V(c.x, c.y + sp + 8, c.z)], [scaled(TINT.white, 1.2), scaled(TINT.white, 1.2)]);
	}

	// --- arrival branch: fibres interleaved by step so instanceCount grows it ---
	const arrive = new Bag();
	const NF = 80,
		NA = 90;
	{
		const fib: { pts: V3[]; cols: RGB[] }[] = [];
		for (let f = 0; f < NF; f++) {
			const th = r() * 6.28,
				rr = f < 6 ? r() * 0.25 : 0.2 + r() * 0.8,
				ph = r() * 6.28,
				k = 3 + r() * 6;
			const tr = r();
			const tint = f < 6 ? TINT.white : tr < 0.5 ? TINT.white : tr < 0.72 ? TINT.lavender : tr < 0.88 ? TINT.blue : TINT.pink;
			const b = 2.5 * (f < 6 ? 1.1 : 0.5 + 0.5 * (1 - rr));
			const pts: V3[] = [],
				cols: RGB[] = [];
			for (let i = 0; i <= NA; i++) {
				const u = i / NA;
				const p = bez(u);
				const tan = bez(Math.min(1, u + 0.01)).sub(bez(Math.max(0, u - 0.01))).normalize();
				const [p1, p2] = perpendiculars(tan);
				const w = (4 + 34 * u) * rr;
				const a = th + 0.8 * Math.sin(u * k + ph);
				p.addScaledVector(p1, w * Math.cos(a)).addScaledVector(p2, w * Math.sin(a));
				pts.push(p);
				cols.push(scaled(tint, b * (1 - 0.35 * u)));
			}
			fib.push({ pts, cols });
		}
		for (let i = 0; i < NA; i++) for (const f of fib) arrive.polyline([f.pts[i], f.pts[i + 1]], [f.cols[i], f.cols[i + 1]]);
	}

	const trunkObjs = [...core.objects(coreMat), ...fine.objects(fineMat), ...twigs.objects(twigMat)];
	for (const o of trunkObjs) scene.add(o);
	const arriveGeo = arrive.geometry();
	const arriveObj = new LineSegments2(arriveGeo, arriveMat);
	arriveGeo.instanceCount = 0;
	arriveObj.visible = false;
	arriveObj.frustumCulled = false;
	scene.add(arriveObj);
	for (const b of branches) scene.add(b.obj);

	// the traveller
	const spriteTex = (() => {
		const c = document.createElement('canvas');
		c.width = c.height = 128;
		const g = c.getContext('2d')!;
		const rg = g.createRadialGradient(64, 64, 0, 64, 64, 64);
		rg.addColorStop(0, 'rgba(255,255,255,1)');
		rg.addColorStop(0.2, 'rgba(240,235,255,0.7)');
		rg.addColorStop(0.5, 'rgba(200,190,255,0.18)');
		rg.addColorStop(1, 'rgba(200,190,255,0)');
		g.fillStyle = rg;
		g.fillRect(0, 0, 128, 128);
		return new THREE.CanvasTexture(c);
	})();
	const traveller = new THREE.Sprite(new THREE.SpriteMaterial({ map: spriteTex, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, depthTest: false }));
	traveller.scale.set(46, 46, 1);
	scene.add(traveller);

	// post
	const composer = new EffectComposer(renderer);
	composer.addPass(new RenderPass(scene, camera));
	// motion blur on the cheap: each frame keeps a fading copy of the last; the damping
	// (trail length) follows the camera's speed and is zero once we have stopped
	const trails = new AfterimagePass(0);
	composer.addPass(trails);
	const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.6, 0.4, 0.5);
	composer.addPass(bloom);
	composer.addPass(new OutputPass());
	// dev hook for live tuning from the console
	if (import.meta.env.DEV) (window as unknown as { __tl: unknown }).__tl = { bloom, trails, uGain, mats, renderer, camera, scene, traveller, branches, centre };

	let w = 1,
		h = 1;
	function resize(width: number, height: number) {
		w = width;
		h = height;
		const pr = Math.min(1.5, window.devicePixelRatio || 1);
		renderer.setPixelRatio(pr);
		renderer.setSize(w, h, false);
		composer.setPixelRatio(pr);
		composer.setSize(w, h);
		camera.aspect = w / h;
		camera.updateProjectionMatrix();
		for (const m of mats) m.resolution.set(w * pr, h * pr);
		coreMat.linewidth = 2.4 * pr;
		fineMat.linewidth = 1.1 * pr;
		twigMat.linewidth = 0.9 * pr;
		arriveMat.linewidth = 2.2 * pr;
		const hh = 2 * 2600 * Math.tan((camera.fov * Math.PI) / 360);
		bg.scale.set(hh * camera.aspect * 1.15, hh * 1.15, 1);
	}

	const refDist = CAM.length();
	const TH_F = Math.atan2(CAM.z, -CAM.x); // angle of the side pose around the trunk
	const D_F = Math.hypot(CAM.x, CAM.z);
	const camPos = V(),
		look = V(),
		tmp = V(),
		tmp2 = V();

	// opening flight. We come in from far along the future extension of the thread, hugging it
	// (just above and beside the fibres, looking along them), already at full speed. The run
	// eases out to a stop exactly at 2026 while the camera swings out from the hugging pose to
	// the resting side pose. At first the camera looks far down the thread, so the fibres
	// converge on the centre of the screen where the star streaks converge; the gaze then
	// shortens onto the traveller. Returns the normalised speed for blur and bloom.
	const easeOut = (u: number) => 1 - Math.pow(1 - u, 3);
	const RUN = 3600; // how far along the future extension we start
	const HUG = V(0, 34, 26); // camera offset from the thread while hugging it
	const hugPos = V(),
		hugLook = V();
	function runOffset(u: number): number {
		return RUN * (1 - easeOut(Math.min(1, u / 0.78)));
	}
	function introPose(cx: number, intro: number): number {
		const u = Math.min(1, intro);
		const off = runOffset(u);
		const speed = Math.min(1, Math.abs(runOffset(u) - runOffset(Math.max(0, u - 0.01))) / (RUN * 0.03));
		// hugging pose: follow the thread's own centre line
		const c = centre(cx + off);
		hugPos.copy(c).add(HUG);
		const gaze = 1400 * (1 - smooth(0, 0.35, u)) + 260; // far down the thread at first, then the traveller
		hugLook.copy(centre(cx + off - gaze));
		// resting pose
		tmp.copy(CAM).setX(CAM.x + cx);
		tmp2.set(cx, 0, 0);
		const o = easeInOut(smooth(0.62, 1, u));
		camPos.copy(hugPos).lerp(tmp, o);
		look.copy(hugLook).lerp(tmp2, o);
		return speed * (1 - o);
	}

	function frame(f: Frame): { anchors: Map<string, Anchor>; years: Anchor[] } {
		const t = f.t / 1000;
		uTime.value = t;
		bgMat.uniforms.uTime.value = t;
		const L = f.leaving;

		// growth of the arrival branch
		const g = smooth(0, 0.45, L);
		arriveObj.visible = L > 0;
		arriveGeo.instanceCount = Math.floor(g * NA) * NF;

		let speed = 0;
		if (f.intro < 1) speed = introPose(f.centreX, f.intro);
		else {
			camPos.copy(CAM).setX(CAM.x + f.centreX);
			look.set(f.centreX, 0, 0);
		}
		if (L > 0) {
			// dolly in to the root of the new branch, then ride just above it looking ahead
			const m = smooth(0.15, 0.5, L);
			const uC = easeInOut(Math.max(0, Math.min(1, (L - 0.42) / 0.58))) * 0.9;
			bez(uC, tmp);
			tmp.y += 4;
			tmp.z += 3;
			camPos.lerp(tmp, m);
			bez(Math.min(1, uC + 0.12), tmp2);
			look.lerp(tmp2, m);
		}
		camera.position.copy(camPos);
		camera.lookAt(look);

		// the fibres burn brighter as we fly into them; speed streaks and glows during the opening run
		const burn = smooth(0.45, 1, L);
		uGainA.value = uGain.value * (1 + 14 * burn);
		bloom.strength = 0.6 + 1.6 * burn + 0.9 * speed;
		(trails.uniforms as { damp: { value: number } }).damp.value = 0.92 * Math.pow(speed, 0.6);
		trails.enabled = speed > 0; // at damp 0 the pass is an identity copy; skip the full-screen blit

		traveller.position.copy(wobble(centre(f.centreX), t));
		const pulse = (0.85 + 0.15 * Math.sin(t * 3)) * (1 - smooth(0.12, 0.32, L));
		traveller.scale.set(46 * pulse, 46 * pulse, 1);

		composer.render();

		const anchors = new Map<string, Anchor>();
		const ui = f.ui;
		const UP = V(0, 1, 0);
		const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
		for (const b of branches) {
			// the thread's own point for this event, on screen
			const P = wobble(centre(b.e.x), t);
			P.y += 3 * b.s;
			tmp.copy(P);
			const d = tmp.distanceTo(camera.position);
			tmp.project(camera);
			const ndcZ = tmp.z;
			const px = ((tmp.x + 1) / 2) * w;
			const py = ((1 - tmp.y) / 2) * h;
			// the DOM scales the lens by distance (and shrinks far-lane lenses); mirror that here
			const sc = Math.max(0.5, Math.min(1.05, refDist / d)) * (b.far ? 0.6 : 1);
			const R = (ui.portalPx / 2) * sc;
			const capH = ui.captions[b.e.id] ?? 0;
			// how far the portal's box reaches beyond its centre, away from the thread and towards it
			const outward = b.far ? Math.max(R, capH / 2) : R + capH;
			const inward = b.far ? Math.max(R, capH / 2) : R;
			// screen offset from the thread: the lane's preferred distance, clamped so the whole box
			// stays inside the viewport (screen y grows downward; b.s = +1 means above the thread)
			const room = b.s > 0 ? py - ui.marginPx - outward : h - ui.marginPx - (ui.footPx ?? 0) - py - outward;
			const minOff = ui.gapPx + inward;
			const off = clamp(b.far ? ui.farLane : ui.nearLane, Math.min(minOff, room), Math.max(minOff, room));
			const tipX = px + (b.far ? 0.55 : 0.4) * off;
			const tipY = py - b.s * off;
			// back to world space at the thread's depth, then pose the branch to reach it
			tmp2.set((tipX / w) * 2 - 1, 1 - (tipY / h) * 2, ndcZ).unproject(camera);
			b.obj.position.copy(P);
			const dir = tmp.copy(tmp2).sub(P);
			const len = dir.length();
			b.obj.quaternion.setFromUnitVectors(UP, dir.normalize());
			b.obj.scale.setScalar(len / UNIT);
			anchors.set(b.e.id, {
				x: tipX,
				y: tipY,
				s: sc,
				visible: ndcZ < 1 && tipX + R > 0 && tipX - R < w // the lens is at least partly on screen
			});
		}
		const proj = (p: V3): Anchor => {
			tmp.copy(p);
			wobble(tmp, t);
			const d = tmp.distanceTo(camera.position);
			tmp.project(camera);
			return {
				x: ((tmp.x + 1) / 2) * w,
				y: ((1 - tmp.y) / 2) * h,
				s: Math.max(0.5, Math.min(1.05, refDist / d)),
				visible: tmp.z < 1 && Math.abs(tmp.x) < 1.25 && Math.abs(tmp.y) < 1.15
			};
		};
		const years = yearXs.map((x) => {
			const c = centre(x);
			c.y -= 20 + 18 * rough(x);
			return proj(c);
		});
		return { anchors, years };
	}

	function dispose() {
		renderer.dispose();
		composer.dispose();
		for (const o of [...trunkObjs, arriveObj]) o.geometry.dispose();
		for (const b of branches) b.obj.geometry.dispose();
		for (const m of mats) m.dispose();
		spriteTex.dispose();
		bgMat.dispose();
	}

	return { resize, frame, dispose };
}
