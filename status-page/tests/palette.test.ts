import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { DARK, LIGHT, contrast, type Palette } from "../lib/palette.ts";

const AA_TEXT = 4.5;
const AA_GRAPHIC = 3;

for (const [name, p] of [["light", LIGHT], ["dark", DARK]] as [string, Palette][]) {
  describe(`${name} palette meets WCAG AA`, () => {
    for (const bg of ["bg", "surface"] as const) {
      it(`body, muted and link text on ${bg}`, () => {
        for (const fg of ["text", "muted", "link"] as const) {
          assert.ok(contrast(p[fg], p[bg]) >= AA_TEXT, `${fg} on ${bg}: ${contrast(p[fg], p[bg]).toFixed(2)}`);
        }
      });
      it(`every status label colour on ${bg}`, () => {
        for (const [status, colour] of Object.entries(p.status)) {
          assert.ok(contrast(colour, p[bg]) >= AA_TEXT, `${status} on ${bg}: ${contrast(colour, p[bg]).toFixed(2)}`);
        }
      });
    }
    it("focus ring and no-data bars are visible (3:1)", () => {
      assert.ok(contrast(p.focus, p.surface) >= AA_GRAPHIC);
      assert.ok(contrast(p.nodata, p.surface) >= AA_GRAPHIC, `nodata ${contrast(p.nodata, p.surface).toFixed(2)}`);
    });
  });
}

describe("contrast()", () => {
  it("matches the WCAG reference values", () => {
    assert.equal(contrast("#000000", "#ffffff").toFixed(1), "21.0");
    assert.equal(contrast("#777777", "#ffffff").toFixed(2), "4.48");
  });
});
