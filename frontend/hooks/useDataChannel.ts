"use client";

import { useEffect, useReducer } from "react";

import type { DailyCall } from "@daily-co/daily-js";

import type { BotState, DataChannelEvent } from "@/types/contract";

export type DataChannelState = {
  botState: BotState | null;
  latencyMs: number | null;
  interruptions: { at: number }[];
  sessionEndedReason: "inactivity" | null;
};

const initial: DataChannelState = {
  botState: null,
  latencyMs: null,
  interruptions: [],
  sessionEndedReason: null,
};

type ReducerAction = DataChannelEvent | { type: "__reset__" };

export function reducer(
  state: DataChannelState,
  action: ReducerAction,
): DataChannelState {
  switch (action.type) {
    case "__reset__":
      return initial;
    case "state":
      return { ...state, botState: action.state };
    case "latency":
      return { ...state, latencyMs: action.ms };
    case "interruption":
      return { ...state, interruptions: [...state.interruptions, { at: action.at }] };
    case "session_ended":
      return { ...state, sessionEndedReason: action.reason };
    default:
      return state;
  }
}

const KNOWN_TYPES = new Set([
  "state",
  "latency",
  "interruption",
  "session_ended",
]);

type SessionEndedCallback = (
  reason: "inactivity",
  endedCall: DailyCall,
) => void;

export function useDataChannel(
  call: DailyCall | null,
  onSessionEnded?: SessionEndedCallback,
): DataChannelState {
  const [state, dispatch] = useReducer(reducer, initial);

  useEffect(() => {
    // Reset state on every call change so a new session never shows stale data
    dispatch({ type: "__reset__" });

    if (!call) return;

    const handler = (msg: { data?: unknown }) => {
      console.log("[useDataChannel] app-message received:", msg.data);

      const d = msg.data;
      if (
        d !== null &&
        typeof d === "object" &&
        "type" in d &&
        typeof (d as Record<string, unknown>).type === "string" &&
        KNOWN_TYPES.has((d as Record<string, unknown>).type as string)
      ) {
        const event = d as DataChannelEvent;
        console.log("[useDataChannel] dispatching event:", event.type, event);
        dispatch(event);
        if (event.type === "session_ended") {
          onSessionEnded?.(event.reason, call);
        }
      }
    };

    call.on("app-message", handler);
    console.log("[useDataChannel] subscribed to app-message");

    return () => {
      call.off("app-message", handler);
      console.log("[useDataChannel] unsubscribed from app-message");
    };
  }, [call, onSessionEnded]);

  return state;
}
