/**
 * Generate the data behind the route pages ("ازاي تروح من X لـ Y") from OTP.
 *
 * 1. Ask OTP (in Arabic) for every route and its trip patterns. A pattern runs
 *    from one end of a route to the other; its headsign is where it's heading.
 * 2. Every pattern gives one page: from its origin place to its headsign place,
 *    placed at the pattern's first and last real (surveyed) stops.
 * 3. Plan each trip with OTP and keep the distinct options.
 *
 * Writes src/data/routes.json. The site only builds these pages in draft builds
 * until they are reviewed (see src/pages/[slug].astro).
 *
 * Usage: OTP_URL=http://127.0.0.1:8083/otp/gtfs/v1 LIMIT=50 bun scripts/generate-routes.ts
 */

const OTP_URL = process.env.OTP_URL ?? 'http://127.0.0.1:8083/otp/gtfs/v1';
const LIMIT = Number(process.env.LIMIT ?? 50);
// A fixed weekday morning; the feed runs on frequencies, so the exact time only
// matters for which trips are running.
const DATE = '2026-10-05';
const TIME = '08:00:00';
// Search 90 minutes of departures. A 10-minute window (what the live server may use
// for speed) misses routes that come every 45 minutes; pages are computed once, so
// they can afford the wide window.
const SEARCH_WINDOW_S = 90 * 60;
// The feed OTP was built from, for how often each trip runs (frequencies.txt).
const FEED = process.env.FEED ?? new URL('../../../tools/benchmark/data/otp/s3_250m_ar/alex_gtfs.zip', import.meta.url).pathname;

type Stop = { gtfsId: string; name: string; lat: number; lon: number };
type Pattern = { headsign: string; stops: Stop[] };
type Route = { gtfsId: string; shortName: string; longName: string; patterns: Pattern[] };

async function otp<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
	const res = await fetch(OTP_URL, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json', 'Accept-Language': 'ar' },
		body: JSON.stringify({ query, variables }),
	});
	const body = await res.json();
	if (body.errors) throw new Error(JSON.stringify(body.errors));
	return body.data;
}

const isReal = (s: Stop) => !s.gtfsId.includes('SYN_');

// OTP translates stop and route names but not route_short_name ("Microbus",
// "Bus 480"), so vehicle types come from the same names.csv the feed uses.
function parseCsv(text: string): string[][] {
	const rows: string[][] = [];
	let row: string[] = [], field = '', quoted = false;
	for (let i = 0; i < text.length; i++) {
		const c = text[i];
		if (quoted) {
			if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
			else if (c === '"') quoted = false;
			else field += c;
		} else if (c === '"') quoted = true;
		else if (c === ',') { row.push(field); field = ''; }
		else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
		else if (c !== '\r') field += c;
	}
	if (field || row.length) { row.push(field); rows.push(row); }
	return rows;
}
const namesCsv = parseCsv(await Bun.file(new URL('../../../tools/gtfs/names.csv', import.meta.url)).text());
const vehicles = new Map(namesCsv.filter((r) => r[0] === 'vehicle').map((r) => [r[1], r[2]]));
const vehicleLabel = (shortName: string) => {
	const [kind, ...rest] = shortName.trim().split(' ');
	return [vehicles.get(kind) ?? kind, ...rest].join(' ');
};

