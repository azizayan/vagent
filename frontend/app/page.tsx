"use client";

import { useRef, useState } from "react";

import type { DailyCall } from "@daily-co/daily-js";

import { createDailyCall, destroyDailyCall } from "@/lib/daily";
import { env } from "@/lib/env";

export default function HomePage() {
  const callRef = useRef<DailyCall | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");

  const toggleConnection = async (): Promise<void> => {
    setError("");

    try {
      if (callRef.current) {
        await destroyDailyCall(callRef.current);
        callRef.current = null;
        setConnected(false);
        return;
      }

      if (!env.dailyRoomUrl) {
        throw new Error("NEXT_PUBLIC_DAILY_ROOM_URL is not set.");
      }

      const call = createDailyCall();
      callRef.current = call;
      await call.join({ url: env.dailyRoomUrl });
      setConnected(true);
    } catch (cause) {
      if (callRef.current) {
        await destroyDailyCall(callRef.current);
        callRef.current = null;
      }
      setConnected(false);
      setError(cause instanceof Error ? cause.message : "Unable to join the Daily room.");
    }
  };

  return (
    <main>
      <h1>Freya voice bot</h1>
      <button type="button" onClick={() => void toggleConnection()}>
        {connected ? "Disconnect" : "Connect"}
      </button>
      {error ? <p role="alert">{error}</p> : null}
    </main>
  );
}
