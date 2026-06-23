import DailyIframe, {
  type DailyCall,
  type DailyEventObjectParticipant,
  type DailyEventObjectTrack,
  type DailyParticipant,
} from "@daily-co/daily-js";

const remoteAudio = new Map<string, HTMLAudioElement>();

const playRemoteAudio = (participant: DailyParticipant): void => {
  if (participant.local) {
    return;
  }

  const track = participant.tracks.audio.persistentTrack;
  if (!track) {
    return;
  }

  let audio = remoteAudio.get(participant.session_id);
  if (!audio) {
    audio = document.createElement("audio");
    audio.autoplay = true;
    document.body.appendChild(audio);
    remoteAudio.set(participant.session_id, audio);
  }

  audio.srcObject = new MediaStream([track]);
  void audio.play();
};

export const createDailyCall = (): DailyCall => {
  const call = DailyIframe.createCallObject({
    audioSource: true,
    videoSource: false,
  });

  const updateAudio = (event?: DailyEventObjectParticipant): void => {
    if (event?.participant) {
      playRemoteAudio(event.participant);
    }
  };

  call.on("participant-joined", updateAudio);
  call.on("participant-updated", updateAudio);
  call.on("track-started", (event: DailyEventObjectTrack) => {
    if (event.participant) {
      playRemoteAudio(event.participant);
    }
  });

  return call;
};

export const destroyDailyCall = async (call: DailyCall): Promise<void> => {
  await call.leave();
  call.destroy();
  for (const audio of remoteAudio.values()) {
    audio.remove();
  }
  remoteAudio.clear();
};
