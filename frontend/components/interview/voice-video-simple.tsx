'use client';

import { useEffect, useRef, useState } from 'react';
import { Room, RoomEvent, Track, ParticipantEvent, RemoteParticipant, LocalParticipant } from 'livekit-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Mic, MicOff, Video, VideoOff, PhoneOff, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

interface VoiceVideoProps {
  token: string;
  serverUrl: string;
  roomName: string;
  userName: string;
  onDisconnect?: () => void;
  onError?: (error: Error) => void;
  onRoomReady?: (room: Room) => void;
}

export function VoiceVideoRoom({
  token,
  serverUrl,
  roomName,
  userName,
  onDisconnect,
  onError,
  onRoomReady,
}: VoiceVideoProps) {
  const [isConnected, setIsConnected] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoEnabled, setIsVideoEnabled] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [participants, setParticipants] = useState<(LocalParticipant | RemoteParticipant)[]>([]);
  const roomRef = useRef<Room | null>(null);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const remoteVideoRef = useRef<HTMLVideoElement>(null);
  const remoteAudioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    let isMounted = true;
    let roomInstance: Room | null = null;
    let isIntentionallyDisconnecting = false;

    const connectToRoom = async () => {
      try {
        const room = new Room({
          adaptiveStream: true,
          dynacast: true,
          publishDefaults: {
            videoCodec: 'vp9',
          },
        });

        roomInstance = room;
        roomRef.current = room;

        const updateParticipants = () => {
          if (!isMounted || !roomInstance) return;
          const allParticipants = [
            roomInstance.localParticipant,
            ...Array.from(roomInstance.remoteParticipants.values()),
          ];
          setParticipants(allParticipants);
        };

        // Set up event listeners
        room.on(RoomEvent.Connected, () => {
          if (!isMounted) return;
          setIsConnected(true);
          setIsLoading(false);
          toast.success('Connected to interview room');
          updateParticipants();
          // Notify parent component that room is ready
          if (onRoomReady) {
            onRoomReady(room);
          }
        });

        room.on(RoomEvent.Disconnected, () => {
          if (!isMounted) return;
          setIsConnected(false);
          if (onDisconnect) {
            onDisconnect();
          }
        });

        room.on(RoomEvent.Reconnecting, () => {
          if (!isMounted) return;
          toast.info('Reconnecting to room...');
        });

        room.on(RoomEvent.Reconnected, () => {
          if (!isMounted) return;
          toast.success('Reconnected to room');
        });

        room.on(RoomEvent.ParticipantConnected, () => {
          if (!isMounted) return;
          updateParticipants();
        });

        room.on(RoomEvent.ParticipantDisconnected, () => {
          if (!isMounted) return;
          updateParticipants();
        });

        room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
          if (!isMounted) return;
          if (track.kind === 'video') {
            const videoElement = remoteVideoRef.current;
            if (videoElement) {
              track.attach(videoElement);
            }
          } else if (track.kind === 'audio') {
            // Create audio element if it doesn't exist
            if (!remoteAudioRef.current) {
              const audioElement = document.createElement('audio');
              audioElement.autoplay = true;
              audioElement.playsInline = true;
              audioElement.setAttribute('playsinline', 'true');
              // Important: Enable autoplay and mute control
              audioElement.muted = false;
              remoteAudioRef.current = audioElement;
              document.body.appendChild(audioElement);
              console.log('Created audio element for remote audio');
            }
            // Attach audio track to audio element
            if (remoteAudioRef.current) {
              track.attach(remoteAudioRef.current);
              console.log('Audio track attached to element:', publication.trackSid, participant.name);
            }
          }
        });

        room.on(RoomEvent.TrackUnsubscribed, (track) => {
          if (!isMounted) return;
          track.detach();
          // Clean up audio element if needed
          if (track.kind === 'audio' && remoteAudioRef.current) {
            // Audio element will be cleaned up on component unmount
          }
        });

        // Connect to room
        await room.connect(serverUrl, token);

        if (!isMounted) {
          await room.disconnect();
          return;
        }

        // Enable local tracks
        await room.localParticipant.setCameraEnabled(true);
        await room.localParticipant.setMicrophoneEnabled(true);

        // Attach local video
        const localVideoTrack = room.localParticipant.getTrackPublication(Track.Source.Camera);
        if (localVideoTrack?.track && localVideoRef.current) {
          localVideoTrack.track.attach(localVideoRef.current);
        }
      } catch (error: any) {
        if (!isMounted || isIntentionallyDisconnecting) return;
        
        // Don't show error for expected disconnects during development (Fast Refresh)
        const isDisconnectError = error?.message?.includes('Client initiated disconnect') || 
                                  error?.message?.includes('disconnect') ||
                                  error?.message?.includes('cancelled');
        
        if (!isDisconnectError) {
          console.error('Failed to connect to room:', error);
          setIsLoading(false);
          if (onError) {
            onError(error as Error);
          } else {
            toast.error('Failed to connect to interview room');
          }
        } else {
          // Silently handle expected disconnects (cleanup, Fast Refresh, etc.)
          setIsLoading(false);
        }
      }
    };

    connectToRoom();

    return () => {
      isMounted = false;
      isIntentionallyDisconnecting = true;
      // Clean up audio element
      if (remoteAudioRef.current) {
        remoteAudioRef.current.remove();
        remoteAudioRef.current = null;
      }
      if (roomInstance) {
        // Disconnect the room - errors are expected during Fast Refresh/unmount
        roomInstance.disconnect().catch(() => {
          // Silently ignore disconnect errors during cleanup
        });
        roomInstance = null;
      }
      roomRef.current = null;
    };
  }, [token, serverUrl]);

  const toggleMute = async () => {
    if (!roomRef.current) return;

    const localParticipant = roomRef.current.localParticipant;
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
    if (!roomRef.current) return;

    const localParticipant = roomRef.current.localParticipant;
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
    if (roomRef.current) {
      try {
        await roomRef.current.disconnect();
      } catch (error) {
        // Ignore disconnect errors
      }
      roomRef.current = null;
    }
    if (onDisconnect) {
      onDisconnect();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {isLoading && (
        <div className="flex items-center justify-center h-full">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Connecting...</span>
        </div>
      )}

      {isConnected && (
        <>
          <div className="flex-1 relative bg-black rounded-lg overflow-hidden mb-4">
            {participants.length === 0 ? (
              <div className="flex items-center justify-center h-full text-white">
                <p>Waiting for participants...</p>
              </div>
            ) : participants.length === 1 ? (
              <div className="flex items-center justify-center h-full">
                <video
                  ref={localVideoRef}
                  autoPlay
                  playsInline
                  muted
                  className="w-full h-full object-cover"
                />
                <div className="absolute bottom-2 left-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
                  {userName}
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2 h-full p-2">
                <div className="relative rounded-lg overflow-hidden">
                  <video
                    ref={localVideoRef}
                    autoPlay
                    playsInline
                    muted
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute bottom-2 left-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
                    You
                  </div>
                </div>
                <div className="relative rounded-lg overflow-hidden">
                  <video
                    ref={remoteVideoRef}
                    autoPlay
                    playsInline
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute bottom-2 left-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
                    {participants.find((p) => !p.isLocal)?.name || 'Participant'}
                  </div>
                </div>
              </div>
            )}
          </div>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-center space-x-4">
                <Button
                  variant={isMuted ? 'destructive' : 'default'}
                  size="lg"
                  onClick={toggleMute}
                  className="rounded-full"
                >
                  {isMuted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
                </Button>

                <Button
                  variant={isVideoEnabled ? 'default' : 'secondary'}
                  size="lg"
                  onClick={toggleVideo}
                  className="rounded-full"
                >
                  {isVideoEnabled ? <Video className="h-5 w-5" /> : <VideoOff className="h-5 w-5" />}
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
        </>
      )}
    </div>
  );
}

