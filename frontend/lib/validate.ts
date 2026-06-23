import type { SessionConfig } from "@/types/contract";

export type FieldErrors = Partial<Record<keyof SessionConfig, string>>;

/**
 * Mirror of the backend's Pydantic constraints in `app/schemas/config.py`.
 * Backend remains the source of truth; this is a UX layer so the user gets
 * immediate feedback before the request round-trip.
 */
export function validateSessionConfig(config: SessionConfig): FieldErrors {
  const errors: FieldErrors = {};

  if (config.system_prompt.length > 4000) {
    errors.system_prompt = "Must be 4000 characters or fewer.";
  }
  if (/(?:^|\n)\s*(system|assistant|user|developer)\s*:/i.test(config.system_prompt)) {
    errors.system_prompt =
      "Cannot contain role markers (system:/assistant:/user:/developer:).";
  }

  if (!inRange(config.temperature, 0, 2)) {
    errors.temperature = "LLM temperature must be between 0 and 2.";
  }
  if (!Number.isInteger(config.max_tokens) || !inRange(config.max_tokens, 1, 4096)) {
    errors.max_tokens = "Max tokens must be a whole number between 1 and 4096.";
  }
  if (!inRange(config.stt_temperature, 0, 1)) {
    errors.stt_temperature = "STT temperature must be between 0 and 1.";
  }
  if (config.tts_voice_id.trim().length === 0) {
    errors.tts_voice_id = "A Cartesia voice ID is required.";
  }
  if (!inRange(config.tts_speed, 0.6, 1.5)) {
    errors.tts_speed = "Voice speed must be between 0.6 and 1.5.";
  }
  if (!inRange(config.tts_temperature, 0, 1)) {
    errors.tts_temperature = "TTS temperature must be between 0 and 1.";
  }
  if (
    !Number.isInteger(config.interruptibility_pct) ||
    !inRange(config.interruptibility_pct, 0, 100)
  ) {
    errors.interruptibility_pct =
      "Interruptibility must be a whole number between 0 and 100.";
  }

  return errors;
}

function inRange(value: number, min: number, max: number): boolean {
  return Number.isFinite(value) && value >= min && value <= max;
}
