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

	// The amount box accepts whole dollars only: digits are kept, everything else dropped (a pasted
	// "$1,000.50" becomes 1,000), leading zeros are trimmed, and it stops at nine digits. Commas are
	// regrouped on every keystroke and the caret is put back where it was among the digits.
	const MIN = 100,
		MAX_DIGITS = 9;
	const group = (digits: string) => digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
	function typed(e: Event) {
		const el = e.target as HTMLInputElement;
		const raw = el.value;
		const caret = el.selectionStart ?? raw.length;
		const digitsBefore = raw.slice(0, caret).replace(/\D/g, '').length;
		const whole = raw.split('.')[0]; // drop any cents
		const digits = whole.replace(/\D/g, '').replace(/^0+(?=\d)/, '').slice(0, MAX_DIGITS);
		amountText = group(digits);
		// the box is rewritten even when the state did not change (a rejected letter must not linger)
		el.value = amountText;
		let pos = 0,
			seen = 0;
		while (pos < amountText.length && seen < digitsBefore) if (/\d/.test(amountText[pos++])) seen++;
		el.setSelectionRange(pos, pos);
	}
	const amount = $derived(Number(amountText.replace(/\D/g, '')) || 0);
	const valid = $derived(amount >= MIN);
	// long amounts shrink a little so nine digits still fit on a narrow phone
	const shrink = $derived(Math.min(1, 8 / Math.max(8, amountText.length)));

	function wish() {
		if (!valid || warping) return;
		app.amount = amount;
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
			<label class="amount mono" style:font-size={`calc(clamp(2.4rem, 6vw, 4.5rem) * ${shrink})`}>
				<span>$</span><input
					value={amountText}
					oninput={typed}
					onkeydown={(e) => e.key === 'Enter' && wish()}
					inputmode="numeric"
					autocomplete="off"
					enterkeyhint="go"
					aria-label="amount to invest"
					aria-invalid={!valid}
					style:width={`${Math.max(1, amountText.length) + 0.8}ch`}
				/>
			</label>
			<p class="line small">to invest.</p>
			<p class="note mono" style:opacity={valid ? 0 : 0.7}>at least ${MIN.toLocaleString()}</p>
			<button class="wishbtn" onclick={wish} disabled={warping || !valid}>Make the wish</button>
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
		padding: 0;
		min-width: 1.4ch;
		caret-color: #ece7d8;
	}
	.note {
		font-size: 0.65rem;
		letter-spacing: 0.25em;
		text-transform: uppercase;
		color: #ece7d8;
		margin: 0.4rem 0 0;
		transition: opacity 0.3s;
	}
	.wishbtn {
		margin-top: 1.4rem;
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
		cursor: not-allowed;
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
