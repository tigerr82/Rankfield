import { describe, expect, it } from "vitest";
import { dayMonth, fullDate, monthShort } from "./format";

describe("date labels", () => {
  it("formats without shifting the day", () => {
    // new Date("2026-08-31") would render 30 Aug in any timezone west of UTC.
    expect(dayMonth("2026-08-31")).toBe("31 Aug");
    expect(fullDate("2026-08-31")).toBe("31 Aug 2026");
    expect(monthShort("2026-07-31")).toBe("Jul");
  });

  it("drops a leading zero on the day", () => {
    expect(dayMonth("2026-09-04")).toBe("4 Sep");
  });

  it("tolerates a timestamp suffix", () => {
    expect(fullDate("2026-08-31T12:00:00Z")).toBe("31 Aug 2026");
  });

  it("renders a dash, never a wrong date, when missing", () => {
    expect(dayMonth(null)).toBe("—");
    expect(fullDate(undefined)).toBe("—");
    expect(monthShort("")).toBe("—");
  });
});
