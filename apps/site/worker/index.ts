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
};

const KINDS = new Set(['wrong_route', 'wrong_name', 'wrong_time', 'route_changed', 'missing_trip', 'other']);
const clip = (v: unknown, max: number) => (typeof v === 'string' ? v.trim().slice(0, max) : '');

const app = new Hono<{ Bindings: Env }>();

app.post('/api/feedback', async (c) => {
	const form = await c.req.parseBody();
	const page = clip(form.page, 200);
	const kind = clip(form.kind, 32);
	const message = clip(form.message, 1000);
	const contact = clip(form.contact, 200);

	if (!page.startsWith('/') || !KINDS.has(kind) || (kind === 'other' && !message)) {
		return c.json({ ok: false, error: 'invalid' }, 400);
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
