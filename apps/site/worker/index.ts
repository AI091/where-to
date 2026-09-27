/**
 * The site's only server code. Static pages are served straight from assets;
 * requests under /api/ come here (see run_worker_first in wrangler.jsonc).
 *
 * POST /api/feedback stores a correction or request from the "فيه حاجة غلط؟" form in D1.
 */
import { Hono } from 'hono';

type Env = {
	ASSETS: Fetcher;
	DB: D1Database;
	TURNSTILE_SECRET: string;
};

const KINDS = new Set(['wrong_route', 'wrong_name', 'wrong_time', 'route_changed', 'missing_trip', 'other']);
const clip = (v: unknown, max: number) => (typeof v === 'string' ? v.trim().slice(0, max) : '');
// Our own page paths only ("/" or "/some-slug/"): the no-JS redirect below goes back
// to `page`, and "//evil.example" would otherwise make it an open redirect.
const PAGE = /^\/(?:[a-z0-9-]+\/)?$/;

/**
 * Turnstile check: the token must be valid, made for this form (action "feedback"),
 * and issued on the same host that received the post. Fails closed.
 */
async function humanCheck(token: string, secret: string, host: string, ip: string | undefined) {
	if (!token || token.length > 2048 || !secret) return false;
	try {
		const r = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			signal: AbortSignal.timeout(10_000),
			body: new URLSearchParams({ secret, response: token, ...(ip ? { remoteip: ip } : {}) }),
		});
		if (!r.ok) return false;
		const result = (await r.json()) as { success: boolean; action?: string; hostname?: string };
		return result.success === true && result.action === 'feedback' && result.hostname === host;
	} catch {
		return false;
	}
}

const app = new Hono<{ Bindings: Env }>();

app.post('/api/feedback', async (c) => {
	const form = await c.req.parseBody();
	const page = clip(form.page, 200);
	const kind = clip(form.kind, 32);
	const message = clip(form.message, 1000);
	const contact = clip(form.contact, 200);

	if (!PAGE.test(page) || !KINDS.has(kind) || (kind === 'other' && !message)) {
		return c.json({ ok: false, error: 'invalid' }, 400);
	}

	const token = clip(form['cf-turnstile-response'], 2048);
	const host = new URL(c.req.url).hostname;
	if (!(await humanCheck(token, c.env.TURNSTILE_SECRET, host, c.req.header('CF-Connecting-IP')))) {
		if (c.req.header('accept')?.includes('text/html')) return c.redirect(`${page}?retry=1#feedback`, 303);
		return c.json({ ok: false, error: 'verification' }, 403);
	}

	await c.env.DB.prepare('INSERT INTO feedback (page, kind, message, contact) VALUES (?, ?, ?, ?)')
		.bind(page, kind, message || null, contact || null)
		.run();

	// Without JavaScript the browser posts the form itself: send it back to the page.
	if (c.req.header('accept')?.includes('text/html')) {
		return c.redirect(`${page}?shukran=1#feedback`, 303);
	}
	return c.json({ ok: true });
});

app.all('/api/*', (c) => c.json({ ok: false, error: 'not_found' }, 404));

// Anything else falls through to the static site.
app.all('*', (c) => c.env.ASSETS.fetch(c.req.raw));

export default app;
