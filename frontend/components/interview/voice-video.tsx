'use client';

import { useEffect, useRef, useState } from 'react';
import {
  LiveKitRoom,
  VideoTrack,
  useTracks,
  RoomAudioRenderer,
  useRoomContext,
} from '@livekit/components-react';
import '@livekit/components-styles';
import {
  Room,
  RoomEvent,
  Track,
  ParticipantEvent,
  RemoteParticipant,
  LocalParticipant,
} from 'livekit-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Mic,
  MicOff,
  Video,
  VideoOff,
  PhoneOff,
  Loader2,
} from 'lucide-react';
import { toast } from 'sonner';

interface VoiceVideoProps {
  token: string;
  serverUrl: string;
  roomName: string;
  onDisconnect?: () => void;
  onError?: (error: Error) => void;
}

export function VoiceVideoRoom({
  token,
  serverUrl,
  roomName,
  onDisconnect,
  onError,
}: VoiceVideoProps) {
  const [isConnected, setIsConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const handleConnect = () => {
    setIsConnected(true);
    setIsLoading(false);
    toast.success('Connected to interview room');
  };

  const handleDisconnected = () => {
    setIsConnected(false);
    if (onDisconnect) {
      onDisconnect();
    }
  };

  return (
    <LiveKitRoom
      video={true}
      audio={true}
      token={token}
      serverUrl={serverUrl}
      connect={true}
      onConnected={handleConnect}
      onDisconnected={handleDisconnected}
      onError={onError}
      options={{
        adaptiveStream: true,
        dynacast: true,
        publishDefaults: {
          videoCodec: 'vp9',
        },
      }}
      className="h-full"
    >
      <RoomAudioRenderer />
      <RoomControls
        isLoading={isLoading}
        isConnected={isConnected}
        onDisconnect={onDisconnect}
      />
      {isConnected && (
        <div className="flex-1 relative bg-black rounded-lg overflow-hidden mb-4">
          <ParticipantGrid roomName={roomName} />
        </div>
      )}
    </LiveKitRoom>
  );
}

function RoomControls({
  isLoading,
  isConnected,
  onDisconnect,
}: {
  isLoading: boolean;
  isConnected: boolean;
  onDisconnect?: () => void;
}) {
  const room = useRoomContext();
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoEnabled, setIsVideoEnabled] = useState(true);

  const toggleMute = async () => {
    if (!room) return;

    const localParticipant = room.localParticipant;
    const micTrack = localParticipant.getTrackPublication(Track.Source.Microphone);

    if (micTrack && micTrack.isMuted) {
      await localParticipant.setMicrophoneEnabled(true);
      setIsMuted(false);
    } else {
      await localParticipant.setMicrophoneEnabled(false);
      setIsMuted(true);
    }
  };

  const toggleVideo = async () => {
    if (!room) return;

    const localParticipant = room.localParticipant;
    const cameraTrack = localParticipant.getTrackPublication(Track.Source.Camera);

    if (cameraTrack && !cameraTrack.isMuted) {
      await localParticipant.setCameraEnabled(false);
      setIsVideoEnabled(false);
    } else {
      await localParticipant.setCameraEnabled(true);
      setIsVideoEnabled(true);
    }
  };

  const handleDisconnect = async () => {
    if (room) {
      await room.disconnect();
    }
    if (onDisconnect) {
      onDisconnect();
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Connecting...</span>
      </div>
    );
  }

  if (!isConnected) {
    return null;
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-center space-x-4">
          <Button
            variant={isMuted ? 'destructive' : 'default'}
            size="lg"
            onClick={toggleMute}
            className="rounded-full"
          >
            {isMuted ? (
              <MicOff className="h-5 w-5" />
            ) : (
              <Mic className="h-5 w-5" />
            )}
          </Button>

          <Button
            variant={isVideoEnabled ? 'default' : 'secondary'}
            size="lg"
            onClick={toggleVideo}
            className="rounded-full"
          >
            {isVideoEnabled ? (
              <Video className="h-5 w-5" />
            ) : (
              <VideoOff className="h-5 w-5" />
            )}
          </Button>

          <Button
            variant="destructive"
            size="lg"
            onClick={handleDisconnect}
            className="rounded-full"
          >
            <PhoneOff className="h-5 w-5" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ParticipantGrid({ roomName }: { roomName: string }) {
  const room = useRoomContext();
  const [participants, setParticipants] = useState<
    (LocalParticipant | RemoteParticipant)[]
  >([]);

  useEffect(() => {
    if (!room) return;

    const updateParticipants = () => {
      const allParticipants = [
        room.localParticipant,
        ...Array.from(room.remoteParticipants.values()),
      ];
      setParticipants(allParticipants);
    };

    updateParticipants();

    room.on(ParticipantEvent.TrackPublished, updateParticipants);
    room.on(ParticipantEvent.TrackUnpublished, updateParticipants);
    room.on(RoomEvent.ParticipantConnected, updateParticipants);
    room.on(RoomEvent.ParticipantDisconnected, updateParticipants);

    return () => {
      room.off(ParticipantEvent.TrackPublished, updateParticipants);
      room.off(ParticipantEvent.TrackUnpublished, updateParticipants);
      room.off(RoomEvent.ParticipantConnected, updateParticipants);
      room.off(RoomEvent.ParticipantDisconnected, updateParticipants);
    };
  }, [room]);

  if (participants.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-white">
        <p>Waiting for participants...</p>
      </div>
    );
  }

  if (participants.length === 1) {
    // Only local participant
    return (
      <div className="flex items-center justify-center h-full">
        <ParticipantVideo participant={participants[0]} />
      </div>
    );
  }

  // Multiple participants - grid layout
  return (
    <div className="grid grid-cols-2 gap-2 h-full p-2">
      {participants.map((participant) => (
        <div key={participant.identity} className="relative rounded-lg overflow-hidden">
          <ParticipantVideo participant={participant} />
        </div>
      ))}
    </div>
  );
}

function ParticipantVideo({
  participant,
}: {
  participant: LocalParticipant | RemoteParticipant;
}) {
  const allTracks = useTracks(
    [
      { source: Track.Source.Camera, withPlaceholder: true },
      { source: Track.Source.ScreenShare, withPlaceholder: true },
    ],
    { onlySubscribed: false }
  );

  const videoTrack = allTracks.find(
    (track) =>
      track.participant.identity === participant.identity &&
      'publication' in track &&
      track.publication &&
      track.publication.kind === 'video' &&
      (track.source === Track.Source.Camera || track.source === Track.Source.ScreenShare)
  ) as typeof allTracks[number] & { publication: NonNullable<typeof allTracks[number]['publication']> } | undefined;

  return (
    <div className="relative w-full h-full bg-gray-900 rounded-lg overflow-hidden">
      {videoTrack ? (
        <VideoTrack
          trackRef={videoTrack}
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="flex items-center justify-center h-full bg-gray-800">
          <div className="text-center text-white">
            <div className="w-20 h-20 rounded-full bg-gray-700 flex items-center justify-center mx-auto mb-2">
              <span className="text-2xl font-semibold">
                {participant.name?.charAt(0).toUpperCase() || 'U'}
              </span>
            </div>
            <p className="text-sm">{participant.name || 'Participant'}</p>
          </div>
        </div>
      )}
      <div className="absolute bottom-2 left-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
        {participant.isLocal ? 'You' : participant.name || 'Participant'}
      </div>
    </div>
  );
}
