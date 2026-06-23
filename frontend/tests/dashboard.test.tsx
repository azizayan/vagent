import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import HomePage from "@/app/page";
import type { DataChannelState } from "@/hooks/useDataChannel";

const mockCall = {
  join: jest.fn().mockResolvedValue(undefined),
  leave: jest.fn().mockResolvedValue(undefined),
  destroy: jest.fn(),
};
let mockDataState: DataChannelState;

jest.mock("../lib/daily", () => ({
  createDailyCall: () => mockCall,
  destroyDailyCall: jest.fn().mockResolvedValue(undefined),
}));

jest.mock("../hooks/useDataChannel", () => ({
  useDataChannel: () => mockDataState,
}));

jest.mock("../lib/api", () => {
  class ApiError extends Error {
    public readonly fields: Record<string, string> | null = null;
    public readonly retryAfterSeconds: number | null = null;

    constructor(
      public readonly status: number,
      public readonly body: unknown,
      message: string,
    ) {
      super(message);
      this.name = "ApiError";
    }
  }

  return {
    api: { post: jest.fn() },
    ApiError,
  };
});

jest.mock("@tanstack/react-query", () => ({
  useMutation: (options: {
    onSuccess: (session: {
      roomUrl: string;
      token: string;
      sessionId: string;
    }) => Promise<void>;
  }) => ({
    mutate: () =>
      void options.onSuccess({
        roomUrl: "https://test.daily.co/room",
        token: "token",
        sessionId: "session-1",
      }),
    reset: jest.fn(),
    isPending: false,
    error: null,
  }),
}));

async function renderConnectedDashboard(state: DataChannelState) {
  mockDataState = state;
  const user = userEvent.setup();
  render(<HomePage />);
  await user.click(screen.getByRole("button", { name: "Start session" }));
  await screen.findByText(/^Live/);
}

describe("HomePage session dashboard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDataState = {
      botState: null,
      latencyMs: null,
      interruptions: [],
      sessionEndedReason: null,
    };
  });

  it.each(["LISTENING", "THINKING", "SPEAKING"] as const)(
    "renders the %s state from the production dashboard",
    async (botState) => {
      await renderConnectedDashboard({
        ...mockDataState,
        botState,
      });

      expect(screen.getByLabelText(`Bot state: ${botState}`)).toHaveAttribute(
        "data-state",
        botState,
      );
    },
  );

  it("renders the idle dashboard state before the first event", async () => {
    await renderConnectedDashboard(mockDataState);

    expect(screen.getByLabelText("Bot state: idle")).toHaveAttribute(
      "data-state",
      "idle",
    );
    expect(screen.getByText("Round-trip latency").parentElement).toHaveTextContent("—");
  });

  it("rounds latency and renders interruption entries", async () => {
    await renderConnectedDashboard({
      botState: "LISTENING",
      latencyMs: 183.7,
      interruptions: [{ at: 1234.5 }, { at: 5678.9 }],
      sessionEndedReason: null,
    });

    expect(screen.getByText("184").parentElement).toHaveTextContent("184ms");
    expect(screen.getByText("Interruptions").parentElement).toHaveTextContent(
      "Interruptions2",
    );
    expect(screen.getByText("1235 ms into session")).toBeInTheDocument();
    expect(screen.getByText("5679 ms into session")).toBeInTheDocument();
  });

  it("does not render an interruption list when there are no events", async () => {
    await renderConnectedDashboard({
      ...mockDataState,
      botState: "LISTENING",
    });

    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
