export type SessionConfig = {
  system_prompt: string;
  temperature: number;
  max_tokens: number;
  stt_temperature: number;
  tts_voice_id: string;
  tts_speed: number;
  tts_temperature: number;
  interruptibility_pct: number;
};

export type SessionResponse = {
  roomUrl: string;
  token: string;
  sessionId: string;
};

export type BotState = "LISTENING" | "THINKING" | "SPEAKING";

export type StateEvent = { type: "state"; state: BotState; at: number };
export type LatencyEvent = { type: "latency"; ms: number; at: number };
export type InterruptionEvent = { type: "interruption"; at: number };
export type SessionEndedEvent = {
  type: "session_ended";
  reason: "inactivity";
  at: number;
};
export type DataChannelEvent =
  | StateEvent
  | LatencyEvent
  | InterruptionEvent
  | SessionEndedEvent;
