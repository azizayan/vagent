import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import HomePage from "@/app/page";
import type { DataChannelState } from "@/hooks/useDataChannel";

const mockCall = {
  join: jest.fn().mockResolvedValue(undefined),
  leave: jest.fn().mockResolvedValue(undefined),
  destroy: jest.fn(),
};
const mockCreateDailyCall = jest.fn(() => mockCall);
const mockDestroyDailyCall = jest.fn().mockResolvedValue(undefined);
const mockUseDataChannel = jest.fn();
let mockOnSessionEnded:
  | ((reason: "inactivity", endedCall: typeof mockCall) => void)
  | undefined;
let mockDataState: DataChannelState = {
  botState: null,
  latencyMs: null,
  interruptions: [],
  sessionEndedReason: null as "inactivity" | null,
};

jest.mock("../lib/daily", () => ({
  createDailyCall: () => mockCreateDailyCall(),
  destroyDailyCall: (call: unknown) => mockDestroyDailyCall(call),
}));

jest.mock("../hooks/useDataChannel", () => ({
  useDataChannel: (
    call: unknown,
    onSessionEnded: typeof mockOnSessionEnded,
  ) => {
    mockOnSessionEnded = onSessionEnded;
    return mockUseDataChannel(call);
  },
}));

jest.mock("../lib/api", () => ({
  api: { post: jest.fn() },
}));

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

describe("session inactivity handling", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDataState = {
      botState: null,
      latencyMs: null,
      interruptions: [],
      sessionEndedReason: null,
    };
    mockUseDataChannel.mockImplementation(() => mockDataState);
    mockOnSessionEnded = undefined;
  });

  it("destroys the call, resets the dashboard, and shows a persistent notice", async () => {
    const user = userEvent.setup();
    render(<HomePage />);

    await user.click(screen.getByRole("button", { name: "Start session" }));
    expect(await screen.findByText(/^Live/)).toBeInTheDocument();

    act(() => {
      mockOnSessionEnded?.("inactivity", mockCall);
    });

    expect(
      await screen.findByText("Session ended due to inactivity."),
    ).toBeInTheDocument();
    await waitFor(() => expect(mockDestroyDailyCall).toHaveBeenCalledWith(mockCall));
    await waitFor(() => {
      expect(mockUseDataChannel).toHaveBeenLastCalledWith(null);
    });
    expect(screen.queryByLabelText(/Bot state:/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start session" })).toBeEnabled();
  });

  it("clears the old inactivity notice when starting a new session", async () => {
    const user = userEvent.setup();
    render(<HomePage />);

    await user.click(screen.getByRole("button", { name: "Start session" }));
    await screen.findByText(/^Live/);

    act(() => {
      mockOnSessionEnded?.("inactivity", mockCall);
    });
    await screen.findByText("Session ended due to inactivity.");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Start session" }));
    });

    expect(
      screen.queryByText("Session ended due to inactivity."),
    ).not.toBeInTheDocument();
  });
});
