/** Engagement Hub, Feature 2/3 — the calendar's date and geometry maths.
 *
 * These are the functions the week grid, the month picker and the meeting
 * timer are built out of, and they are pure precisely so the awkward cases can
 * be tested here rather than by clicking around a rendered calendar: a week
 * that crosses a month boundary, a 31st that must not skip a month, a booking
 * that starts before the first rendered hour, and a local date that is a
 * different day in UTC.
 *
 * No calendar library is under test because there is none — see the note at
 * the top of src/lib/calendar/grid.ts.
 */

import { describe, expect, it } from "vitest";

import {
  GRID_END_HOUR,
  GRID_START_HOUR,
  HOUR_HEIGHT,
  addDays,
  addMonths,
  blockGeometry,
  countdown,
  dateKey,
  elapsed,
  formatHour,
  gridHours,
  groupByDay,
  isSameDay,
  isSameMonth,
  monthMatrix,
  startOfWeek,
  weekDays,
  weekdayIndex,
} from "@/lib/calendar/grid";

describe("weekday convention", () => {
  it("is 0=Monday..6=Sunday, matching the backend", () => {
    // The backend stores availability against datetime.weekday(). If these
    // two ever disagree, a rule saved as "Monday" is offered on Sunday and
    // nothing anywhere errors.
    expect(weekdayIndex(new Date(2026, 8, 7))).toBe(0); // Mon 7 Sep 2026
    expect(weekdayIndex(new Date(2026, 8, 13))).toBe(6); // Sun 13 Sep 2026
  });
});

describe("startOfWeek / weekDays", () => {
  it("starts the week on Monday", () => {
    const wednesday = new Date(2026, 8, 9);
    expect(startOfWeek(wednesday).getDate()).toBe(7);
    expect(startOfWeek(wednesday).getHours()).toBe(0);
  });

  it("returns seven consecutive days, Monday first", () => {
    const days = weekDays(new Date(2026, 8, 9));
    expect(days).toHaveLength(7);
    expect(weekdayIndex(days[0])).toBe(0);
    expect(weekdayIndex(days[6])).toBe(6);
    expect(days[6].getDate() - days[0].getDate()).toBe(6);
  });

  it("spans a month boundary without losing a day", () => {
    // Mon 28 Sep – Sun 4 Oct 2026.
    const days = weekDays(new Date(2026, 8, 30));
    expect(days.map((d) => d.getDate())).toEqual([28, 29, 30, 1, 2, 3, 4]);
  });
});

describe("addMonths", () => {
  it("does not skip a month from the 31st", () => {
    // The naive setMonth(+1) on 31 March gives 1 May, so a "next month"
    // button would page straight past April.
    const next = addMonths(new Date(2026, 2, 31), 1);
    expect(next.getMonth()).toBe(3);
  });

  it("goes backwards too", () => {
    expect(addMonths(new Date(2026, 0, 15), -1).getMonth()).toBe(11);
  });
});

describe("addDays", () => {
  it("crosses a year boundary", () => {
    const next = addDays(new Date(2026, 11, 31), 1);
    expect(next.getFullYear()).toBe(2027);
    expect(next.getMonth()).toBe(0);
    expect(next.getDate()).toBe(1);
  });
});

describe("monthMatrix", () => {
  it("is always six rows of seven", () => {
    // A picker whose height changes as you page through the year makes the
    // whole sidebar jump.
    for (const month of [0, 1, 4, 8, 11]) {
      const matrix = monthMatrix(new Date(2026, month, 1));
      expect(matrix).toHaveLength(6);
      expect(matrix.every((week) => week.length === 7)).toBe(true);
    }
  });

  it("pads with the neighbouring months", () => {
    const matrix = monthMatrix(new Date(2026, 8, 1)); // September 2026
    expect(isSameMonth(matrix[0][0], new Date(2026, 7, 1))).toBe(true);
    expect(matrix.flat().some((d) => isSameMonth(d, new Date(2026, 9, 1))))
      .toBe(true);
  });

  it("starts every row on a Monday", () => {
    const matrix = monthMatrix(new Date(2026, 1, 1));
    expect(matrix.every((week) => weekdayIndex(week[0]) === 0)).toBe(true);
  });
});

describe("dateKey", () => {
  it("uses the LOCAL date, not the UTC one", () => {
    // toISOString().slice(0,10) converts to UTC first, so a 23:30 booking
    // files under tomorrow for everyone east of Greenwich. That is the single
    // most common date bug in a calendar UI.
    const late = new Date(2026, 8, 7, 23, 30);
    expect(dateKey(late)).toBe("2026-09-07");
  });

  it("zero-pads", () => {
    expect(dateKey(new Date(2026, 0, 5))).toBe("2026-01-05");
  });
});

