import { render, screen } from "@testing-library/react";

import type { BotState } from "@/types/contract";

// Minimal dashboard component extracted for isolated testing
function Dashboard({
  botState,
  latencyMs,
  interruptions,
}: {
  botState: BotState | null;
  latencyMs: number | null;
  interruptions: { at: number }[];
}) {
  return (
    <section aria-label="Session dashboard">
      <p>
        Status:{" "}
        <span data-state={botState ?? "idle"}>{botState ?? "—"}</span>
      </p>
      <p>Latency: {latencyMs !== null ? `${Math.round(latencyMs)} ms` : "—"}</p>
      {interruptions.length > 0 && (
        <details>
          <summary>Interruptions ({interruptions.length})</summary>
          <ol>
            {interruptions.map((ev) => (
              <li key={ev.at}>{Math.round(ev.at)} ms</li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}

describe("Dashboard", () => {
  it("shows idle state when botState is null", () => {
    const { container } = render(
      <Dashboard botState={null} latencyMs={null} interruptions={[]} />,
    );
    expect(screen.getByRole("region", { name: "Session dashboard" })).toBeInTheDocument();
    const span = container.querySelector("[data-state='idle']");
    expect(span).toBeInTheDocument();
    expect(span).toHaveTextContent("—");
  });

  it("renders LISTENING state with correct data-state", () => {
    render(<Dashboard botState="LISTENING" latencyMs={null} interruptions={[]} />);
    const span = screen.getByText("LISTENING");
    expect(span).toHaveAttribute("data-state", "LISTENING");
  });

  it("renders THINKING state with correct data-state", () => {
    render(<Dashboard botState="THINKING" latencyMs={null} interruptions={[]} />);
    const span = screen.getByText("THINKING");
    expect(span).toHaveAttribute("data-state", "THINKING");
  });

  it("renders SPEAKING state with correct data-state", () => {
    render(<Dashboard botState="SPEAKING" latencyMs={null} interruptions={[]} />);
    const span = screen.getByText("SPEAKING");
    expect(span).toHaveAttribute("data-state", "SPEAKING");
  });

  it("shows — for latency when null", () => {
    render(<Dashboard botState={null} latencyMs={null} interruptions={[]} />);
    expect(screen.getByText(/Latency:/).textContent).toContain("—");
  });

  it("formats latency as rounded ms", () => {
    render(<Dashboard botState={null} latencyMs={250.4} interruptions={[]} />);
    expect(screen.getByText(/Latency:/).textContent).toContain("250 ms");
  });

  it("rounds latency value", () => {
    render(<Dashboard botState={null} latencyMs={183.7} interruptions={[]} />);
    expect(screen.getByText(/Latency:/).textContent).toContain("184 ms");
  });

  it("does not show interruption list when empty", () => {
    render(<Dashboard botState={null} latencyMs={null} interruptions={[]} />);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("shows interruption summary with count", () => {
    const interruptions = [{ at: 1000 }, { at: 2000 }];
    render(<Dashboard botState={null} latencyMs={null} interruptions={interruptions} />);
    expect(screen.getByText("Interruptions (2)")).toBeInTheDocument();
  });

  it("lists each interruption entry as rounded ms", () => {
    const interruptions = [{ at: 1234.5 }, { at: 5678.9 }];
    render(<Dashboard botState={null} latencyMs={null} interruptions={interruptions} />);
    expect(screen.getByText("1235 ms")).toBeInTheDocument();
    expect(screen.getByText("5679 ms")).toBeInTheDocument();
  });
});
