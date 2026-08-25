<script lang="ts">
	import '../app.css';
	import { base } from '$app/paths';
	import { env } from '$env/dynamic/public';

	let { children } = $props();

	const title = "Yesterday's Portfolio";
	const description = 'Go back to 1 January 2016 with $10,000, place it yourself, hire an adviser who optimises against extreme risk, and watch ten years unfold side by side.';
	// PUBLIC_SITE_URL is set by the Netlify build (see netlify.toml); share cards need absolute URLs
	const site = (env.PUBLIC_SITE_URL ?? '').replace(/\/$/, '');
	// `base` is relative ("./") while prerendering, so absolute share-card URLs are built without it
	const image = site ? `${site}/og.jpg` : `${base}/og.jpg`;
</script>

<svelte:head>
	<title>{title}</title>
	<meta name="description" content={description} />
	<meta name="theme-color" content="#0b0d12" />
	<link rel="icon" href={`${base}/favicon.svg`} type="image/svg+xml" />
	<link rel="apple-touch-icon" href={`${base}/apple-touch-icon.png`} />
	<link rel="manifest" href={`${base}/manifest.webmanifest`} />
	<meta property="og:type" content="website" />
	<meta property="og:title" content={title} />
	<meta property="og:description" content={description} />
	<meta property="og:image" content={image} />
	<meta property="og:image:width" content="1200" />
	<meta property="og:image:height" content="630" />
	{#if site}<meta property="og:url" content={`${site}${base}/`} />{/if}
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content={title} />
	<meta name="twitter:description" content={description} />
	<meta name="twitter:image" content={image} />
</svelte:head>

{@render children()}