// English route names look like "Asafra - Sidi Bishr"; the slug uses the English
// place names so URLs stay readable ASCII.
const slugify = (s: string) =>
	s.toLowerCase().replace(/\(.*?\)/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

type Place = { ar: string; en: string; lat: number; lon: number };
type Pair = { from: Place; to: Place; routes: string[] };

async function pairs(): Promise<Pair[]> {
	const q = `{ routes { gtfsId shortName longName patterns { headsign stops { gtfsId name lat lon } } } }`;
	const [ar, en] = await Promise.all([
		otp<{ routes: Route[] }>(q),
		fetch(OTP_URL, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'Accept-Language': 'en' },
			body: JSON.stringify({ query: q }),
		}).then((r) => r.json()).then((b) => b.data as { routes: Route[] }),
	]);
	const enById = new Map(en.routes.map((r) => [r.gtfsId, r]));

	const byKey = new Map<string, Pair>();
	for (const route of ar.routes) {
		const enRoute = enById.get(route.gtfsId)!;
		const arParts = route.longName.split(' - ');
		const enParts = enRoute.longName.split(' - ');
		route.patterns.forEach((p, i) => {
			const enHeadsign = enRoute.patterns[i]?.headsign ?? '';
			const toIdx = enParts.findIndex((x) => x.trim() === enHeadsign.trim());
			if (toIdx < 0 || arParts.length !== 2 || enParts.length !== 2) return;
			const real = p.stops.filter(isReal);
			if (real.length < 2) return;
			const first = real[0];
			const last = real[real.length - 1];
			const from: Place = { ar: arParts[1 - toIdx].trim(), en: enParts[1 - toIdx].trim(), lat: first.lat, lon: first.lon };
			const to: Place = { ar: arParts[toIdx].trim(), en: enParts[toIdx].trim(), lat: last.lat, lon: last.lon };
			const key = `${from.en}>${to.en}`;
			const pair = byKey.get(key) ?? { from, to, routes: [] };
			pair.routes.push(route.gtfsId);
			byKey.set(key, pair);
		});
	}
	// Places on many routes are the hubs people travel between most.
	const degree = new Map<string, number>();
	for (const p of byKey.values()) {
		degree.set(p.from.en, (degree.get(p.from.en) ?? 0) + 1);
		degree.set(p.to.en, (degree.get(p.to.en) ?? 0) + 1);
	}
	const score = (p: Pair) => (degree.get(p.from.en) ?? 0) + (degree.get(p.to.en) ?? 0);
	return [...byKey.values()].sort((a, b) => score(b) - score(a) || a.from.en.localeCompare(b.from.en));
}

const PLAN = `query Plan($from: InputCoordinates!, $to: InputCoordinates!, $date: String!, $time: String!, $sw: Long, $banned: String) {
  plan(from: $from, to: $to, date: $date, time: $time, numItineraries: 12, searchWindow: $sw, locale: "ar",
       banned: {routes: $banned},
       transportModes: [{mode: BUS}, {mode: WALK}]) {
    itineraries { duration walkDistance legs {
      mode distance duration
      from { name stop { gtfsId } } to { name stop { gtfsId } }
      route { gtfsId shortName longName longNameEn: longName(language: "en") } trip { gtfsId tripHeadsign }
      legGeometry { points }
    } }
  }
}`;

type Leg = {
	mode: string; distance: number; duration: number;
	from: { name: string; stop: { gtfsId: string } | null }; to: { name: string; stop: { gtfsId: string } | null };
	route: { gtfsId: string; shortName: string; longName: string; longNameEn: string } | null;
	trip: { gtfsId: string; tripHeadsign: string } | null;
	legGeometry: { points: string };
};

// Synthetic stops (SYN_) are points on the road, not real stops: you stand there and wave.
const onRoad = (stop: { gtfsId: string } | null) => !!stop && stop.gtfsId.includes('SYN_');
type Itinerary = { duration: number; walkDistance: number; legs: Leg[] };

// Headsigns aren't translated either; they name one end of the route, so take
// that end from the route's Arabic name ("A - B").
function arabicHeadsign(l: Leg): string {
	const headsign = l.trip?.tripHeadsign?.trim() ?? '';
	const en = l.route?.longNameEn.split(' - ').map((x) => x.trim()) ?? [];
	const ar = l.route?.longName.split(' - ').map((x) => x.trim()) ?? [];
	const i = en.indexOf(headsign);
	return i >= 0 && ar.length === en.length ? ar[i] : headsign;
}

