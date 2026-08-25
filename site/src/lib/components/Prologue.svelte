<script lang="ts">
	// Scroll-driven prologue: each beat is a full screen; its text fades in as it
	// reaches the middle of the viewport and out as it leaves.
	import { onMount } from 'svelte';
	import { app } from '$lib/state.svelte';

	const beats = [
		['The best time to start investing', 'was ten years ago.'],
		['The second best time', 'is now.'],
		['But what if', 'you could go back?'],
		['Ten years.', 'One wish.']
	];

	let amountText = $state('100,000');
	const warping = $derived(app.warp);
	let scrollY = $state(0);
	let vh = $state(800);

	onMount(() => {
		const onScroll = () => (scrollY = window.scrollY);
		const onResize = () => (vh = window.innerHeight);
		onResize();
		window.addEventListener('scroll', onScroll, { passive: true });
		window.addEventListener('resize', onResize);
		return () => {
			window.removeEventListener('scroll', onScroll);
			window.removeEventListener('resize', onResize);
		};
	});

	// The text is pinned; scrolling only moves `progress` through the beats and
	// each beat crossfades in and out around its own integer position.
	const total = $derived(beats.length + 1);
	const progress = $derived(vh > 0 ? Math.max(0, Math.min(total - 1, scrollY / vh)) : 0);
	function pose(i: number) {
		const d = progress - i; // 0 when beat i is centred
		const o = Math.max(0, 1 - Math.abs(d) * 1.8);
		return { opacity: o, scale: 1 - Math.abs(d) * 0.06 };
	}

	const wishPose = $derived(pose(beats.length));

	function wish() {
		const n = Number(amountText.replace(/[^0-9.]/g, ''));
		if (n >= 100) app.amount = Math.round(n);
		app.warp = true;
	}
</script>

<div class="prologue" class:warping style:height={`${total * vh}px`}>
	<div class="pin">
	{#each beats as [a, b], i (i)}
		{@const p = pose(i)}
		<div class="text" style:opacity={p.opacity} style:transform={`scale(${p.scale})`} style:pointer-events="none">
			<p class="line">{a}</p>
			<p class="line">{b}</p>
		</div>
	{/each}
		<div class="text wish" style:opacity={wishPose.opacity} style:transform={`scale(${wishPose.scale})`} style:pointer-events={wishPose.opacity > 0.5 ? 'auto' : 'none'}>
			<p class="line small">I wish I could go back to the first of January, 2016,</p>
			<p class="line small">with</p>
			<label class="amount mono">
				<span>$</span><input bind:value={amountText} inputmode="numeric" aria-label="amount to invest" />
			</label>
			<p class="line small">to invest.</p>
			<button class="wishbtn" onclick={wish} disabled={warping}>Make the wish</button>
		</div>
	</div>
	<p class="hint mono" style:opacity={scrollY < 40 ? 0.7 : 0}>scroll</p>
</div>

<style>
	.prologue {
		position: relative;
		z-index: 1;
	}
	.pin {
		position: sticky;
		top: 0;
		height: 100vh;
		height: 100dvh;
		display: grid;
		place-items: center;
		text-align: center;
		padding: 0 1.5rem;
	}
	.text {
		grid-area: 1 / 1;
		will-change: opacity, transform;
		max-width: 46rem;
	}
	.line {
		font-size: clamp(1.8rem, 4.2vw, 3.4rem);
		line-height: 1.15;
		margin: 0;
		color: #ece7d8;
		letter-spacing: -0.01em;
	}
	.line.small {
		font-size: clamp(1.2rem, 2.4vw, 1.9rem);
	}
	.amount {
		display: inline-flex;
		align-items: baseline;
		gap: 0.2rem;
		font-size: clamp(2.4rem, 6vw, 4.5rem);
		color: #fff;
		border-bottom: 1px solid rgba(236, 231, 216, 0.5);
		margin: 0.6rem 0;
	}
	.amount input {
		font: inherit;
		color: inherit;
		background: transparent;
		border: 0;
		outline: 0;
		width: 8ch;
	}
	.wishbtn {
		margin-top: 2.2rem;
		padding: 0.8rem 2rem;
		border: 1px solid rgba(236, 231, 216, 0.7);
		background: rgba(236, 231, 216, 0.06);
		color: #ece7d8;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		font-size: 0.75rem;
		border-radius: 999px;
		transition:
			background 0.3s,
			box-shadow 0.3s;
	}
	.wishbtn:hover {
		background: rgba(236, 231, 216, 0.16);
		box-shadow: 0 0 24px rgba(236, 231, 216, 0.25);
	}
	.wishbtn:disabled {
		opacity: 0.5;
	}
	.hint {
		position: fixed;
		bottom: 1.2rem;
		left: 50%;
		transform: translateX(-50%);
		font-size: 0.65rem;
		letter-spacing: 0.3em;
		text-transform: uppercase;
		color: #ece7d8;
		transition: opacity 0.6s;
		z-index: 1;
	}
	.warping .text {
		transition: opacity 0.8s;
		opacity: 0 !important;
	}
</style>
