"use client";

import { useCallback, useState } from "react";

import type { DailyCall } from "@daily-co/daily-js";
import { useMutation } from "@tanstack/react-query";

import {
  CUSTOM_VOICE_VALUE,
  DEFAULT_CARTESIA_VOICE,
  VoicePicker,
} from "@/components/config/VoicePicker";
import { useDataChannel } from "@/hooks/useDataChannel";
import { api } from "@/lib/api";
import { createDailyCall, destroyDailyCall } from "@/lib/daily";
import { DEFAULT_SYSTEM_PROMPT } from "@/lib/defaults";
import type { SessionConfig, SessionResponse } from "@/types/contract";

const defaultConfig: SessionConfig = {
  system_prompt: DEFAULT_SYSTEM_PROMPT,
  temperature: 0.7,
  max_tokens: 160,
  stt_temperature: 0,
  tts_voice_id: DEFAULT_CARTESIA_VOICE.id,
  tts_speed: 1,
  tts_temperature: 0.7,
  interruptibility_pct: 50,
};

export default function HomePage() {
  const [call, setCall] = useState<DailyCall | null>(null);
  const [config, setConfig] = useState<SessionConfig>(defaultConfig);
  const [selectedVoice, setSelectedVoice] = useState(defaultConfig.tts_voice_id);
  const [customVoiceName, setCustomVoiceName] = useState("");
  const [customVoiceId, setCustomVoiceId] = useState("");
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [inactivityNotice, setInactivityNotice] = useState(false);
  const handleSessionEnded = useCallback(
    (reason: "inactivity", endedCall: DailyCall) => {
      if (reason !== "inactivity") {
        return;
      }

      setInactivityNotice(true);
      setConnected(false);
      setSessionId("");
      void destroyDailyCall(endedCall).finally(() => {
        setCall((current) => (current === endedCall ? null : current));
      });
    },
    [],
  );
  const { botState, latencyMs, interruptions } = useDataChannel(
    call,
    handleSessionEnded,
  );

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
  const customVoiceIncomplete =
    selectedVoice === CUSTOM_VOICE_VALUE &&
    (!customVoiceName.trim() || !customVoiceId.trim());
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
              className="system-prompt-input"
              required
              maxLength={4000}
              rows={11}
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

          <VoicePicker
            disabled={connected || busy}
            selectedVoice={selectedVoice}
            customName={customVoiceName}
            customVoiceId={customVoiceId}
            onSelectedVoiceChange={(value) => {
              setSelectedVoice(value);
              setConfig((current) => ({
                ...current,
                tts_voice_id:
                  value === CUSTOM_VOICE_VALUE ? customVoiceId : value,
              }));
            }}
            onCustomNameChange={setCustomVoiceName}
            onCustomVoiceIdChange={(value) => {
              setCustomVoiceId(value);
              setConfig((current) => ({ ...current, tts_voice_id: value }));
            }}
          />

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
              disabled={busy || customVoiceIncomplete}
              onClick={() => {
                setInactivityNotice(false);
                sessionMutation.mutate(config);
              }}
            >
              {busy ? "Connecting…" : "Start session"}
            </button>
          )}
        </aside>

        {/* ── RIGHT: Session ── */}
        <main className="panel-session">
          {!connected ? (
            inactivityNotice ? (
              <p className="session-idle" role="status">
                Session ended due to inactivity.
              </p>
            ) : (
              <p className="session-idle">
                Configure the agent on the left, then start a session.
              </p>
            )
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
