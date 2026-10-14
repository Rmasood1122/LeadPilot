/**
 * The product-facts file (src/content/product-facts.json) is what pages and
 * JSON-LD read. Guard its shape and its rules (docs/program/ai-visibility/SPEC.md 2.3).
 */
import { describe, expect, it } from "vitest";

import { PRODUCT_FACTS, PRODUCT_FULL_NAME } from "@/lib/productFacts";

describe("product facts", () => {
  it("builds the full product name from the brand constants", () => {
    expect(PRODUCT_FULL_NAME).toBe(`${PRODUCT_FACTS.brand.product_name} by ${PRODUCT_FACTS.brand.company_name}`);
    expect(PRODUCT_FACTS.description.startsWith(PRODUCT_FULL_NAME)).toBe(true);
  });

  it("keeps the tagline to 60 characters or fewer", () => {
    expect(PRODUCT_FACTS.tagline.length).toBeLessThanOrEqual(60);
  });

  it("gives every capability a known status", () => {
    const statuses = Object.keys(PRODUCT_FACTS.status_labels);
    for (const c of PRODUCT_FACTS.capabilities) expect(statuses).toContain(c.status);
  });

  it("every channel points at a capability", () => {
    const ids = PRODUCT_FACTS.capabilities.map((c) => c.id);
    for (const ch of PRODUCT_FACTS.channels) expect(ids).toContain(ch.capability);
  });

  it("states compliance as what the product does, never as a legal status", () => {
    const text = JSON.stringify(PRODUCT_FACTS);
    expect(text).not.toMatch(/\b(CAN-SPAM|GDPR|CASL|PDPA|TCPA)[- ]compliant\b|compliant with|fully compliant|compliance (maintained|guaranteed)/i);
  });

  it("keeps the home page's banned promises out of the facts it now supplies", () => {
    // The same phrases src/tests/homeClaims.test.ts bans in the home files;
    // AUDIENCES and NOT_A_FIT moved from content.ts into this file.
    const text = JSON.stringify(PRODUCT_FACTS);
    for (const phrase of [/guarantee/i, /no credit card/i, /unlimited/i, /auto-?repl(y|ies)/i,
      /upload (your|a) (contact )?list/i, /\b\d+x\b|\b\d+%\s+(more|higher|better)/i]) {
      expect(text).not.toMatch(phrase);
    }
  });

  it("names no rating, review, customer count or superlative", () => {
    const text = JSON.stringify(PRODUCT_FACTS);
    expect(text).not.toMatch(/\b(#1|best|leading|rated|customers? trust)\b|(?<!send-)\breviews?\b/i);
  });
});
