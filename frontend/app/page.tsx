"use client";

import { useState } from "react";

import type { DailyCall } from "@daily-co/daily-js";
import { useMutation } from "@tanstack/react-query";

import { useDataChannel } from "@/hooks/useDataChannel";
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
  const [call, setCall] = useState<DailyCall | null>(null);
  const [config, setConfig] = useState<SessionConfig>(defaultConfig);
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const { botState, latencyMs, interruptions } = useDataChannel(call);

  const sessionMutation = useMutation({
    mutationFn: (cfg: SessionConfig) => api.post<SessionResponse>("/session", cfg),
    onSuccess: async (session) => {
      const newCall = createDailyCall();
      try {
        await newCall.join({ url: session.roomUrl, token: session.token });
        setCall(newCall);
        setConnected(true);
        setSessionId(session.sessionId);
      } catch (err) {
        await destroyDailyCall(newCall);
        throw err;
      }
    },
  });

  const disconnect = async (): Promise<void> => {
    sessionMutation.reset();
    if (call) {
      await destroyDailyCall(call);
      setCall(null);
    }
    setConnected(false);
    setSessionId("");
  };

  const setNum = (field: keyof SessionConfig, value: string): void => {
    setConfig((c) => ({ ...c, [field]: Number(value) }));
  };

  const busy = sessionMutation.isPending;
  const error =
    sessionMutation.error instanceof Error
      ? sessionMutation.error.message
      : sessionMutation.error
        ? "Unable to join the Daily room."
        : null;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Freya</h1>
        <p>Interruptible voice agent</p>
        {connected && (
          <span className="status-badge" role="status">
            Live{sessionId ? ` · ${sessionId.slice(0, 8)}` : ""}
          </span>
        )}
      </header>

      <div className="panels">
        {/* ── LEFT: Config ── */}
        <aside className="panel-config">
          <div className="field">
            <span className="field-label">System prompt</span>
            <textarea
              required
              maxLength={4000}
              rows={5}
              disabled={connected || busy}
              value={config.system_prompt}
              onChange={(e) =>
                setConfig((c) => ({ ...c, system_prompt: e.target.value }))
              }
            />
          </div>

          <div className="field-grid-2">
            <div className="field">
              <span className="field-label">LLM temperature</span>
              <input
                type="number"
                min="0"
                max="2"
                step="0.1"
                disabled={connected || busy}
                value={config.temperature}
                onChange={(e) => setNum("temperature", e.target.value)}
              />
            </div>
            <div className="field">
              <span className="field-label">Max tokens</span>
              <input
                type="number"
                min="1"
                max="4096"
                disabled={connected || busy}
                value={config.max_tokens}
                onChange={(e) => setNum("max_tokens", e.target.value)}
              />
            </div>
            <div className="field">
              <span className="field-label">STT temperature</span>
              <input
                type="number"
                min="0"
                max="1"
                step="0.1"
                disabled={connected || busy}
                value={config.stt_temperature}
                onChange={(e) => setNum("stt_temperature", e.target.value)}
              />
            </div>
            <div className="field">
              <span className="field-label">TTS temperature</span>
              <input
                type="number"
                min="0"
                max="1"
                step="0.1"
                disabled={connected || busy}
                value={config.tts_temperature}
                onChange={(e) => setNum("tts_temperature", e.target.value)}
              />
            </div>
            <div className="field">
              <span className="field-label">Voice ID</span>
              <input
                required
                disabled={connected || busy}
                value={config.tts_voice_id}
                onChange={(e) =>
                  setConfig((c) => ({ ...c, tts_voice_id: e.target.value }))
                }
              />
            </div>
            <div className="field">
              <span className="field-label">Voice speed</span>
              <input
                type="number"
                min="0.6"
                max="1.5"
                step="0.1"
                disabled={connected || busy}
                value={config.tts_speed}
                onChange={(e) => setNum("tts_speed", e.target.value)}
              />
            </div>
          </div>

          <div className="field">
            <span className="field-label">
              Interruptibility: {config.interruptibility_pct}%
            </span>
            <input
              type="range"
              min="0"
              max="100"
              disabled={connected || busy}
              value={config.interruptibility_pct}
              onChange={(e) => setNum("interruptibility_pct", e.target.value)}
            />
          </div>

          {error && (
            <p className="error-msg" role="alert">
              {error}
            </p>
          )}

          {!connected && (
            <button
              className="btn-primary"
              disabled={busy}
              onClick={() => sessionMutation.mutate(config)}
            >
              {busy ? "Connecting…" : "Start session"}
            </button>
          )}
        </aside>

        {/* ── RIGHT: Session ── */}
        <main className="panel-session">
          {!connected ? (
            <p className="session-idle">
              Configure the agent on the left, then start a session.
            </p>
          ) : (
            <>
              <div
                className="state-pill"
                data-state={botState ?? "idle"}
                aria-live="polite"
                aria-label={`Bot state: ${botState ?? "idle"}`}
              >
                {botState ?? "—"}
              </div>

              <div className="metric-block">
                <p className="metric-label">Round-trip latency</p>
                <p className="metric-value">
                  {latencyMs !== null ? (
                    <>
                      {Math.round(latencyMs)}
                      <span>ms</span>
                    </>
                  ) : (
                    "—"
                  )}
                </p>
                <p className="metric-hint">user silence → first bot audio</p>
              </div>

              {interruptions.length > 0 && (
                <div className="interruption-block">
                  <div className="interruption-header">
                    <span>Interruptions</span>
                    <span>{interruptions.length}</span>
                  </div>
                  <ol className="interruption-list">
                    {interruptions.map((ev) => (
                      <li key={ev.at} className="interruption-item">
                        {Math.round(ev.at)} ms into session
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              <button
                className="btn-disconnect"
                onClick={() => void disconnect()}
              >
                Disconnect
              </button>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