// How often each trip runs, in minutes, from the survey's frequencies.txt.
const csvRows = (name: string) => {
	const text = Bun.spawnSync(['unzip', '-p', FEED, name]).stdout.toString();
	const [head, ...rows] = parseCsv(text).filter((r) => r.length > 1);
	return rows.map((r) => Object.fromEntries(head.map((h, i) => [h.trim(), r[i]])));
};
const everyMinutes = new Map(csvRows('frequencies.txt').map((f) => [`1:${f.trip_id}`, Math.round(Number(f.headway_secs) / 60)]));

// "Best" means least hassle, not just fastest: walking counts double and each
// change of vehicle costs 5 minutes, so a 47-minute trip with 1 km of walking
// loses to a 47-minute trip without it.
const hassle = (it: Itinerary) =>
	it.duration / 60 + it.walkDistance / 80 + 5 * (it.legs.filter((l) => l.mode !== 'WALK').length - 1);

async function plan(pair: Pair, allRoutes: string[]) {
	const search = (banned: string[]) =>
		otp<{ plan: { itineraries: Itinerary[] } }>(PLAN, {
			from: { lat: pair.from.lat, lon: pair.from.lon },
			to: { lat: pair.to.lat, lon: pair.to.lon },
			date: DATE,
			time: TIME,
			sw: SEARCH_WINDOW_S,
			banned: banned.join(',') || null,
		});
	// OTP drops a direct route that comes every 45 minutes, because its cost counts
	// the full wait. The page exists because of that route, so also search with every
	// other route banned and let it compete on hassle.
	const [open, direct] = await Promise.all([
		search([]),
		search(allRoutes.filter((r) => !pair.routes.includes(r))),
	]);
	const itineraries = [...open.plan.itineraries, ...direct.plan.itineraries];
	// Headway trips come back as near-copies a minute apart; keep one per sequence of routes.
	const seen = new Set<string>();
	const options = [];
	for (const it of itineraries.sort((a, b) => hassle(a) - hassle(b))) {
		const rides = it.legs.filter((l) => l.mode !== 'WALK');
		if (rides.length === 0) continue;
		const key = rides.map((l) => l.route?.gtfsId).join('>');
		if (seen.has(key)) continue;
		seen.add(key);
		options.push({
			minutes: Math.round(it.duration / 60),
			walkMeters: Math.round(it.walkDistance),
			steps: it.legs.map((l, i) =>
				l.mode === 'WALK'
					? {
							kind: 'walk' as const,
							meters: Math.round(l.distance),
							to: i === it.legs.length - 1 ? pair.to.ar : l.to.name,
							geometry: l.legGeometry.points,
						}
					: {
							kind: 'ride' as const,
							vehicle: vehicleLabel(l.route?.shortName ?? ''),
							route: l.route?.longName ?? '',
							headsign: arabicHeadsign(l),
							from: l.from.name,
							to: l.to.name,
							fromOnRoad: onRoad(l.from.stop),
							toOnRoad: onRoad(l.to.stop),
							minutes: Math.round(l.duration / 60),
							everyMinutes: everyMinutes.get(l.trip?.gtfsId ?? '') ?? null,
							geometry: l.legGeometry.points,
						},
			),
		});
		if (options.length === 3) break;
	}
	return options;
}

const all = await pairs();
const allRoutes = [...new Set(all.flatMap((p) => p.routes))];
const pages = [];
for (const pair of all.slice(0, LIMIT)) {
	const options = await plan(pair, allRoutes);
	if (options.length === 0) {
		console.warn(`no transit option: ${pair.from.en} -> ${pair.to.en}`);
		continue;
	}
	pages.push({ slug: `${slugify(pair.from.en)}-to-${slugify(pair.to.en)}`, from: pair.from, to: pair.to, options });
}
await Bun.write(new URL('../src/data/routes.json', import.meta.url), JSON.stringify({ generatedFor: `${DATE} ${TIME}`, pages }, null, '\t'));
console.log(`${pages.length} pages from ${all.length} candidate pairs`);
