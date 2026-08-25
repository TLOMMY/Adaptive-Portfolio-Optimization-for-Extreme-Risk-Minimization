<script lang="ts">
	// A canvas starfield. Idle: slow drift, twinkle, occasional meteor with a trail.
	// Warp: stars rush toward the viewer, streak, and the screen burns to white.
	import { onMount } from 'svelte';

	// warp: accelerate to full speed, then call ondark once the streaks are at full speed; the
	// canvas keeps streaking after that so the next stage can fade in underneath it.
	let { warp = false, ondark }: { warp?: boolean; ondark?: () => void } = $props();

	let canvas: HTMLCanvasElement;

	interface Star {
		x: number; // -1..1 (relative to centre)
		y: number;
		z: number; // depth 0.05..1
		tw: number; // twinkle phase
		s: number; // size
	}
	interface Meteor {
		x: number;
		y: number;
		vx: number;
		vy: number;
		life: number;
	}

	onMount(() => {
		const ctx = canvas.getContext('2d')!;
		const stars: Star[] = [];
		const N = 700;
		for (let i = 0; i < N; i++) stars.push(newStar(true));
		let meteor: Meteor | null = null;
		let nextMeteor = 1500;
		let speed = 0; // warp speed
		let warpStart = 0;
		let raf = 0;
		let last = performance.now();
		let w = 0,
			h = 0,
			dpr = 1;

		function newStar(anyDepth: boolean): Star {
			return {
				x: (Math.random() * 2 - 1) * 1.6,
				y: (Math.random() * 2 - 1) * 1.6,
				z: anyDepth ? 0.05 + Math.random() * 0.95 : 1,
				tw: Math.random() * Math.PI * 2,
				s: 0.5 + Math.random() * 1.3
			};
		}
		function resize() {
			dpr = Math.min(2, window.devicePixelRatio || 1);
			w = canvas.clientWidth;
			h = canvas.clientHeight;
			canvas.width = w * dpr;
			canvas.height = h * dpr;
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		}
		resize();
		window.addEventListener('resize', resize);

		function frame(t: number) {
			const dt = Math.min(50, t - last);
			last = t;
			if (warp && !warpStart) warpStart = t;
			if (warpStart) {
				const e = (t - warpStart) / 1000;
				speed = Math.min(6, 0.15 * Math.exp(1.6 * e)); // exponential acceleration
				if (e >= 2.3 && ondark) {
					ondark();
					ondark = undefined;
				}
			}

			ctx.fillStyle = warpStart ? `rgba(4,5,10,${Math.max(0.25, 1 - speed / 6)})` : '#04050a';
			ctx.fillRect(0, 0, w, h);
			const cx = w / 2,
				cy = h / 2,
				R = Math.max(w, h) * 0.55;

			for (const s of stars) {
				s.tw += dt * 0.002;
				if (speed > 0) {
					const pz = s.z;
					s.z -= speed * dt * 0.001 * (0.3 + s.z);
					if (s.z <= 0.02) {
						Object.assign(s, newStar(false));
						continue;
					}
					// streak from previous depth to current
					const x0 = cx + (s.x / pz) * R,
						y0 = cy + (s.y / pz) * R;
					const x1 = cx + (s.x / s.z) * R,
						y1 = cy + (s.y / s.z) * R;
					ctx.strokeStyle = `rgba(232,226,208,${Math.min(1, 0.35 + speed / 5)})`;
					ctx.lineWidth = s.s * (1 + speed / 3) * (1.2 - s.z);
					ctx.beginPath();
					ctx.moveTo(x0, y0);
					ctx.lineTo(x1, y1);
					ctx.stroke();
				} else {
					s.x += dt * 0.000004;
					const x = cx + (s.x / s.z) * R,
						y = cy + (s.y / s.z) * R;
					if (x < -10 || x > w + 10 || y < -10 || y > h + 10) {
						Object.assign(s, newStar(true));
						continue;
					}
					const a = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(s.tw)) * (1.1 - s.z);
					ctx.fillStyle = `rgba(232,226,208,${a.toFixed(3)})`;
					ctx.beginPath();
					ctx.arc(x, y, s.s * (1.3 - s.z), 0, Math.PI * 2);
					ctx.fill();
				}
			}

			// meteor
			if (!warpStart) {
				nextMeteor -= dt;
				if (!meteor && nextMeteor <= 0) {
					meteor = {
						x: w * (0.55 + Math.random() * 0.4),
						y: h * (0.05 + Math.random() * 0.25),
						vx: -(0.9 + Math.random() * 0.5),
						vy: 0.45 + Math.random() * 0.3,
						life: 1
					};
					nextMeteor = 3500 + Math.random() * 4000;
				}
				if (meteor) {
					const len = 160;
					const g = ctx.createLinearGradient(meteor.x, meteor.y, meteor.x - meteor.vx * len, meteor.y - meteor.vy * len);
					g.addColorStop(0, `rgba(255,250,235,${meteor.life})`);
					g.addColorStop(1, 'rgba(255,250,235,0)');
					ctx.strokeStyle = g;
					ctx.lineWidth = 2;
					ctx.lineCap = 'round';
					ctx.beginPath();
					ctx.moveTo(meteor.x, meteor.y);
					ctx.lineTo(meteor.x - meteor.vx * len, meteor.y - meteor.vy * len);
					ctx.stroke();
					ctx.fillStyle = `rgba(255,255,255,${meteor.life})`;
					ctx.beginPath();
					ctx.arc(meteor.x, meteor.y, 2.2, 0, Math.PI * 2);
					ctx.fill();
					meteor.x += meteor.vx * dt * 0.9;
					meteor.y += meteor.vy * dt * 0.9;
					meteor.life -= dt / 1400;
					if (meteor.life <= 0 || meteor.x < -200 || meteor.y > h + 200) meteor = null;
				}
			}
			raf = requestAnimationFrame(frame);
		}
		raf = requestAnimationFrame(frame);
		return () => {
			cancelAnimationFrame(raf);
			window.removeEventListener('resize', resize);
		};
	});
</script>

<canvas bind:this={canvas} class="stars" aria-hidden="true"></canvas>

<style>
	.stars {
		position: fixed;
		inset: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
		z-index: 0;
	}
</style>
