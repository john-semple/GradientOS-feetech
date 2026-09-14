import { describe, expect, it, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { installFetchMock } from "./apiMock";
import { ControlPanel } from "../ControlPanel";

describe("ControlPanel smoke test", () => {
  it("renders the control panel with jog buttons and STOP action", () => {
    installFetchMock();
    render(<ControlPanel apiHost="http://test" />);
    expect(screen.getByText("Robot Control")).toBeInTheDocument();
    expect(screen.getAllByText("+X").length).toBeGreaterThan(0);
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Rest")).toBeInTheDocument();
    // STOP is the rose-colored emergency action button
    expect(screen.getByText("STOP")).toBeInTheDocument();
    cleanup();
  });

  it("calls the home endpoint when the Home button is clicked", async () => {
    const { log } = installFetchMock();
    render(<ControlPanel apiHost="http://test" />);
    const user = userEvent.setup();
    await user.click(screen.getByText("Home"));
    const homeCall = log.calls.find((c) => c.path === "/control/home");
    expect(homeCall).toBeDefined();
    expect(homeCall?.method).toBe("POST");
    cleanup();
  });

  it("renders gripper slider and speed multiplier controls", () => {
    installFetchMock();
    render(<ControlPanel apiHost="http://test" />);
    // Two sliders: gripper angle (0..180) and speed multiplier
    const sliders = screen.getAllByRole("slider");
    expect(sliders.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/speed multiplier/i)).toBeInTheDocument();
    cleanup();
  });
});