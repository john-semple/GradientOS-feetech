import { describe, expect, it, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SidebarDrawer } from "../components/SidebarDrawer";

describe("SidebarDrawer smoke test", () => {
  it("renders header content and children", () => {
    render(
      <SidebarDrawer onClose={() => {}} headerContent={<span>Test Panel</span>}>
        <div>Drawer body content</div>
      </SidebarDrawer>
    );
    expect(screen.getByText("Test Panel")).toBeInTheDocument();
    expect(screen.getByText("Drawer body content")).toBeInTheDocument();
    cleanup();
  });

  it("renders the close button with aria-label", () => {
    render(
      <SidebarDrawer onClose={() => {}} headerContent={<span>Test Panel</span>}>
        <div>body</div>
      </SidebarDrawer>
    );
    expect(screen.getByRole("button", { name: "Close drawer" })).toBeInTheDocument();
    cleanup();
  });

  it("fires onClose when the close button is clicked", async () => {
    const onClose = vi.fn();
    render(
      <SidebarDrawer onClose={onClose} headerContent={<span>Test Panel</span>}>
        <div>body</div>
      </SidebarDrawer>
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Close drawer" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    cleanup();
  });
});