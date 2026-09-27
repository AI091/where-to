/**
 * Turns a route page's raw OTP steps into what the page says and draws.
 * Shared by every design option so they differ only in presentation.
 */
import data from '../data/routes.json';

export type Page = (typeof data.pages)[number];
export type Option = Page['options'][number];
type RawStep = Option['steps'][number];
type Ride = Extract<RawStep, { kind: 'ride' }>;

export type Vehicle = 'microbus' | 'tomnaya' | 'bus' | 'minibus';

export const vehicleOf = (label: string): Vehicle =>
	label.startsWith('مشروع') ? 'microbus' : label.startsWith('تمناية') ? 'tomnaya' : label.startsWith('ميني') ? 'minibus' : 'bus';

// Plate colours: orange for the microbus (المشروع), blue for the تمناية.
export const vehicleColor: Record<Vehicle, string> = {
	microbus: '#e8871e',
	tomnaya: '#2f6fb3',
	bus: '#0b5e7a',
	minibus: '#277a61',
};

// Text on a vehicle's colour: dark ink on the microbus orange, white on the rest (all ≥ 4.5:1).
export const vehicleInk: Record<Vehicle, string> = {
	microbus: '#1d2830',
	tomnaya: '#ffffff',
	bus: '#ffffff',
	minibus: '#ffffff',
};

// "المشروع" is what Alexandrians call the microbus; the bracket in the label is for everyone else.
export const vehicleShort = (label: string) => label.replace(/\s*\(.*\)/, '');

/** Egyptian "to X": لسيدي بشر, and للعصافرة when the name starts with ال. */
export const li = (name: string) => (name.startsWith('ال') ? `لل${name.slice(2)}` : `ل${name}`);
export const round5 = (m: number) => Math.max(5, Math.round(m / 5) * 5);
export const walkMinutes = (meters: number) => Math.max(1, Math.round(meters / 80));

export const rides = (o: Option) => o.steps.filter((s): s is Ride => s.kind === 'ride');

export type ViewStep =
	| { type: 'walk'; meters: number; minutes: number; to: string }
	| { type: 'board'; ride: Ride; vehicle: Vehicle }
	| { type: 'alight'; ride: Ride; vehicle: Vehicle }
	| { type: 'arrive'; place: string };

/** The steps a rider follows, in order. Walks under 50 m are dropped: you're already there. */
export function viewSteps(page: Page, option: Option): ViewStep[] {
	const out: ViewStep[] = [];
	for (const s of option.steps) {
		if (s.kind === 'walk') {
			if (s.meters >= 50) out.push({ type: 'walk', meters: s.meters, minutes: walkMinutes(s.meters), to: s.to });
		} else {
			const vehicle = vehicleOf(s.vehicle);
			out.push({ type: 'board', ride: s, vehicle }, { type: 'alight', ride: s, vehicle });
		}
	}
	out.push({ type: 'arrive', place: page.to.ar });
	return out;
}

/** What to do to get on: at a real stop you board there; on the road you stand and wave. */
export const boardText = (r: Ride) =>
	r.fromOnRoad ? `استنى على ${r.from} وشاور لل${vehicleShort(r.vehicle)}` : `اركب من ${r.from}`;

export const walkText = (meters: number) => (meters < 50 ? 'من غير مشي تقريباً' : `مشي حوالي ${meters} متر`);

/** Google's encoded polyline format (precision 5) → [lat, lon] pairs. */
export function decodePolyline(s: string): [number, number][] {
	const pts: [number, number][] = [];
	let i = 0, lat = 0, lon = 0;
	while (i < s.length) {
		for (const which of [0, 1]) {
			let shift = 0, result = 0, b: number;
			do {
				b = s.charCodeAt(i++) - 63;
				result |= (b & 0x1f) << shift;
				shift += 5;
			} while (b >= 0x20);
			const d = result & 1 ? ~(result >> 1) : result >> 1;
			if (which === 0) lat += d;
			else lon += d;
		}
		pts.push([lat / 1e5, lon / 1e5]);
	}
	return pts;
}

/** "دقيقة"، "دقيقتين"، "3 دقايق"، "15 دقيقة": Egyptian counting of minutes. */
export const mins = (n: number) =>
	n <= 1 ? 'دقيقة' : n === 2 ? 'دقيقتين' : n <= 10 ? `${n} دقايق` : `${n} دقيقة`;

/** "بيعدي كل دقيقة"، "بيعدي كل 9 دقايق": how often the vehicle comes, from the survey. */
export const everyText = (n: number | null) => (n ? `بيعدي كل ${n <= 1 ? 'دقيقة' : mins(n)} تقريباً` : '');
// Fares are in whole and half pounds: 8.5 reads «8 جنيه ونص».
export const fareText = (egp: number) =>
	Number.isInteger(egp) ? `${egp} جنيه` : Number.isInteger(egp * 2) ? `${Math.floor(egp)} جنيه ونص` : `${egp} جنيه`;

