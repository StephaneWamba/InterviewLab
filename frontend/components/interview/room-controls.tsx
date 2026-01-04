'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Mic, MicOff, Video, VideoOff } from 'lucide-react';
import { Room, Track, RoomEvent } from 'livekit-client';
import { toast } from 'sonner';

interface RoomControlsProps {
  room: Room | null;
  onMuteChange?: (muted: boolean) => void;
  onVideoChange?: (enabled: boolean) => void;
}

export function RoomControls({ room, onMuteChange, onVideoChange }: RoomControlsProps) {
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoEnabled, setIsVideoEnabled] = useState(true);
  const [isLoading, setIsLoading] = useState(false);

  // Sync state with actual track states
  useEffect(() => {
    if (!room) return;

    const updateStates = () => {
      const micTrack = room.localParticipant.getTrackPublication(Track.Source.Microphone);
      const cameraTrack = room.localParticipant.getTrackPublication(Track.Source.Camera);
      
      setIsMuted(!micTrack || micTrack.isMuted || !micTrack.isSubscribed);
      setIsVideoEnabled(!!(cameraTrack && !cameraTrack.isMuted && cameraTrack.isSubscribed));
    };

    updateStates();
    
    room.on(RoomEvent.TrackPublished, updateStates);
    room.on(RoomEvent.TrackUnpublished, updateStates);
    room.on(RoomEvent.TrackSubscribed, updateStates);
    room.on(RoomEvent.TrackUnsubscribed, updateStates);

    return () => {
      room.off(RoomEvent.TrackPublished, updateStates);
      room.off(RoomEvent.TrackUnpublished, updateStates);
      room.off(RoomEvent.TrackSubscribed, updateStates);
      room.off(RoomEvent.TrackUnsubscribed, updateStates);
    };
  }, [room]);

  const toggleMute = async () => {
    console.log('toggleMute called', { room: !!room, roomState: room?.state });
    
    if (!room) {
      toast.error('Room not available');
      return;
    }

    // Only allow if room is connected
    if (room.state !== 'connected') {
      toast.error(`Room is ${room.state}. Please wait for connection.`);
      return;
    }

    setIsLoading(true);
    try {
      const localParticipant = room.localParticipant;
      const micTrack = localParticipant.getTrackPublication(Track.Source.Microphone);
      const isCurrentlyMuted = !micTrack || micTrack.isMuted || !micTrack.isSubscribed;

      console.log('Mute state:', { micTrack: !!micTrack, isMuted: micTrack?.isMuted, isCurrentlyMuted });

      if (isCurrentlyMuted) {
        await localParticipant.setMicrophoneEnabled(true);
        setIsMuted(false);
        onMuteChange?.(false);
        toast.success('Microphone enabled');
      } else {
        await localParticipant.setMicrophoneEnabled(false);
        setIsMuted(true);
        onMuteChange?.(true);
        toast.success('Microphone muted');
      }
    } catch (error) {
      console.error('Failed to toggle mute:', error);
      toast.error(`Failed to toggle microphone: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleVideo = async () => {
    console.log('toggleVideo called', { room: !!room, roomState: room?.state });
    
    if (!room) {
      toast.error('Room not available');
      return;
    }

    // Only allow if room is connected
    if (room.state !== 'connected') {
      toast.error(`Room is ${room.state}. Please wait for connection.`);
      return;
    }

    setIsLoading(true);
    try {
      const localParticipant = room.localParticipant;
      const cameraTrack = localParticipant.getTrackPublication(Track.Source.Camera);
      const isCurrentlyEnabled = cameraTrack && !cameraTrack.isMuted && cameraTrack.isSubscribed;

      console.log('Video state:', { cameraTrack: !!cameraTrack, isMuted: cameraTrack?.isMuted, isCurrentlyEnabled });

      if (isCurrentlyEnabled) {
        await localParticipant.setCameraEnabled(false);
        setIsVideoEnabled(false);
        onVideoChange?.(false);
        toast.success('Camera disabled');
      } else {
        await localParticipant.setCameraEnabled(true);
        setIsVideoEnabled(true);
        onVideoChange?.(true);
        toast.success('Camera enabled');
      }
    } catch (error) {
      console.error('Failed to toggle video:', error);
      toast.error(`Failed to toggle camera: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsLoading(false);
    }
  };

  const isRoomReady = room && room.state !== 'disconnected';

  return (
    <div className="flex items-center justify-center space-x-4 p-2">
      <Button
        variant={isMuted ? 'destructive' : 'default'}
        size="sm"
        onClick={toggleMute}
        className="rounded-full"
        disabled={!isRoomReady || isLoading}
        title={!isRoomReady ? 'Waiting for room connection...' : isMuted ? 'Unmute' : 'Mute'}
      >
        {isMuted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
      </Button>

      <Button
        variant={isVideoEnabled ? 'default' : 'secondary'}
        size="sm"
        onClick={toggleVideo}
        className="rounded-full"
        disabled={!isRoomReady || isLoading}
        title={!isRoomReady ? 'Waiting for room connection...' : isVideoEnabled ? 'Disable camera' : 'Enable camera'}
      >
        {isVideoEnabled ? <Video className="h-4 w-4" /> : <VideoOff className="h-4 w-4" />}
      </Button>
    </div>
  );
}

