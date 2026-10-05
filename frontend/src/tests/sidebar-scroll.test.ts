import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/** The desktop sidebar is a fixed-height column. Without min-h-0 and
 *  overflow-y-auto on the nav, entries past the viewport are unreachable. */
describe("sidebar scrolls", () => {
  const src = readFileSync("src/components/shell/Shell.tsx", "utf8");
  it("the desktop nav list can scroll and the footer cannot be squeezed", () => {
    expect(src).toMatch(/<nav className="min-h-0 flex-1[^"]*overflow-y-auto/);
    expect(src).toMatch(/className="shrink-0 p-2"/);
  });
});
