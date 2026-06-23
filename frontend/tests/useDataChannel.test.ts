import { reducer } from "@/hooks/useDataChannel";
import type { DataChannelState } from "@/hooks/useDataChannel";
import type { DataChannelEvent } from "@/types/contract";

const initial: DataChannelState = {
  botState: null,
  latencyMs: null,
  interruptions: [],
  sessionEndedReason: null,
};

describe("useDataChannel reducer", () => {
  it("updates botState on state events", () => {
    const s1 = reducer(initial, { type: "state", state: "THINKING", at: 100 });
    expect(s1.botState).toBe("THINKING");

    const s2 = reducer(s1, { type: "state", state: "SPEAKING", at: 200 });
    expect(s2.botState).toBe("SPEAKING");

    const s3 = reducer(s2, { type: "state", state: "LISTENING", at: 300 });
    expect(s3.botState).toBe("LISTENING");
  });

  it("updates latencyMs on latency event", () => {
    const s = reducer(initial, { type: "latency", ms: 250, at: 200 });
    expect(s.latencyMs).toBe(250);
  });

  it("replaces latencyMs on subsequent latency events", () => {
    const s1 = reducer(initial, { type: "latency", ms: 100, at: 100 });
    const s2 = reducer(s1, { type: "latency", ms: 180, at: 500 });
    expect(s2.latencyMs).toBe(180);
  });

  it("appends interruptions and preserves previous ones", () => {
    const s1 = reducer(initial, { type: "interruption", at: 1000 });
    expect(s1.interruptions).toHaveLength(1);

    const s2 = reducer(s1, { type: "interruption", at: 2000 });
    expect(s2.interruptions).toHaveLength(2);

    const s3 = reducer(s2, { type: "interruption", at: 3000 });
    expect(s3.interruptions).toHaveLength(3);
    expect(s3.interruptions[2]).toEqual({ at: 3000 });
  });

  it("does not mutate state — returns new objects", () => {
    const s1 = reducer(initial, { type: "interruption", at: 1 });
    expect(s1).not.toBe(initial);
    expect(s1.interruptions).not.toBe(initial.interruptions);
  });

  it("preserves unrelated fields when updating botState", () => {
    const withLatency = reducer(initial, { type: "latency", ms: 120, at: 100 });
    const withState = reducer(withLatency, { type: "state", state: "SPEAKING", at: 200 });
    expect(withState.latencyMs).toBe(120);
  });

  it("records inactivity session end events", () => {
    const state = reducer(initial, {
      type: "session_ended",
      reason: "inactivity",
      at: 300_000,
    });

    expect(state.sessionEndedReason).toBe("inactivity");
  });

  it("handles a full conversation sequence", () => {
    const events: DataChannelEvent[] = [
      { type: "state", state: "THINKING", at: 100 },
      { type: "state", state: "SPEAKING", at: 300 },
      { type: "latency", ms: 200, at: 300 },
      { type: "state", state: "LISTENING", at: 800 },
      { type: "state", state: "THINKING", at: 1200 },
      { type: "interruption", at: 1400 },
      { type: "state", state: "LISTENING", at: 1400 },
    ];

    const final = events.reduce(reducer, initial);
    expect(final.botState).toBe("LISTENING");
    expect(final.latencyMs).toBe(200);
    expect(final.interruptions).toHaveLength(1);
  });
});
