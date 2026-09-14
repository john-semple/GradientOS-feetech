import { describe, expect, it } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { TelemetryCharts, type TelemetryEvent } from "../TelemetryCharts";

describe("TelemetryCharts smoke test", () => {
  it("renders with null telemetry (no data)", () => {
    render(<TelemetryCharts latest={null} />);
    // No crash on mount is the primary assertion (ResizeObserver polyfill active)
    cleanup();
  });

  it("renders servo telemetry charts with sample data", () => {
    const sample: TelemetryEvent = {
      timestamp: Date.now(),
      joints: [1, 2, 3, 4, 5, 6],
      servos: {
        "10": { voltage_v: 12.1, temp_c: 42.0, current_a: 0.31 },
        "20": { voltage_v: 12.0, temp_c: 45.5, current_a: 0.29 },
      },
    };
    render(<TelemetryCharts latest={sample} />);
    // Chart section titles render for both joint and servo charts.
    // (Servo ids appear only in hover tooltips, so assert on the section titles.)
    expect(screen.getByText("J1 (deg)")).toBeInTheDocument();
    expect(screen.getByText("Voltage (V)")).toBeInTheDocument();
    expect(screen.getByText("Current (A)")).toBeInTheDocument();
    expect(screen.getByText("Temp (°C)")).toBeInTheDocument();
    cleanup();
  });
});