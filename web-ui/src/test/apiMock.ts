import { vi } from "vitest";

/**
 * Fetch mock for component tests. Response shapes are derived from the real
 * FastAPI responses in src/gradient_os/api/main.py (mirroring the assertions in
 * tests/test_api_endpoints.py), so tests exercise the actual API contract.
 *
 * Usage:
 *   import { installFetchMock, readFetchLog } from "./apiMock";
 *   const { log } = installFetchMock();
 *   render(<ControlPanel apiHost="http://test" />);
 *   ... interact ...
 *   expect(log.calls[0]).toEqual({ method: "POST", path: "/control/home", body: undefined });
 */
export type FetchCall = {
  method: string;
  path: string;
  body?: unknown;
};

type MockOptions = {
  /** Override responses: { "/info/pose": { status: 200, json: {...} } } */
  responses?: Record<string, { status: number; json?: unknown; text?: string }>;
};

const DEFAULT_RESPONSES: Record<string, { status: number; json?: unknown }> = {
  "/control/stop": { status: 200, json: { detail: "ACK,STOP" } },
  "/control/home": { status: 200, json: { status: "ok" } },
  "/control/rest": { status: 200, json: { status: "ok" } },
  "/control/set-gripper": { status: 200, json: { status: "ok" } },
  "/control/move-line-relative": { status: 200, json: { status: "ok" } },
  "/control/rotate": { status: 200, json: { status: "ok" } },
  "/control/jog/start": { status: 200, json: { status: "ok" } },
  "/control/jog/stop": { status: 200, json: { status: "ok" } },
  "/control/jog/velocity": { status: 200, json: { status: "ok" } },
  "/control/jog/deadman": { status: 200, json: { status: "ok" } },
  "/control/jog/debug": { status: 200, json: { status: "ok" } },
  "/info/status": { status: 200, json: { gripper_present: true } },
  "/info/pose": {
    status: 200,
    json: {
      position_m: { x: 0.1, y: 0.2, z: 0.3 },
      orientation_euler_deg: { roll: 10.0, pitch: 20.0, yaw: 30.0 },
      joints_deg: [1, 2, 3, 4, 5, 6],
    },
  },
  "/info/joints": { status: 200, json: { arm_deg: [1, 2, 3, 4, 5, 6], gripper_deg: 7 } },
  "/info/gripper": { status: 200, json: { angle_deg: 45.0, raw_position: 2048 } },
  "/info/all-positions": {
    status: 200,
    json: {
      servos: [
        { servo_id: 10, raw_position: 2048 },
        { servo_id: 20, raw_position: 2050 },
        { servo_id: 21, raw_position: 2050 },
      ],
    },
  },
};

export function installFetchMock(options: MockOptions = {}): { log: { calls: FetchCall[] } } {
  const calls: FetchCall[] = [];
  const responses = { ...DEFAULT_RESPONSES, ...options.responses };

  const mock = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = (init?.method ?? "GET").toUpperCase();
    let body: unknown;
    if (init?.body) {
      try {
        body = JSON.parse(init.body as string);
      } catch {
        body = init.body;
      }
    }
    calls.push({ method, path, body });

    const key = `${method} ${path}`;
    const match =
      responses[`${key}`] ??
      responses[path] ??
      { status: 200, json: { status: "ok" } };
    return new Response(match.text ?? JSON.stringify(match.json ?? { status: "ok" }), {
      status: match.status,
      headers: { "Content-Type": "application/json" },
    });
  };

  vi.stubGlobal("fetch", mock);
  return { log: { calls } };
}