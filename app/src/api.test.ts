import { describe, expect, it } from "vitest";
import { parseSse } from "./api";
import { ago, daysLeft, gb, mib } from "./format";

describe("parseSse", () => {
  it("splits complete events and keeps the partial tail", () => {
    const buf = 'event: token\ndata: {"type":"token","text":"Sal"}\n\nevent: sentence\ndata: {"type":"sentence","text":"Salut."}\n\nevent: done\ndata: {"type":"do';
    const { events, rest } = parseSse(buf);
    expect(events).toEqual([{ type: "token", text: "Sal" }, { type: "sentence", text: "Salut." }]);
    expect(rest).toBe('event: done\ndata: {"type":"do');
  });
  it("ignores malformed blocks", () => {
    expect(parseSse("data: nope\n\n").events).toEqual([]);
  });
});

describe("format", () => {
  const now = Date.parse("2026-09-23T13:00:00+03:00");
  it("ago", () => {
    expect(ago("2026-09-23T12:55:00+03:00", now)).toBe("5 min");
    expect(ago("2026-09-23T07:40:00+03:00", now)).toBe("5.3 h");
    expect(ago("2026-09-21T13:00:00+03:00", now)).toBe("2 z");
    expect(ago("2026-09-23T21:00:00+03:00", now)).toBe("în 8.0 h");
    expect(ago(null, now)).toBe("—");
  });
  it("sizes and countdowns", () => {
    expect(gb(2331)).toBe("2.3 TB");
    expect(mib(4112)).toBe("4.0 GB");
    expect(daysLeft(0)).toBe("azi");
    expect(daysLeft(-2)).toBe("depășit cu 2 z");
  });
});
