'use client';

import { Card, CardContent } from '@/components/ui/card';
import { AudioVisualizer } from './audio-visualizer';
import { Room } from 'livekit-client';

interface AvatarWithWavesProps {
  room: Room | null;
  avatarSrc?: string;
}

export function AvatarWithWaves({ room, avatarSrc = '/avatar.jpg' }: AvatarWithWavesProps) {
  return (
    <Card className="h-full w-full">
      <CardContent className="h-full p-0 flex flex-col relative overflow-hidden">
        {/* Avatar Image with Waves Overlay */}
        <div className="flex-1 flex items-center justify-center bg-primary/5 relative overflow-hidden">
          <img 
            src={avatarSrc} 
            alt="Interviewer" 
            className="w-full h-full object-cover z-10 relative"
          />
          {/* Big Animated Waves Overlay */}
          {room && (
            <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/20">
              <div className="w-full px-2">
                <AudioVisualizer room={room} />
              </div>
            </div>
          )}
        </div>
        {/* Big Waves Visualizer at Bottom */}
        {room && (
          <div className="bg-primary/10 border-t border-border/50 py-4 relative overflow-hidden">
            <div className="flex items-center justify-center h-full">
              <AudioVisualizer room={room} />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

