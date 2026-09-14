import "@testing-library/jest-dom/vitest";

// jsdom does not implement ResizeObserver; TelemetryCharts instantiates one on
// mount (src/TelemetryCharts.tsx:273) and crashes without this polyfill.
class ResizeObserverPolyfill {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (typeof globalThis.ResizeObserver !== "function") {
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserverPolyfill }).ResizeObserver =
    ResizeObserverPolyfill;
}