<script lang="ts">
	// A small geometric mark per adviser, hand-drawn so each archetype is recognisable at a glance.
	let { profileKey, size = 56 }: { profileKey: string; size?: number } = $props();
	const tone: Record<string, string> = {
		preserver: '#5b6f8a',
		steady: '#6a8a6e',
		builder: '#b8792b',
		maverick: '#a8321f',
		sprinter: '#7a5c9e',
		ethical: '#4f8a7c'
	};
	const fill = $derived(tone[profileKey] ?? '#777');
</script>

<svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label={`${profileKey} mark`}>
	<circle cx="32" cy="32" r="31" fill={fill} opacity="0.14" />
	<circle cx="32" cy="32" r="31" fill="none" stroke={fill} stroke-width="1.5" />
	{#if profileKey === 'preserver'}
		<!-- a shield -->
		<path d="M32 14 L46 19 V33 C46 42 39 47 32 50 C25 47 18 42 18 33 V19 Z" fill="none" stroke={fill} stroke-width="2.2" />
		<path d="M32 22 V42" stroke={fill} stroke-width="2.2" />
	{:else if profileKey === 'steady'}
		<!-- a balance: three level bars -->
		<path d="M18 24 H46 M18 32 H46 M18 40 H46" stroke={fill} stroke-width="2.6" stroke-linecap="round" />
	{:else if profileKey === 'builder'}
		<!-- rising steps -->
		<path d="M16 46 H26 V38 H34 V30 H42 V20 H48" fill="none" stroke={fill} stroke-width="2.6" stroke-linejoin="round" />
	{:else if profileKey === 'maverick'}
		<!-- a bolt -->
		<path d="M36 14 L22 36 H32 L28 50 L44 26 H34 Z" fill={fill} opacity="0.9" />
	{:else if profileKey === 'sprinter'}
		<!-- chevrons forward -->
		<path d="M20 20 L30 32 L20 44 M32 20 L42 32 L32 44" fill="none" stroke={fill} stroke-width="2.6" stroke-linejoin="round" />
	{:else if profileKey === 'ethical'}
		<!-- a leaf -->
		<path d="M20 44 C20 28 30 18 46 18 C46 34 36 44 20 44 Z" fill="none" stroke={fill} stroke-width="2.2" />
		<path d="M22 42 L42 22" stroke={fill} stroke-width="1.6" />
	{:else}
		<circle cx="32" cy="32" r="8" fill={fill} />
	{/if}
</svg>
