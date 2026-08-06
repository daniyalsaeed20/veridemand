import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeSnapshot } from "../../tests/testUtils";
import { SessionStatusBar } from "./SessionStatusBar";

function renderBar(props: Partial<Parameters<typeof SessionStatusBar>[0]> = {}) {
  const onReset = props.onReset ?? vi.fn();
  render(
    <SessionStatusBar
      snapshot={props.snapshot ?? makeSnapshot()}
      connected={props.connected ?? true}
      reconnecting={props.reconnecting ?? false}
      isResetting={props.isResetting ?? false}
      onReset={onReset}
    />,
  );
  return { onReset };
}

describe("SessionStatusBar", () => {
  it("shows the live connection indicator when connected", () => {
    renderBar({ connected: true });
    expect(screen.getByText("Session active")).toBeInTheDocument();
  });

  it("shows a reconnecting indicator when the stream drops", () => {
    renderBar({ connected: false, reconnecting: true });
    expect(screen.getByText("Reconnecting...")).toBeInTheDocument();
  });

  it("shows a remaining-time chip", () => {
    renderBar();
    expect(screen.getByText(/Expires in/)).toBeInTheDocument();
  });

  it("warns when the session is expiring", () => {
    renderBar({ snapshot: makeSnapshot({ expiring: true }) });
    expect(screen.getByText(/about to expire/i)).toBeInTheDocument();
  });

  it("confirms before resetting", () => {
    const { onReset } = renderBar();
    fireEvent.click(screen.getByRole("button", { name: /reset session/i }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: /reset session/i }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("does not reset when the confirmation is cancelled", () => {
    const { onReset } = renderBar();
    fireEvent.click(screen.getByRole("button", { name: /reset session/i }));

    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(onReset).not.toHaveBeenCalled();
  });
});
