"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface render errors in the browser console so they're visible during
    // debugging without depending on a remote logger.
    console.error("[freya] unhandled render error", error);
  }, [error]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>Freya</h1>
        <p>Interruptible voice agent</p>
      </header>
      <div className="panels">
        <main
          className="panel-session"
          role="alert"
          aria-live="assertive"
          style={{ gridColumn: "1 / -1" }}
        >
          <h2 style={{ marginTop: 0 }}>Something went wrong.</h2>
          <p className="metric-hint">
            The page hit an unexpected error and the session was stopped. Your
            mic and the Daily room have been released.
          </p>
          {error.digest && (
            <p className="metric-hint">Error reference: {error.digest}</p>
          )}
          <button className="btn-primary" onClick={() => reset()}>
            Try again
          </button>
        </main>
      </div>
    </div>
  );
}