describe("blockGeometry", () => {
  const at = (h: number, m = 0) => new Date(2026, 8, 7, h, m);

  it("positions a whole-hour block on its row", () => {
    const { top, height, clipped } = blockGeometry(at(10), at(11));
    expect(top).toBe((10 - GRID_START_HOUR) * HOUR_HEIGHT);
    expect(height).toBe(HOUR_HEIGHT);
    expect(clipped).toBe(false);
  });

  it("draws a half-hour block at half height, on the half hour", () => {
    // A 30-minute call at 10:30 must not be snapped to an hour cell — the
    // grid would then be saying something the calendar does not.
    const { top, height } = blockGeometry(at(10, 30), at(11, 0));
    expect(top).toBe((10.5 - GRID_START_HOUR) * HOUR_HEIGHT);
    expect(height).toBe(HOUR_HEIGHT / 2);
  });

  it("clamps a block starting before the first rendered hour", () => {
    // Drawn at a negative offset it would escape the column and overlap the
    // header.
    const { top, height, clipped } = blockGeometry(at(6), at(8));
    expect(top).toBe(0);
    expect(height).toBe(HOUR_HEIGHT);
    expect(clipped).toBe(true);
  });

  it("clamps a block running past the last rendered hour", () => {
    const { top, height, clipped } = blockGeometry(at(21), at(23, 30));
    expect(top).toBe((21 - GRID_START_HOUR) * HOUR_HEIGHT);
    expect(height).toBe((GRID_END_HOUR - 21) * HOUR_HEIGHT);
    expect(clipped).toBe(true);
  });

  it("never returns a zero height", () => {
    // A 15-minute slot has to be visible, and a degenerate one has to be
    // clickable rather than a 0px sliver nobody can hit.
    expect(blockGeometry(at(10), at(10)).height).toBeGreaterThan(0);
  });
});

describe("gridHours", () => {
  it("covers 7am to 10pm as the brief specifies", () => {
    const hours = gridHours();
    expect(hours[0]).toBe(7);
    expect(hours[hours.length - 1]).toBe(21);
    expect(hours).toHaveLength(GRID_END_HOUR - GRID_START_HOUR);
  });
});

describe("formatHour", () => {
  it("renders noon and midnight as 12, not 0", () => {
    expect(formatHour(0)).toBe("12am");
    expect(formatHour(12)).toBe("12pm");
    expect(formatHour(9)).toBe("9am");
    expect(formatHour(21)).toBe("9pm");
  });
});

describe("groupByDay", () => {
  it("groups by the viewer's local date", () => {
    const grouped = groupByDay([
      { start_at: new Date(2026, 8, 7, 9, 0).toISOString() },
      { start_at: new Date(2026, 8, 7, 23, 45).toISOString() },
      { start_at: new Date(2026, 8, 8, 9, 0).toISOString() },
    ]);
    expect(Object.keys(grouped).sort()).toEqual(["2026-09-07", "2026-09-08"]);
    expect(grouped["2026-09-07"]).toHaveLength(2);
  });
});

describe("countdown", () => {
  const now = new Date(2026, 8, 7, 12, 0);

  it("returns null once the moment has passed", () => {
    // So the caller renders something else entirely rather than a negative
    // countdown on a meeting that already happened.
    expect(countdown(new Date(2026, 8, 7, 11, 59), now)).toBeNull();
  });

  it("counts minutes, hours and days", () => {
    expect(countdown(new Date(2026, 8, 7, 12, 30), now)).toBe("in 30m");
    expect(countdown(new Date(2026, 8, 7, 14, 15), now)).toBe("in 2h 15m");
    expect(countdown(new Date(2026, 8, 10, 12, 0), now)).toBe("in 3 days");
    expect(countdown(new Date(2026, 8, 8, 12, 0), now)).toBe("in 1 day");
  });

  it("says 'now' inside the last minute", () => {
    expect(countdown(new Date(2026, 8, 7, 12, 0, 30), now)).toBe("now");
  });
});

describe("elapsed", () => {
  it("drops the hours field under an hour", () => {
    const start = 1_000_000;
    expect(elapsed(start, start + 65_000)).toBe("01:05");
    expect(elapsed(start, start + 3_725_000)).toBe("1:02:05");
  });

  it("never goes negative on a clock that jumped backwards", () => {
    expect(elapsed(2_000, 1_000)).toBe("00:00");
  });
});

describe("isSameDay", () => {
  it("compares the calendar day, not the instant", () => {
    expect(isSameDay(new Date(2026, 8, 7, 1), new Date(2026, 8, 7, 23))).toBe(
      true,
    );
    expect(isSameDay(new Date(2026, 8, 7), new Date(2027, 8, 7))).toBe(false);
  });
});
