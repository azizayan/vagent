"use client";

import { useRef, useState } from "react";

import type { DailyCall } from "@daily-co/daily-js";

import { api } from "@/lib/api";
import { createDailyCall, destroyDailyCall } from "@/lib/daily";
import type { SessionConfig, SessionResponse } from "@/types/contract";

const defaultConfig: SessionConfig = {
  system_prompt: "You are a helpful, concise voice assistant. Keep replies under three sentences.",
  temperature: 0.7,
  max_tokens: 160,
  stt_temperature: 0,
  tts_voice_id: "71a7ad14-091c-4e8e-a314-022ece01c121",
  tts_speed: 1,
  tts_temperature: 0.7,
  interruptibility_pct: 50,
};

export default function HomePage() {
  const callRef = useRef<DailyCall | null>(null);
  const [config, setConfig] = useState<SessionConfig>(defaultConfig);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [error, setError] = useState("");

  const toggleConnection = async (): Promise<void> => {
    setError("");

    try {
      if (callRef.current) {
        await destroyDailyCall(callRef.current);
        callRef.current = null;
        setConnected(false);
        setSessionId("");
        return;
      }

      setConnecting(true);
      const session = await api.post<SessionResponse>("/session", config);
      const call = createDailyCall();
      callRef.current = call;
      await call.join({ url: session.roomUrl, token: session.token });
      setConnected(true);
      setSessionId(session.sessionId);
    } catch (cause) {
      if (callRef.current) {
        await destroyDailyCall(callRef.current);
        callRef.current = null;
      }
      setConnected(false);
      setError(cause instanceof Error ? cause.message : "Unable to join the Daily room.");
    } finally {
      setConnecting(false);
    }
  };

  const setNumber = (field: keyof SessionConfig, value: string): void => {
    setConfig((current) => ({ ...current, [field]: Number(value) }));
  };

  return (
    <main>
      <h1>Freya voice bot</h1>
      <p>Configure a private voice session, then connect through Daily.</p>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void toggleConnection();
        }}
      >
        <label>
          System prompt
          <textarea
            required
            maxLength={4000}
            rows={5}
            disabled={connected || connecting}
            value={config.system_prompt}
            onChange={(event) =>
              setConfig((current) => ({ ...current, system_prompt: event.target.value }))
            }
          />
        </label>

        <div className="field-grid">
          <label>
            LLM temperature
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              disabled={connected || connecting}
              value={config.temperature}
              onChange={(event) => setNumber("temperature", event.target.value)}
            />
          </label>
          <label>
            Max tokens
            <input
              type="number"
              min="1"
              max="4096"
              disabled={connected || connecting}
              value={config.max_tokens}
              onChange={(event) => setNumber("max_tokens", event.target.value)}
            />
          </label>
          <label>
            Voice ID
            <input
              required
              disabled={connected || connecting}
              value={config.tts_voice_id}
              onChange={(event) =>
                setConfig((current) => ({ ...current, tts_voice_id: event.target.value }))
              }
            />
          </label>
          <label>
            Voice speed
            <input
              type="number"
              min="0.6"
              max="1.5"
              step="0.1"
              disabled={connected || connecting}
              value={config.tts_speed}
              onChange={(event) => setNumber("tts_speed", event.target.value)}
            />
          </label>
        </div>

        <label>
          Interruptibility: {config.interruptibility_pct}%
          <input
            type="range"
            min="0"
            max="100"
            disabled={connected || connecting}
            value={config.interruptibility_pct}
            onChange={(event) => setNumber("interruptibility_pct", event.target.value)}
          />
        </label>

        <button type="submit" disabled={connecting}>
          {connecting ? "Connecting…" : connected ? "Disconnect" : "Start session"}
        </button>
      </form>

      {connected ? (
        <p role="status">
          Connected
          {sessionId ? ` · Session ${sessionId.slice(0, 8)}` : ""}
        </p>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </main>
  );
}
