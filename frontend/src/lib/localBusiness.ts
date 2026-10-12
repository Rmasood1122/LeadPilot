/** Local business mode (docs/features/local-business-mode.md).
 *
 *  Mirrors app/services/local_business.py: the business types, the service
 *  area bounds, and the request bodies the new-strategy wizard sends. Pure
 *  functions, unit-tested in src/tests/localBusiness.test.ts. */

export type BusinessType =
  | "restaurant"
  | "healthcare"
  | "retail"
  | "local_service"
  | "other";

export const BUSINESS_TYPES: { key: BusinessType; label: string; hint: string }[] = [
  { key: "restaurant", label: "Restaurant, café or caterer",
    hint: "Offices nearby for catering and team lunches, event planners, hotels." },
  { key: "healthcare", label: "Clinic, hospital or healthcare practice",
    hint: "Employers (occupational health, screenings), schools, sports clubs, " +
          "referring practices, insurers. Business buyers only — never patients." },
  { key: "retail", label: "Retail or local shop",
    hint: "Nearby offices, schools, property managers and hotels for supply and gifting." },
  { key: "local_service", label: "Salon, fitness or other local service",
    hint: "Employers (staff perks), hotels and venues, property managers." },
  { key: "other", label: "Other local business",
    hint: "Offices and organisations in your area, neighbouring businesses." },
];

export type DistanceUnit = "mi" | "km";

/** Mirrors local_business.MIN_RADIUS / MAX_RADIUS. */
export const RADIUS_BOUNDS: Record<DistanceUnit, [number, number]> = {
  mi: [0.5, 50],
  km: [1, 80],
};

/** Shown next to the radius field: the provider does not apply it. */
export const RADIUS_NOTE =
  "The radius is used for research and messages. The lead provider searches by " +
  "the city or postcode, not by distance.";

export interface LocalDraft {
  businessType: BusinessType | "";
  city: string;
  postalCode: string;
  country: string;
  radius: string;
  unit: DistanceUnit;
  offer: string;
}

export const INITIAL_LOCAL: LocalDraft = {
  businessType: "",
  city: "",
  postalCode: "",
  country: "US",
  radius: "3",
  unit: "mi",
  offer: "",
};

export interface ServiceAreaIn {
  city?: string;
  postal_code?: string;
  country: string;
  radius: number;
  unit: DistanceUnit;
}

/** What is wrong with the draft, in words; [] = valid (or not a local business). */
export function localErrors(draft: LocalDraft | undefined): string[] {
  if (!draft || !draft.businessType) return [];
  const errors: string[] = [];
  if (!draft.city.trim() && !draft.postalCode.trim()) {
    errors.push("Enter a city or a postcode.");
  }
  if (!/^[A-Za-z]{2}$/.test(draft.country.trim())) {
    errors.push("Country must be a two-letter code, e.g. US or GB.");
  }
  const radius = Number(draft.radius);
  const [low, high] = RADIUS_BOUNDS[draft.unit];
  if (!Number.isFinite(radius) || radius < low || radius > high) {
    errors.push(`Radius must be between ${low} and ${high} ${draft.unit}.`);
  }
  if (draft.offer.length > 500) errors.push("Keep the offer under 500 characters.");
  return errors;
}

/** The product-create field: null when this is not a local business. */
export function businessTypeBody(draft: LocalDraft | undefined): BusinessType | null {
  return draft && draft.businessType ? draft.businessType : null;
}

/** The strategy-create fields, or {} when this is not a local business. */
export function strategyLocalBody(
  draft: LocalDraft | undefined,
): { service_area?: ServiceAreaIn; local_offer?: string } {
  if (!draft || !draft.businessType) return {};
  const area: ServiceAreaIn = {
    country: draft.country.trim().toUpperCase(),
    radius: Number(draft.radius),
    unit: draft.unit,
  };
  if (draft.city.trim()) area.city = draft.city.trim();
  if (draft.postalCode.trim()) area.postal_code = draft.postalCode.trim();
  const out: { service_area: ServiceAreaIn; local_offer?: string } = { service_area: area };
  if (draft.offer.trim()) out.local_offer = draft.offer.trim();
  return out;
}

/** "within 3 mi of Astoria, NY, US" -- the same words the server uses. */
export function describeArea(draft: LocalDraft): string {
  const place = [draft.city.trim(), draft.postalCode.trim()].filter(Boolean).join(", ");
  return `within ${Number(draft.radius)} ${draft.unit} of ${place}, ${draft.country.trim().toUpperCase()}`;
}

export function businessTypeLabel(key: string | null | undefined): string | null {
  return BUSINESS_TYPES.find((t) => t.key === key)?.label ?? null;
}
