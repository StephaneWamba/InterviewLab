'use client';

import { useEffect, useRef, useState } from 'react';
import { Room, RemoteParticipant, Track, TrackPublication } from 'livekit-client';

interface AudioVisualizerProps {
  room: Room | null;
  participantIdentity?: string; // Identity of the AI agent participant
}

export function AudioVisualizer({ room, participantIdentity }: AudioVisualizerProps) {
  const [audioLevel, setAudioLevel] = useState(0);
  const animationFrameRef = useRef<number | undefined>(undefined);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const dataArrayRef = useRef<Uint8Array | null>(null);

  useEffect(() => {
    if (!room) {
      setAudioLevel(0);
      return;
    }

    // Find the AI agent participant (usually has a specific identity or name)
    const findAgentParticipant = (): RemoteParticipant | null => {
      for (const participant of room.remoteParticipants.values()) {
        // Check if this is the agent (not the local user)
        if (participantIdentity) {
          if (participant.identity === participantIdentity) {
            return participant;
          }
        } else {
          // If no identity specified, use first remote participant that's not the user
          // In LiveKit, agents typically have specific naming patterns
          if (participant.name && participant.name.toLowerCase().includes('agent')) {
            return participant;
          }
        }
      }
      // Fallback: use first remote participant
      const firstRemote = Array.from(room.remoteParticipants.values())[0];
      return firstRemote || null;
    };

    const setupAudioAnalysis = async () => {
      const agentParticipant = findAgentParticipant();
      if (!agentParticipant) {
        setAudioLevel(0);
        return;
      }

      // Find audio track from agent
      let audioTrack: Track | null = null;
      for (const publication of agentParticipant.audioTrackPublications.values()) {
        if (publication.track) {
          audioTrack = publication.track;
          break;
        }
      }

      if (!audioTrack) {
        setAudioLevel(0);
        return;
      }

      // Wait for track to be ready
      const waitForTrack = async () => {
        let attempts = 0;
        while (attempts < 10 && !audioTrack?.mediaStreamTrack) {
          await new Promise(resolve => setTimeout(resolve, 100));
          attempts++;
        }

        if (!audioTrack?.mediaStreamTrack) {
          setAudioLevel(0);
          return;
        }

        try {
          // Create audio context and analyser
          const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
          const analyser = audioContext.createAnalyser();
          analyser.fftSize = 256;
          analyser.smoothingTimeConstant = 0.8;

          const source = audioContext.createMediaStreamSource(
            new MediaStream([audioTrack.mediaStreamTrack])
          );
          source.connect(analyser);

          const dataArray = new Uint8Array(analyser.frequencyBinCount);

          audioContextRef.current = audioContext;
          analyserRef.current = analyser;
          dataArrayRef.current = dataArray;

          // Start analyzing audio levels
          const analyzeAudio = () => {
            if (!analyserRef.current || !dataArrayRef.current) return;

            // @ts-ignore - TypeScript type mismatch, but works at runtime
            analyserRef.current.getByteFrequencyData(dataArrayRef.current);

            // Calculate average audio level
            const sum = Array.from(dataArrayRef.current).reduce((a, b) => a + b, 0);
            const average = sum / dataArrayRef.current.length;
            const normalizedLevel = Math.min(average / 128, 1); // Normalize to 0-1

            setAudioLevel(normalizedLevel);

            animationFrameRef.current = requestAnimationFrame(analyzeAudio);
          };

          analyzeAudio();
        } catch (error) {
          console.error('Error setting up audio analysis:', error);
          setAudioLevel(0);
        }
      };

      waitForTrack();
    };

    // Set up audio analysis when room or participants change
    const handleParticipantChange = () => {
      setupAudioAnalysis();
    };

    room.on('participantConnected', handleParticipantChange);
    room.on('trackSubscribed', handleParticipantChange);

    setupAudioAnalysis();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(console.error);
      }
      room.off('participantConnected', handleParticipantChange);
      room.off('trackSubscribed', handleParticipantChange);
    };
  }, [room, participantIdentity]);

  // Generate wave bars based on audio level
  const [timeOffset, setTimeOffset] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setTimeOffset(Date.now() / 150);
    }, 50); // Update every 50ms for smooth animation

    return () => clearInterval(interval);
  }, []);

  const generateBars = () => {
    const barCount = 16; // Fewer bars for bigger waves
    const bars = [];
    const baseHeight = 8; // Bigger base
    const maxHeight = 60; // Much bigger max height for "big waves"

    for (let i = 0; i < barCount; i++) {
      // Create wave pattern with variation based on audio level
      const phase = (i / barCount) * Math.PI * 2;
      const wave = Math.sin(phase + timeOffset);
      
      // Vary the height based on audio level and wave pattern
      // Bigger waves when audio is present
      const heightMultiplier = audioLevel > 0.1 
        ? audioLevel * (1 + wave * 0.6) // More variation
        : 0.3 + Math.sin(phase + timeOffset * 0.5) * 0.2; // More visible idle animation
      
      const height = baseHeight + heightMultiplier * (maxHeight - baseHeight);

      bars.push(
        <div
          key={i}
          className="bg-primary rounded-full transition-all duration-75 ease-out"
          style={{
            height: `${Math.max(height, baseHeight)}px`,
            width: '4px', // Slightly wider bars
            opacity: audioLevel > 0.1 ? 0.8 + audioLevel * 0.2 : 0.5,
          }}
        />
      );
    }
    return bars;
  };

  return (
    <div className="w-full h-10 flex items-center justify-center gap-1 px-2">
      {generateBars()}
    </div>
  );
}

