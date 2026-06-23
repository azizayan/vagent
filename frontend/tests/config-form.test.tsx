import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  CARTESIA_VOICES,
  CUSTOM_VOICE_VALUE,
  DEFAULT_CARTESIA_VOICE,
  VoicePicker,
} from "@/components/config/VoicePicker";

// Minimal form component matching the shape in page.tsx for isolated testing
function ConfigForm({
  onSubmit,
}: {
  onSubmit: (systemPrompt: string, interruptibilityPct: number) => void;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        onSubmit(
          fd.get("system_prompt") as string,
          Number(fd.get("interruptibility_pct")),
        );
      }}
    >
      <label>
        System prompt
        <textarea name="system_prompt" required maxLength={4000} rows={5} defaultValue="" />
      </label>

      <label>
        Voice ID
        <input name="tts_voice_id" required defaultValue="" />
      </label>

      <label>
        Interruptibility
        <input
          name="interruptibility_pct"
          type="range"
          min="0"
          max="100"
          defaultValue="50"
        />
      </label>

      <label>
        LLM temperature
        <input name="temperature" type="number" min="0" max="2" step="0.1" defaultValue="0.7" />
      </label>

      <label>
        Max tokens
        <input name="max_tokens" type="number" min="1" max="4096" defaultValue="160" />
      </label>

      <button type="submit">Start session</button>
    </form>
  );
}

describe("Config form", () => {
  it("renders the system prompt textarea", () => {
    render(<ConfigForm onSubmit={() => undefined} />);
    expect(screen.getByRole("textbox", { name: /system prompt/i })).toBeInTheDocument();
  });

  it("system prompt textarea has required attribute", () => {
    render(<ConfigForm onSubmit={() => undefined} />);
    expect(screen.getByRole("textbox", { name: /system prompt/i })).toBeRequired();
  });

  it("system prompt textarea has maxLength 4000", () => {
    render(<ConfigForm onSubmit={() => undefined} />);
    const ta = screen.getByRole("textbox", { name: /system prompt/i });
    expect(ta).toHaveAttribute("maxlength", "4000");
  });

  it("voice ID field is required", () => {
    render(<ConfigForm onSubmit={() => undefined} />);
    expect(screen.getByRole("textbox", { name: /voice id/i })).toBeRequired();
  });

  it("interruptibility slider has min=0 and max=100", () => {
    render(<ConfigForm onSubmit={() => undefined} />);
    const slider = screen.getByRole("slider", { name: /interruptibility/i });
    expect(slider).toHaveAttribute("min", "0");
    expect(slider).toHaveAttribute("max", "100");
  });

  it("LLM temperature input has min=0 and max=2", () => {
    render(<ConfigForm onSubmit={() => undefined} />);
    const input = screen.getByRole("spinbutton", { name: /llm temperature/i });
    expect(input).toHaveAttribute("min", "0");
    expect(input).toHaveAttribute("max", "2");
  });

  it("max tokens input has min=1 and max=4096", () => {
    render(<ConfigForm onSubmit={() => undefined} />);
    const input = screen.getByRole("spinbutton", { name: /max tokens/i });
    expect(input).toHaveAttribute("min", "1");
    expect(input).toHaveAttribute("max", "4096");
  });

  it("system prompt textarea value round-trips through onChange", async () => {
    const user = userEvent.setup();
    render(<ConfigForm onSubmit={() => undefined} />);
    const ta = screen.getByRole("textbox", { name: /system prompt/i });
    await user.type(ta, "Hello, world!");
    expect(ta).toHaveValue("Hello, world!");
  });
});

describe("Voice picker", () => {
  it("lists the provided Cartesia voices and their roles", () => {
    render(
      <VoicePicker
        disabled={false}
        selectedVoice={DEFAULT_CARTESIA_VOICE.id}
        customName=""
        customVoiceId=""
        onSelectedVoiceChange={() => undefined}
        onCustomNameChange={() => undefined}
        onCustomVoiceIdChange={() => undefined}
      />,
    );

    expect(screen.getByRole("option", { name: "Skylar — Friendly Guide" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Corey — Supportive Buddy" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Ella — Caring Scout" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Jacqueline — Reassuring Agent" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Cathy — Coworker" })).toBeInTheDocument();
  });

  it("shows required name and ID fields for a custom voice", () => {
    render(
      <VoicePicker
        disabled={false}
        selectedVoice={CUSTOM_VOICE_VALUE}
        customName=""
        customVoiceId=""
        onSelectedVoiceChange={() => undefined}
        onCustomNameChange={() => undefined}
        onCustomVoiceIdChange={() => undefined}
      />,
    );

    expect(screen.getByRole("textbox", { name: /voice name/i })).toBeRequired();
    expect(screen.getByRole("textbox", { name: /cartesia voice id/i })).toBeRequired();
  });

  it("passes the selected preset ID to the parent", async () => {
    const user = userEvent.setup();
    const onSelectedVoiceChange = jest.fn();
    render(
      <VoicePicker
        disabled={false}
        selectedVoice={DEFAULT_CARTESIA_VOICE.id}
        customName=""
        customVoiceId=""
        onSelectedVoiceChange={onSelectedVoiceChange}
        onCustomNameChange={() => undefined}
        onCustomVoiceIdChange={() => undefined}
      />,
    );

    await user.selectOptions(
      screen.getByRole("combobox", { name: /voice/i }),
      CARTESIA_VOICES[1]!.id,
    );
    expect(onSelectedVoiceChange).toHaveBeenCalledWith(CARTESIA_VOICES[1]!.id);
  });
});
