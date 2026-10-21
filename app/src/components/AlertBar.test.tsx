import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AlertBar } from "./AlertBar";
import type { Alert } from "../types";

const mk = (n: number, severity: Alert["severity"]): Alert[] =>
  Array.from({ length: n }, (_, i) => ({ id: `${severity}${i}`, severity, text: `${severity} ${i}`, source: "t" }));

describe("AlertBar", () => {
  it("shows calm state when nothing is red or yellow", () => {
    render(<AlertBar alerts={mk(2, "info")} connected generated="2026-09-23T13:00:00" />);
    expect(screen.getByText("Nicio alertă. Totul rulează.")).toBeTruthy();
    expect(screen.getByText("2 note")).toBeTruthy();
  });
  it("caps chips and shows the overflow count", () => {
    render(<AlertBar alerts={[...mk(5, "red"), ...mk(4, "yellow")]} connected />);
    expect(screen.getAllByText(/^(red|yellow) \d$/)).toHaveLength(6);
    expect(screen.getByText("+3")).toBeTruthy();
  });
  it("flags a lost backend", () => {
    render(<AlertBar alerts={[]} connected={false} />);
    expect(screen.getByText(/backend deconectat/)).toBeTruthy();
  });
});
