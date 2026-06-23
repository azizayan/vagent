from __future__ import annotations


def temperature_to_emotion(temperature: float) -> str | None:
    """Map ``tts_temperature`` (0.0–1.0) to a Cartesia Sonic-3 emotion string.

    Pipecat 1.0.0's ``CartesiaTTSService`` exposes only ``volume`` / ``speed`` /
    ``emotion`` on Sonic-3 — temperature was dropped from the model. We translate
    the user-facing temperature into the closest available knob so the config
    field has a real audible effect:

    - ``< 0.34``  → ``"neutral"``   (flat, low-variation delivery)
    - ``0.34..0.66`` → ``None``      (Cartesia default — moderate expressiveness)
    - ``> 0.66``  → ``"excited"``   (high-energy, varied prosody)

    Returning ``None`` lets Cartesia fall back to its default voice prosody.
    """
    if temperature < 0.34:
        return "neutral"
    if temperature > 0.66:
        return "excited"
    return None
