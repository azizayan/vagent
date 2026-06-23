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
