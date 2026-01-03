'use client';

import { useEffect, useRef, useState } from 'react';
import { Room, RoomEvent, Track } from 'livekit-client';
import { Card, CardContent } from '@/components/ui/card';

interface ParticipantVideoProps {
  room: Room | null;
  userName?: string;
}

export function ParticipantVideo({ room, userName = 'You' }: ParticipantVideoProps) {
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const [hasVideo, setHasVideo] = useState(false);

  useEffect(() => {
    // Only run when room is connected and video element exists
    if (!room || room.state !== 'connected' || !localVideoRef.current) return;

    // Idempotent attachment function - handles both event-based and reconciliation cases
    const attachIfExists = () => {
      for (const pub of room.localParticipant.videoTrackPublications.values()) {
        if (
          pub.source === Track.Source.Camera &&
          pub.track &&
          localVideoRef.current
        ) {
          try {
            console.log('🎥 Attaching local camera track');
            pub.track.attach(localVideoRef.current);
            setHasVideo(true);
            console.log('✅ Video track attached successfully');
            return true;
          } catch (error) {
            console.error('❌ Failed to attach video track:', error);
            setHasVideo(false);
            return false;
          }
        }
      }
      return false;
    };

    // Event handler for when tracks are published after listener is registered
    const handleLocalTrackPublished = (publication: any) => {
      if (
        publication?.source === Track.Source.Camera &&
        publication.track &&
        localVideoRef.current
      ) {
        console.log('🎥 Local camera track published event received');
        attachIfExists();
      }
    };

    // Handle track being unpublished (camera disabled)
    const handleLocalTrackUnpublished = (publication: any) => {
      if (publication?.source === Track.Source.Camera) {
        console.log('🎥 Local video track unpublished');
        setHasVideo(false);
        if (localVideoRef.current) {
          localVideoRef.current.srcObject = null;
        }
      }
    };

    // Register event listeners
    room.on(RoomEvent.LocalTrackPublished, handleLocalTrackPublished);
    room.on(RoomEvent.LocalTrackUnpublished, handleLocalTrackUnpublished);

    // 🔑 CRITICAL: Reconcile immediately - handles case where track was published
    // before component mounted or before listener was registered
    attachIfExists();

    return () => {
      room.off(RoomEvent.LocalTrackPublished, handleLocalTrackPublished);
      room.off(RoomEvent.LocalTrackUnpublished, handleLocalTrackUnpublished);
      // Cleanup: detach track on unmount
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = null;
      }
    };
  }, [room, room?.state]); // Re-run when room or room state changes

  return (
    <Card className="h-full w-full">
      <CardContent className="h-full p-0 relative bg-black rounded-lg overflow-hidden">
        {/* Always render video element - track attachment happens regardless */}
        <video
          ref={localVideoRef}
          autoPlay
          playsInline
          muted
          className="w-full h-full object-cover"
        />
        {/* Show overlay when no video track is available */}
        {!hasVideo && (
          <div className="absolute inset-0 flex items-center justify-center bg-muted/80 pointer-events-none">
            <p className="text-muted-foreground text-sm">No video</p>
          </div>
        )}
        <div className="absolute bottom-2 left-2 bg-black/50 text-white px-2 py-1 rounded text-xs z-10">
          {userName}
        </div>
      </CardContent>
    </Card>
  );
}

