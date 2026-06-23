import { render, screen } from "@testing-library/react";

import HomePage from "@/app/page";

let mockMutationError: Error | null;

jest.mock("../lib/daily", () => ({
  createDailyCall: jest.fn(),
  destroyDailyCall: jest.fn(),
}));

jest.mock("../hooks/useDataChannel", () => ({
  useDataChannel: () => ({
    botState: null,
    latencyMs: null,
    interruptions: [],
    sessionEndedReason: null,
  }),
}));

jest.mock("../lib/api", () => {
  class ApiError extends Error {
    public readonly fields: Record<string, string> | null;
    public readonly retryAfterSeconds: number | null;

    constructor(
      public readonly status: number,
      public readonly body: {
        fields?: Record<string, string>;
        retry_after_seconds?: number;
      },
      message: string,
    ) {
      super(message);
      this.name = "ApiError";
      this.fields = body.fields ?? null;
      this.retryAfterSeconds = body.retry_after_seconds ?? null;
    }
  }

  return {
    api: { post: jest.fn() },
    ApiError,
  };
});

jest.mock("@tanstack/react-query", () => ({
  useMutation: () => ({
    mutate: jest.fn(),
    reset: jest.fn(),
    isPending: false,
    error: mockMutationError,
  }),
}));

const { ApiError } = jest.requireMock("../lib/api") as {
  ApiError: new (
    status: number,
    body: {
      fields?: Record<string, string>;
      retry_after_seconds?: number;
    },
    message: string,
  ) => Error;
};

describe("HomePage API errors", () => {
  beforeEach(() => {
    mockMutationError = null;
  });

  it("renders backend field validation beside the production control", () => {
    mockMutationError = new ApiError(
      422,
      { fields: { max_tokens: "Must be less than or equal to 4096." } },
      "Request validation failed.",
    );

    render(<HomePage />);

    expect(screen.getByRole("spinbutton", { name: /max tokens/i })).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(
      screen.getByText("Must be less than or equal to 4096."),
    ).toBeInTheDocument();
  });

  it("renders the rate-limit retry delay", () => {
    mockMutationError = new ApiError(
      429,
      { retry_after_seconds: 12.2 },
      "Too many session requests.",
    );

    render(<HomePage />);

    expect(
      screen.getByText("Too many sessions. Try again in 13 seconds."),
    ).toBeInTheDocument();
  });

  it("renders a generic Daily join failure message", () => {
    mockMutationError = new Error("Unable to acquire microphone.");

    render(<HomePage />);

    expect(screen.getByText("Unable to acquire microphone.")).toBeInTheDocument();
  });
});
