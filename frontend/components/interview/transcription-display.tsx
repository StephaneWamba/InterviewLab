'use client';

import { useEffect, useState, useRef } from 'react';
import { Room, RoomEvent, TranscriptionSegment, ParticipantEvent } from 'livekit-client';
import { Card, CardContent } from '@/components/ui/card';
import { User, UserCheck } from 'lucide-react';

interface TranscriptionDisplayProps {
  room: Room | null;
}

interface TranscriptionMessage {
  id: string;
  text: string;
  speaker: string;
  timestamp: Date;
  isFinal: boolean;
}

export function TranscriptionDisplay({ room }: TranscriptionDisplayProps) {
  const [messages, setMessages] = useState<TranscriptionMessage[]>([]);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!room) return;

    console.log('Setting up transcription text stream handler for room:', room.name);

    // AgentSession STT outputs are sent via text streams, NOT RoomEvent.TranscriptionReceived
    // We must use registerTextStreamHandler with topic 'lk.transcription'
    const handler = async (reader: any, participantInfo?: any) => {
      try {
        const textData = await reader.readAll();
        const fullText = Array.isArray(textData) ? textData.join('') : textData;
        
        // Check if this is a final transcription
        const isFinal = reader.info?.attributes?.['lk.transcription_final'] === 'true';
        const segmentId = reader.info?.attributes?.['lk.segment_id'];
        const transcribedTrackId = reader.info?.attributes?.['lk.transcribed_track_id'];
        
        console.log('📝 Transcription received:', {
          text: fullText,
          isFinal,
          segmentId,
          participant: participantInfo?.identity || participantInfo?.name || 'Unknown',
          transcribedTrackId,
        });

        // Normalize speaker name - replace agent/AI references with "Interviewer"
        let speakerName = participantInfo?.name || 
                          participantInfo?.identity || 
                          'Unknown';
        
        // Replace agent/AI references with "Interviewer"
        if (speakerName.toLowerCase().includes('agent') || 
            speakerName.toLowerCase().includes('ai') ||
            speakerName.toLowerCase().includes('interviewer')) {
          speakerName = 'Interviewer';
        }
        
        setMessages((prev) => {
          const newMessages = [...prev];
          
          if (isFinal) {
            // Add final transcription
            newMessages.push({
              id: `${segmentId || 'final'}-${Date.now()}`,
              text: fullText,
              speaker: speakerName,
              timestamp: new Date(),
              isFinal: true,
            });
          } else {
            // Update or add interim transcription
            const existingIndex = newMessages.findIndex(
              (m) => !m.isFinal && m.speaker === speakerName && segmentId && m.id.startsWith(segmentId)
            );
            
            if (existingIndex >= 0) {
              newMessages[existingIndex] = {
                ...newMessages[existingIndex],
                text: fullText,
              };
            } else {
              newMessages.push({
                id: `${segmentId || 'interim'}-${Date.now()}`,
                text: fullText,
                speaker: speakerName,
                timestamp: new Date(),
                isFinal: false,
              });
            }
          }
          
          // Keep only last 100 messages
          return newMessages.slice(-100);
        });
      } catch (error) {
        console.error('Error reading transcription text stream:', error);
      }
    };

    // Register text stream handler for AgentSession transcriptions
    // Note: registerTextStreamHandler doesn't return a Promise, so no .catch()
    try {
      room.registerTextStreamHandler('lk.transcription', handler);
      console.log('✅ Transcription text stream handler registered for topic: lk.transcription');
    } catch (error) {
      console.error('Failed to register transcription text stream handler:', error);
    }

    return () => {
      try {
        room.unregisterTextStreamHandler('lk.transcription', handler);
      } catch (error) {
        console.warn('Failed to unregister transcription handler:', error);
      }
    };
  }, [room]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <Card className="h-full flex flex-col">
      <CardContent className="flex-1 p-4 flex flex-col min-h-0">
        <h3 className="text-sm font-semibold mb-3">Conversation</h3>
        <div className="flex-1 overflow-y-auto space-y-2 pr-4" ref={scrollAreaRef}>
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              Waiting for conversation to start...
            </p>
          ) : (
            messages.map((message) => {
              const isInterviewer = message.speaker === 'Interviewer' ||
                                   message.speaker.toLowerCase().includes('interviewer') ||
                                   message.speaker.toLowerCase().includes('agent') ||
                                   message.speaker.toLowerCase().includes('ai');
              const isUser = message.speaker === room?.localParticipant?.name || 
                           message.speaker === room?.localParticipant?.identity;
              
              const displayName = isUser ? 'You' : (isInterviewer ? 'Interviewer' : message.speaker);
              
              return (
                <div
                  key={message.id}
                  className={`flex items-start gap-2 p-2 rounded-lg ${
                    isInterviewer 
                      ? 'bg-primary/5 border-l-2 border-primary' 
                      : isUser
                      ? 'bg-muted/50 border-l-2 border-muted-foreground'
                      : 'bg-background'
                  } ${!message.isFinal ? 'opacity-60' : ''}`}
                >
                  <div className={`flex-shrink-0 mt-0.5 ${
                    isInterviewer ? 'text-primary' : 'text-muted-foreground'
                  }`}>
                    {isInterviewer ? (
                      <UserCheck className="h-4 w-4" />
                    ) : (
                      <User className="h-4 w-4" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`font-semibold text-xs ${
                        isInterviewer ? 'text-primary' : 'text-foreground'
                      }`}>
                        {displayName}
                      </span>
                      {!message.isFinal && (
                        <span className="text-xs text-muted-foreground italic">(typing...)</span>
                      )}
                    </div>
                    <p className={`text-sm ${
                      isInterviewer ? 'text-foreground' : 'text-foreground'
                    } ${!message.isFinal ? 'italic' : ''}`}>
                      {message.text}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </CardContent>
    </Card>
  );
}

