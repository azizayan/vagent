"use client";

export type VoiceOption = {
  id: string;
  name: string;
  role: string;
  description: string;
};

export const CARTESIA_VOICES: VoiceOption[] = [
  {
    id: "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
    name: "Skylar",
    role: "Friendly Guide",
    description:
      "Approachable American female ideal for customer care and support.",
  },
  {
    id: "630ed21c-2c5c-41cf-9d82-10a7fd668370",
    name: "Corey",
    role: "Supportive Buddy",
    description:
      "Inviting, cheerful young adult male for casual conversation.",
  },
  {
    id: "2a12b36c-7f9b-4c3a-9f7a-72731b15323a",
    name: "Ella",
    role: "Caring Scout",
    description:
      "Approachable presence for bright, lightweight and everyday customer conversations.",
  },
  {
    id: "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
    name: "Jacqueline",
    role: "Reassuring Agent",
    description:
      "Confident, young adult female for empathic customer support.",
  },
  {
    id: "e8e5fffb-252c-436d-b842-8879b84445b6",
    name: "Cathy",
    role: "Coworker",
    description: "Nice, young adult female for casual conversations.",
  },
];

export const DEFAULT_CARTESIA_VOICE = CARTESIA_VOICES[0]!;

const CUSTOM_VOICE = "custom";

type VoicePickerProps = {
  disabled: boolean;
  selectedVoice: string;
  customName: string;
  customVoiceId: string;
  onSelectedVoiceChange: (value: string) => void;
  onCustomNameChange: (value: string) => void;
  onCustomVoiceIdChange: (value: string) => void;
};

export function VoicePicker({
  disabled,
  selectedVoice,
  customName,
  customVoiceId,
  onSelectedVoiceChange,
  onCustomNameChange,
  onCustomVoiceIdChange,
}: VoicePickerProps) {
  const selectedPreset = CARTESIA_VOICES.find(
    (voice) => voice.id === selectedVoice,
  );
  const isCustom = selectedVoice === CUSTOM_VOICE;

  return (
    <div className="field voice-picker">
      <label className="field-label" htmlFor="voice-select">
        Voice
      </label>
      <select
        id="voice-select"
        disabled={disabled}
        value={selectedVoice}
        onChange={(event) => onSelectedVoiceChange(event.target.value)}
      >
        {CARTESIA_VOICES.map((voice) => (
          <option key={voice.id} value={voice.id}>
            {voice.name} — {voice.role}
          </option>
        ))}
        <option value={CUSTOM_VOICE}>Custom Cartesia voice…</option>
      </select>

      {selectedPreset && (
        <p className="voice-description">{selectedPreset.description}</p>
      )}

      {isCustom && (
        <div className="custom-voice-fields">
          <label className="field">
            <span className="field-label">Voice name</span>
            <input
              type="text"
              required
              disabled={disabled}
              placeholder="e.g. My support voice"
              value={customName}
              onChange={(event) => onCustomNameChange(event.target.value)}
            />
          </label>
          <label className="field">
            <span className="field-label">Cartesia voice ID</span>
            <input
              type="text"
              required
              disabled={disabled}
              placeholder="Paste a Cartesia voice ID"
              value={customVoiceId}
              onChange={(event) => onCustomVoiceIdChange(event.target.value)}
            />
          </label>
        </div>
      )}
    </div>
  );
}

export const CUSTOM_VOICE_VALUE = CUSTOM_VOICE;
