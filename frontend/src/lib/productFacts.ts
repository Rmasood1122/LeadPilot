/**
 * The one source of product facts for the public site (pages, JSON-LD and,
 * later, llms.txt): src/content/product-facts.json.
 *
 * The brand is defined once there (brand.product_name, brand.company_name).
 * Titles are literal strings in each page.tsx (src/tests/websiteClaims.test.ts
 * reads them from source), so after a rename scripts/seo/check_static_seo.mjs
 * fails every title that lacks the new PRODUCT_FULL_NAME until it is updated.
 *
 * A capability is described as working only when its status is "live", which
 * is a founder answer (docs/program/ai-visibility/NOTES.md), not a flag.
 */

import facts from "@/content/product-facts.json";

export type CapabilityStatus = keyof typeof facts.status_labels;
export type CapabilityId = (typeof facts.capabilities)[number]["id"];

export const PRODUCT_FACTS = facts;
export const PRODUCT_NAME = facts.brand.product_name;
export const COMPANY_NAME = facts.brand.company_name;
/** "LeadPilot by Calendarharvest": how the product is named in titles and first mentions. */
export const PRODUCT_FULL_NAME = `${PRODUCT_NAME} by ${COMPANY_NAME}`;

export function capability(id: CapabilityId) {
  const found = facts.capabilities.find((c) => c.id === id);
  if (!found) throw new Error(`unknown capability ${id}`);
  return { ...found, status: found.status as CapabilityStatus };
}

export function statusLabel(status: CapabilityStatus): string {
  return facts.status_labels[status];
}

export function capabilitiesWithStatus(status: CapabilityStatus) {
  return facts.capabilities.filter((c) => c.status === status);
}
