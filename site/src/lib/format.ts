export const money = (x: number, digits = 0) =>
	x.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: digits });
export const pct = (x: number, digits = 1) => `${x >= 0 ? '' : '−'}${Math.abs(x * 100).toFixed(digits)}%`;
export const signedPct = (x: number, digits = 1) => `${x >= 0 ? '+' : '−'}${Math.abs(x * 100).toFixed(digits)}%`;
export const longDate = (iso: string) =>
	new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
export const monthYear = (iso: string) =>
	new Date(iso).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });
