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
    if (!room || !localVideoRef.current) return;

    // The ONLY reliable event for local video: LocalTrackPublished
    // Local tracks are NOT subscribed - they're published and immediately available
    const handleLocalTrackPublished = (publication: any) => {
      if (
        publication?.source === Track.Source.Camera &&
        publication?.track &&
        localVideoRef.current
      ) {
        console.log('🎥 Local camera track published, attaching...');
        try {
          publication.track.attach(localVideoRef.current);
          setHasVideo(true);
          console.log('✅ Video track attached successfully');
        } catch (error) {
          console.error('Failed to attach video track:', error);
          setHasVideo(false);
        }
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

    room.on(RoomEvent.LocalTrackPublished, handleLocalTrackPublished);
    room.on(RoomEvent.LocalTrackUnpublished, handleLocalTrackUnpublished);

    // Check if camera was already enabled BEFORE listener was set up
    // This handles the case where camera is enabled before component mounts
    if (room.state === 'connected') {
      for (const pub of room.localParticipant.videoTrackPublications.values()) {
        if (pub.source === Track.Source.Camera && pub.track && localVideoRef.current) {
          console.log('🎥 Camera already published, attaching...');
          try {
            pub.track.attach(localVideoRef.current);
            setHasVideo(true);
            console.log('✅ Video track attached (already published)');
          } catch (error) {
            console.error('Failed to attach existing video track:', error);
          }
          break;
        }
      }
    }

    return () => {
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = null;
      }
      room.off(RoomEvent.LocalTrackPublished, handleLocalTrackPublished);
      room.off(RoomEvent.LocalTrackUnpublished, handleLocalTrackUnpublished);
    };
  }, [room]);

  return (
    <Card className="h-full w-full">
      <CardContent className="h-full p-0 relative bg-black rounded-lg overflow-hidden">
        {hasVideo ? (
          <video
            ref={localVideoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-muted">
            <p className="text-muted-foreground text-sm">No video</p>
          </div>
        )}
        <div className="absolute bottom-2 left-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
          {userName}
        </div>
      </CardContent>
    </Card>
  );
}

