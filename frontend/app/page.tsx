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
import { ApiError, api } from "@/lib/api";
import { createDailyCall, destroyDailyCall } from "@/lib/daily";
import { DEFAULT_SYSTEM_PROMPT } from "@/lib/defaults";
import { type FieldErrors, validateSessionConfig } from "@/lib/validate";
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

const interruptibilityLabel = (percentage: number): string => {
  if (percentage === 0) return "Disabled";
  if (percentage <= 30) return "Conservative";
  if (percentage <= 50) return "Balanced";
  if (percentage <= 75) return "Responsive";
  return "Immediate";
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

  const [clientErrors, setClientErrors] = useState<FieldErrors>({});

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

  const serverFieldErrors: FieldErrors = (() => {
    const out: FieldErrors = {};
    if (sessionMutation.error instanceof ApiError && sessionMutation.error.fields) {
      for (const [path, msg] of Object.entries(sessionMutation.error.fields)) {
        const last = path.split(".").pop() ?? path;
        if (last in defaultConfig) {
          out[last as keyof SessionConfig] = msg;
        }
      }
    }
    return out;
  })();

  const fieldErrors: FieldErrors = { ...serverFieldErrors, ...clientErrors };

  const handleStart = (): void => {
    setInactivityNotice(false);
    const errors = validateSessionConfig(config);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }
    sessionMutation.mutate(config);
  };

  const fieldError = (name: keyof SessionConfig) => {
    const msg = fieldErrors[name];
    if (!msg) return null;
    return (
      <p className="field-error" role="alert" id={`${name}-error`}>
        {msg}
      </p>
    );
  };

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

  const apiErr =
    sessionMutation.error instanceof ApiError ? sessionMutation.error : null;
  const isRateLimited = apiErr?.status === 429;
  const rateLimitSeconds = apiErr?.retryAfterSeconds ?? null;
  const error: string | null = (() => {
    if (!sessionMutation.error) return null;
    if (isRateLimited && rateLimitSeconds !== null) {
      return `Too many sessions. Try again in ${Math.ceil(rateLimitSeconds)} seconds.`;
    }
    if (apiErr) return apiErr.message;
    if (sessionMutation.error instanceof Error) return sessionMutation.error.message;
    return "Unable to join the Daily room.";
  })();

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
            <label className="field-label" htmlFor="system_prompt">
              Personality / System Prompt
            </label>
            <textarea
              id="system_prompt"
              className="system-prompt-input"
              maxLength={4000}
              rows={11}
              disabled={connected || busy}
              aria-invalid={Boolean(fieldErrors.system_prompt)}
              aria-describedby={
                fieldErrors.system_prompt ? "system_prompt-error" : undefined
              }
              value={config.system_prompt}
              onChange={(e) =>
                setConfig((c) => ({ ...c, system_prompt: e.target.value }))
              }
            />
            <p className="field-help">
              Defines Freya&apos;s identity, tone, boundaries, and response style.
            </p>
            {fieldError("system_prompt")}
          </div>

          <div className="field-grid-2">
            <div className="field">
              <label className="field-label" htmlFor="temperature">
                LLM temperature
              </label>
              <input
                id="temperature"
                type="number"
                min="0"
                max="2"
                step="0.1"
                disabled={connected || busy}
                aria-invalid={Boolean(fieldErrors.temperature)}
                value={config.temperature}
                onChange={(e) => setNum("temperature", e.target.value)}
              />
              {fieldError("temperature")}
            </div>
            <div className="field">
              <label className="field-label" htmlFor="max_tokens">
                Max tokens
              </label>
              <input
                id="max_tokens"
                type="number"
                min="1"
                max="4096"
                disabled={connected || busy}
                aria-invalid={Boolean(fieldErrors.max_tokens)}
                value={config.max_tokens}
                onChange={(e) => setNum("max_tokens", e.target.value)}
              />
              {fieldError("max_tokens")}
            </div>
            <div className="field">
              <label className="field-label" htmlFor="stt_temperature">
                STT temperature
              </label>
              <input
                id="stt_temperature"
                type="number"
                min="0"
                max="1"
                step="0.1"
                disabled={connected || busy}
                aria-invalid={Boolean(fieldErrors.stt_temperature)}
                value={config.stt_temperature}
                onChange={(e) => setNum("stt_temperature", e.target.value)}
              />
              <p className="field-help">
                Deepgram streaming does not expose temperature. This value is
                validated and logged for contract traceability, but is not applied.
              </p>
              {fieldError("stt_temperature")}
            </div>
            <div className="field">
              <label className="field-label" htmlFor="tts_temperature">
                TTS temperature
              </label>
              <input
                id="tts_temperature"
                type="number"
                min="0"
                max="1"
                step="0.1"
                disabled={connected || busy}
                aria-invalid={Boolean(fieldErrors.tts_temperature)}
                value={config.tts_temperature}
                onChange={(e) => setNum("tts_temperature", e.target.value)}
              />
              <p className="field-help">
                Mapped to Cartesia voice emotion: neutral, default, or excited.
              </p>
              {fieldError("tts_temperature")}
            </div>
            <div className="field">
              <label className="field-label" htmlFor="tts_speed">
                Voice speed
              </label>
              <input
                id="tts_speed"
                type="number"
                min="0.6"
                max="1.5"
                step="0.1"
                disabled={connected || busy}
                aria-invalid={Boolean(fieldErrors.tts_speed)}
                value={config.tts_speed}
                onChange={(e) => setNum("tts_speed", e.target.value)}
              />
              {fieldError("tts_speed")}
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
          {fieldError("tts_voice_id")}

          <div className="field">
            <label className="field-label" htmlFor="interruptibility_pct">
              Interruptibility: {config.interruptibility_pct}% ·{" "}
              {interruptibilityLabel(config.interruptibility_pct)}
            </label>
            <input
              id="interruptibility_pct"
              type="range"
              min="0"
              max="100"
              disabled={connected || busy}
              aria-invalid={Boolean(fieldErrors.interruptibility_pct)}
              value={config.interruptibility_pct}
              onChange={(e) => setNum("interruptibility_pct", e.target.value)}
            />
            <p className="field-help">
              Controls how much speech is required to interrupt Freya. Zero disables
              barge-in; higher values react to fewer, quieter words.
            </p>
            {fieldError("interruptibility_pct")}
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
              onClick={handleStart}
            >
              {busy ? "Connecting…" : "Start session"}
            </button>
          )}
          {customVoiceIncomplete && (
            <p className="field-error" role="alert">
              Enter a name and voice ID for the custom voice, or pick a preset above.
            </p>
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
