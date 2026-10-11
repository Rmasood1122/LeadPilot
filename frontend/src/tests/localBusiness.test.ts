/** Local business mode -- the wizard's validation and request bodies
 *  (mirrors app/services/local_business.py ServiceArea). */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { canAdvance, INITIAL_INTAKE, type IntakeState } from "@/components/intake/wizard";
import { createProduct, createStrategy } from "@/lib/api/strategies";
import {
  BUSINESS_TYPES,
  INITIAL_LOCAL,
  businessTypeBody,
  describeArea,
  localErrors,
  strategyLocalBody,
  type LocalDraft,
} from "@/lib/localBusiness";

const CAFE: LocalDraft = {
  ...INITIAL_LOCAL,
  businessType: "restaurant",
  city: " Astoria, NY ",
  country: "us",
  radius: "3",
  offer: " Team lunch catering ",
};

describe("localErrors", () => {
  it("not a local business is always valid", () => {
    expect(localErrors(undefined)).toEqual([]);
    expect(localErrors({ ...INITIAL_LOCAL, city: "" })).toEqual([]);
  });

  it("a complete draft is valid", () => expect(localErrors(CAFE)).toEqual([]));

  it("needs a city or a postcode", () =>
    expect(localErrors({ ...CAFE, city: "", postalCode: "" })[0]).toMatch(/city or a postcode/));

  it("needs a two-letter country", () =>
    expect(localErrors({ ...CAFE, country: "USA" })[0]).toMatch(/two-letter/));

  it("bounds the radius per unit", () => {
    expect(localErrors({ ...CAFE, radius: "51" })[0]).toMatch(/between 0.5 and 50 mi/);
    expect(localErrors({ ...CAFE, radius: "80", unit: "km" })).toEqual([]);
    expect(localErrors({ ...CAFE, radius: "0.2" })).toHaveLength(1);
    expect(localErrors({ ...CAFE, radius: "abc" })).toHaveLength(1);
  });
});

describe("request bodies", () => {
  it("non-local sends nothing extra", () => {
    expect(businessTypeBody(undefined)).toBeNull();
    expect(strategyLocalBody({ ...INITIAL_LOCAL })).toEqual({});
  });

  it("local sends a trimmed service area and offer", () => {
    expect(businessTypeBody(CAFE)).toBe("restaurant");
    expect(strategyLocalBody(CAFE)).toEqual({
      service_area: { city: "Astoria, NY", country: "US", radius: 3, unit: "mi" },
      local_offer: "Team lunch catering",
    });
  });

  it("describes the area like the server", () =>
    expect(describeArea(CAFE)).toBe("within 3 mi of Astoria, NY, US"));

  it("lists the five business types, healthcare as business buyers only", () => {
    expect(BUSINESS_TYPES.map((t) => t.key)).toEqual(
      ["restaurant", "healthcare", "retail", "local_service", "other"]);
    expect(BUSINESS_TYPES[1].hint).toMatch(/never patients/);
  });
});

describe("wizard gate", () => {
  const filled: IntakeState = {
    ...INITIAL_INTAKE,
    product: { name: "Bella Cafe", description: "Cafe", type: "product" },
  };

  it("an invalid service area blocks Continue", () => {
    expect(canAdvance({ ...filled, local: { ...CAFE, country: "" } })).toBe(false);
    expect(canAdvance({ ...filled, local: CAFE })).toBe(true);
    expect(canAdvance(filled)).toBe(true);
  });
});

describe("wire bodies are objects (no double stringify)", () => {
  let calls: { url: string; init: RequestInit }[] = [];

  beforeEach(() => {
    calls = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({ id: "x" }), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("createProduct carries business_type", async () => {
    await createProduct({ name: "B", description: "C", type: "product",
                          business_type: "retail" });
    const body = JSON.parse(calls[0].init.body as string);
    expect(body.business_type).toBe("retail");
  });

  it("createStrategy carries the service area", async () => {
    await createStrategy("p1", false, undefined, strategyLocalBody(CAFE));
    const body = JSON.parse(calls[0].init.body as string);
    expect(body.flow_type).toBe("no_clients");
    expect(body.service_area.city).toBe("Astoria, NY");
  });

  it("createStrategy without local context is unchanged", async () => {
    await createStrategy("p1", true);
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ flow_type: "with_clients" });
  });
});
