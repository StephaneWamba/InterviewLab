'use client';

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Play,
  CheckCircle2,
  Loader2,
  Video,
  ArrowLeft,
  Volume2,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { interviewsApi, Interview } from '@/lib/api/interviews';
import { voiceApi } from '@/lib/api/voice';
import { useAuthStore } from '@/lib/store/auth-store';
import dynamic from 'next/dynamic';
import { toast } from 'sonner';
import Link from 'next/link';
import { CodeSandbox } from '@/components/interview/sandbox';
import { useLiveKitRoom } from '@/hooks/use-livekit-room';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { InterviewSkillCard } from '@/components/analytics/interview-skill-card';

// Dynamically import components to avoid SSR issues
const AvatarWithWaves = dynamic(
  () => import('@/components/interview/avatar-with-waves').then((mod) => ({ default: mod.AvatarWithWaves })),
  { ssr: false }
);

const ParticipantVideo = dynamic(
  () => import('@/components/interview/participant-video').then((mod) => ({ default: mod.ParticipantVideo })),
  { ssr: false }
);

const TranscriptionDisplay = dynamic(
  () => import('@/components/interview/transcription-display').then((mod) => ({ default: mod.TranscriptionDisplay })),
  { ssr: false }
);

const RoomControls = dynamic(
  () => import('@/components/interview/room-controls').then((mod) => ({ default: mod.RoomControls })),
  { ssr: false }
);

export default function InterviewDetailPage() {
  const params = useParams();
  const interviewId = parseInt(params.id as string);
  const [isStarting, setIsStarting] = useState(false);
  const [voiceToken, setVoiceToken] = useState<{ token: string; url: string } | null>(null);
  const [showVoiceVideo, setShowVoiceVideo] = useState(false);
  const [agentReady, setAgentReady] = useState(false);
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  // Use the custom LiveKit hook - handles all connection lifecycle
  const {
    room: roomInstance,
    state: roomState,
    isConnected,
    isConnecting,
    reconnect: reconnectRoom,
    error: roomError,
  } = useLiveKitRoom({
    token: voiceToken?.token || null,
    url: voiceToken?.url || null,
    onConnected: async (room) => {
      // Reset agent ready state when connecting to new room
      setAgentReady(false);
      
      // Check if agent has audio tracks playing (agent is speaking)
      const checkAgentSpeaking = () => {
        for (const participant of room.remoteParticipants.values()) {
          // Check if participant has audio tracks
          for (const publication of participant.audioTrackPublications.values()) {
            if (publication.track && publication.track.mediaStreamTrack) {
              // Check if track is actually playing (has active media stream)
              const mediaStreamTrack = publication.track.mediaStreamTrack;
              if (mediaStreamTrack.readyState === 'live' && !mediaStreamTrack.muted) {
                setAgentReady(true);
                console.log('✅ Agent is speaking (audio track active)');
                return true;
              }
            }
          }
        }
        return false;
      };
      
      // Listen for track subscribed events (when agent starts publishing audio)
      const handleTrackSubscribed = (track: any, publication: any, participant: any) => {
        if (track.kind === 'audio' && !participant.isLocal) {
          // Wait a bit for track to be ready
          setTimeout(() => {
            if (checkAgentSpeaking()) {
              room.off('trackSubscribed', handleTrackSubscribed);
            }
          }, 100);
        }
      };
      
      room.on('trackSubscribed', handleTrackSubscribed);
      
      // Check immediately
      if (!checkAgentSpeaking()) {
        // Also check periodically for agent audio (in case event was missed)
        const intervalId = setInterval(() => {
          if (checkAgentSpeaking()) {
            clearInterval(intervalId);
            room.off('trackSubscribed', handleTrackSubscribed);
          }
        }, 500);
        
        // Cleanup interval after 30 seconds
        setTimeout(() => {
          clearInterval(intervalId);
          room.off('trackSubscribed', handleTrackSubscribed);
        }, 30000);
      }
      
      console.log('Room connected, enabling tracks...');
      // Wait for engine to be ready
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // Check camera permission before enabling
      try {
        const permissionStatus = await navigator.permissions.query({ 
          name: 'camera' as PermissionName 
        });
        console.log('Camera permission status:', permissionStatus.state);
        if (permissionStatus.state === 'denied') {
          console.warn('⚠️ Camera permission denied - video may not work');
          toast.warning('Camera permission denied. Please allow camera access in browser settings.');
        }
      } catch (error) {
        // Permissions API not supported or camera permission not queryable
        console.log('Could not query camera permission:', error);
      }
      
      // Enable tracks with retry
      const enableTrackWithRetry = async (
        enableFn: () => Promise<unknown>,
        trackName: string,
        maxRetries = 3
      ) => {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
          try {
            await enableFn();
            console.log(`${trackName} enabled successfully`);
            return true;
          } catch (error: unknown) {
            console.warn(`${trackName} enable attempt ${attempt} failed:`, error);
            if (attempt < maxRetries) {
              await new Promise(resolve => setTimeout(resolve, 500 * Math.pow(2, attempt - 1)));
            }
          }
        }
        return false;
      };

      // Enable microphone
      enableTrackWithRetry(
        () => room.localParticipant.setMicrophoneEnabled(true),
        'Microphone'
      ).catch(() => {});

      // Wait before enabling camera
      await new Promise(resolve => setTimeout(resolve, 500));

      // Enable camera (async - must await the promise)
      const cameraEnabled = await enableTrackWithRetry(
        () => room.localParticipant.setCameraEnabled(true),
        'Camera'
      );
      
      if (!cameraEnabled) {
        console.error('Failed to enable camera after retries');
        toast.error('Failed to enable camera. Please check browser permissions.');
      }
    },
    onDisconnected: (reason) => {
      console.warn('Room disconnected:', reason);
      toast.warning('Room disconnected. Click reconnect to continue.');
    },
    onError: (error) => {
      console.error('Room connection error:', error);
      toast.error(`Connection failed: ${error.message}`);
    },
  });

  // Fetch interview
  const { data: interview, isLoading } = useQuery<Interview>({
    queryKey: ['interview', interviewId],
    queryFn: () => interviewsApi.get(interviewId),
    enabled: !!interviewId,
    refetchInterval: (query) => {
      return query.state.data?.status === 'in_progress' ? 2000 : false;
    },
  });

  const canRespond = interview?.status === 'in_progress';
  const isCompleted = interview?.status === 'completed';

  // Fetch skill breakdown for completed interviews
  const { data: skillBreakdown, isLoading: skillBreakdownLoading } = useQuery({
    queryKey: ['interview-skills', interviewId],
    queryFn: () => interviewsApi.getInterviewSkills(interviewId),
    enabled: isCompleted && !!interviewId,
  });

  // Get voice token mutation
  const voiceTokenMutation = useMutation({
    mutationFn: async () => {
      const roomName = `interview-${interviewId}`;
      const response = await voiceApi.getToken({
        room_name: roomName,
        participant_name: user?.full_name || 'User',
        participant_identity: user?.id.toString() || '',
        can_publish: true,
        can_subscribe: true,
      });
      return response;
    },
    onSuccess: (data) => {
      setVoiceToken({ token: data.token, url: data.url });
      setShowVoiceVideo(true);
      toast.success('Voice token obtained. Connecting to room...');
    },
    onError: (error: any) => {
      console.error('Failed to get voice token:', error);
    },
  });

  // Start interview mutation
  const startMutation = useMutation({
    mutationFn: async () => {
      const data = await interviewsApi.start(interviewId);
      try {
        await voiceTokenMutation.mutateAsync();
      } catch (error) {
        console.warn('Voice token failed, continuing with text-only interview');
      }
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['interview', interviewId], data);
      setIsStarting(false);
      toast.success('Interview started!');
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to start interview');
      setIsStarting(false);
    },
  });

  // Complete mutation
  const completeMutation = useMutation({
    mutationFn: () => interviewsApi.complete(interviewId),
    onSuccess: (data) => {
      queryClient.setQueryData(['interview', interviewId], data);
      toast.success('Interview completed!');
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to complete interview');
    },
  });

  const handleStart = () => {
    setIsStarting(true);
    startMutation.mutate();
  };

  const handleComplete = () => {
    if (confirm('Are you sure you want to complete this interview?')) {
      completeMutation.mutate();
    }
  };

  // Audio test function - triggers interviewer to speak
  const testAudio = async () => {
    console.log('testAudio called', { roomInstance: !!roomInstance, state: roomState, isConnected });
    
    try {
      if (!roomInstance || !isConnected) {
        toast.error('Not connected to room yet. Please wait for connection.');
        return;
      }

      // Request microphone permission first (browser requirement)
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(track => track.stop()); // Stop immediately, we just needed permission

      // Send test audio request to interviewer via data channel
      const testMessage = JSON.stringify({ type: 'test_audio' });
      await roomInstance.localParticipant.publishData(
        new TextEncoder().encode(testMessage),
        { reliable: true }
      );

      toast.info('Sent test request to interviewer. Listen for greeting...');
      
      // Check if interviewer audio tracks are available
      let hasAudioTracks = false;
      for (const participant of roomInstance.remoteParticipants.values()) {
        const audioPublications = Array.from(participant.trackPublications.values()).filter(
          pub => pub.kind === 'audio' && pub.isSubscribed
        );
        if (audioPublications.length > 0) {
          hasAudioTracks = true;
          break;
        }
      }

      if (!hasAudioTracks) {
        toast.warning('Waiting for interviewer audio tracks. The interviewer should speak shortly...');
      }
    } catch (error: any) {
      console.error('Audio test failed:', error);
      toast.error(
        error.name === 'NotAllowedError'
          ? 'Please allow microphone access to test audio'
          : `Audio test failed: ${error.message}`
      );
    }
  };

  if (isLoading) {
    return (
      <div className="h-screen flex flex-col">
        <Skeleton className="h-16 w-full" />
        <div className="flex-1 flex">
          <Skeleton className="w-96 h-full" />
          <Skeleton className="flex-1 h-full" />
        </div>
      </div>
    );
  }

  if (!interview) {
    return (
      <div className="h-screen flex items-center justify-center">
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">Interview not found</p>
            <Button asChild className="mt-4" variant="outline">
              <Link href="/dashboard/interviews">Back to Interviews</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Top Navigation Bar with Buttons */}
      <div className="border-b border-border bg-background px-4 py-3 flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/dashboard/interviews">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h1 className="text-lg font-semibold">{interview.title}</h1>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          {interview.status === 'pending' && (
            <Button
              onClick={handleStart}
              disabled={isStarting || startMutation.isPending}
            >
              {isStarting || startMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Start Interview
                </>
              )}
            </Button>
          )}
          {canRespond && !showVoiceVideo && (
            <Button
              variant="outline"
              onClick={() => voiceTokenMutation.mutate()}
              disabled={voiceTokenMutation.isPending}
            >
              {voiceTokenMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Connecting...
                </>
              ) : (
                <>
                  <Video className="mr-2 h-4 w-4" />
                  Enable Video
                </>
              )}
            </Button>
          )}
          {canRespond && showVoiceVideo && (
            <>
              {isConnecting && (
                <Button variant="outline" disabled>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Connecting...
                </Button>
              )}
              {roomState === 'disconnected' && (
                <Button
                  variant="default"
                  onClick={reconnectRoom}
                  title="Reconnect to room"
                  disabled={isConnecting}
                >
                  {isConnecting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Reconnecting...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      Reconnect
                    </>
                  )}
                </Button>
              )}
              {isConnected && roomInstance && (
                <Button
                  variant="outline"
                  onClick={testAudio}
                  title="Test audio playback"
                >
                  <Volume2 className="mr-2 h-4 w-4" />
                  Test Audio
                </Button>
              )}
            </>
          )}
          {canRespond && (
            <Button
              variant="outline"
              onClick={handleComplete}
              disabled={completeMutation.isPending}
            >
              {completeMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Completing...
                </>
              ) : (
                <>
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                  Complete
                </>
              )}
            </Button>
          )}
        </div>
      </div>

      {/* Disconnect Banner - Always visible at top when disconnected */}
      {showVoiceVideo && roomState === 'disconnected' && (
        <div className="bg-destructive text-white px-4 py-3 flex items-center justify-between border-b border-destructive/20 shadow-lg">
          <div className="flex items-center space-x-3">
            <AlertCircle className="h-5 w-5 shrink-0" />
            <div>
              <p className="font-semibold text-sm">Room Disconnected</p>
              <p className="text-xs text-destructive-foreground/80">
                Your connection to the interview room has been lost. Click reconnect to continue.
              </p>
            </div>
          </div>
          <Button 
            size="sm" 
            variant="secondary"
            className="bg-white text-destructive hover:bg-white/90 font-semibold"
            onClick={reconnectRoom}
            disabled={isConnecting}
          >
            {isConnecting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Reconnecting...
              </>
            ) : (
              <>
                <RefreshCw className="mr-2 h-4 w-4" />
                Reconnect Now
              </>
            )}
          </Button>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex min-h-0">
        {isCompleted ? (
          <Tabs defaultValue="skills" className="flex-1 flex flex-col min-h-0 w-full">
            <div className="border-b border-border px-4 pt-4">
              <TabsList>
                <TabsTrigger value="skills">Skill Breakdown</TabsTrigger>
                <TabsTrigger value="transcript">Transcript</TabsTrigger>
              </TabsList>
            </div>
            
            <TabsContent value="skills" className="flex-1 overflow-y-auto p-4 mt-0">
              {skillBreakdownLoading ? (
                <div className="space-y-4">
                  <Card>
                    <CardContent className="p-6">
                      <Skeleton className="h-64 w-full" />
                    </CardContent>
                  </Card>
                </div>
              ) : skillBreakdown ? (
                <InterviewSkillCard breakdown={skillBreakdown} />
              ) : (
                <Card>
                  <CardContent className="p-12 text-center">
                    <p className="text-muted-foreground">
                      Skill breakdown not available yet. The analysis may still be processing.
                    </p>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
            
            <TabsContent value="transcript" className="flex-1 overflow-y-auto p-4 mt-0">
              <Card className="h-full">
                <CardContent className="p-6">
                  <h3 className="font-semibold mb-4">Interview Transcript</h3>
                  <div className="space-y-4">
                    {interview.conversation_history && interview.conversation_history.length > 0 ? (
                      interview.conversation_history
                        .filter(msg => msg.role !== 'system')
                        .map((msg, idx) => (
                          <div
                            key={idx}
                            className={`p-3 rounded-lg ${
                              msg.role === 'user'
                                ? 'bg-primary/10 ml-8'
                                : 'bg-muted mr-8'
                            }`}
                          >
                            <div className="font-semibold text-sm mb-1">
                              {msg.role === 'user' ? 'You' : 'Interviewer'}
                            </div>
                            <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
                            {msg.timestamp && (
                              <div className="text-xs text-muted-foreground mt-1">
                                {new Date(msg.timestamp).toLocaleString()}
                              </div>
                            )}
                          </div>
                        ))
                    ) : (
                      <p className="text-sm text-muted-foreground text-center py-4">
                        No transcript available.
                      </p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        ) : (
          <>
            {/* Left Side - 1/3 width (Video Area + Transcription) */}
            <div className="w-1/3 border-r border-border flex flex-col">
              {/* Connection Status Banner */}
              {showVoiceVideo && roomState === 'disconnected' && (
                <div className="bg-destructive/10 border-b border-destructive/20 px-4 py-3 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <AlertCircle className="h-5 w-5 text-destructive" />
                    <span className="text-sm font-medium text-destructive">Room disconnected. Click reconnect to continue.</span>
                  </div>
                  <Button 
                    size="sm" 
                    variant="default"
                    className="bg-destructive hover:bg-destructive/90 text-white"
                    onClick={reconnectRoom}
                    disabled={isConnecting}
                  >
                    {isConnecting ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Reconnecting...
                      </>
                    ) : (
                      <>
                        <RefreshCw className="mr-2 h-4 w-4" />
                        Reconnect
                      </>
                    )}
                  </Button>
                </div>
              )}
              {showVoiceVideo && isConnecting && (
                <div className="bg-blue-500/10 border-b border-blue-500/20 px-4 py-2 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                    <span className="text-sm text-blue-600">Connecting to room...</span>
                  </div>
                </div>
              )}
              {/* Show "Interviewer is preparing" when connected but agent not ready yet */}
              {showVoiceVideo && isConnected && roomInstance && !agentReady && (
                <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Loader2 className="h-4 w-4 animate-spin text-amber-600" />
                    <span className="text-sm text-amber-700">Interviewer is preparing... Please wait a moment.</span>
                  </div>
                </div>
              )}
              
              {canRespond && showVoiceVideo && voiceToken ? (
            <>
              {/* Top Row: Participant Video | Interviewer Avatar side by side */}
              <div className="h-64 p-4 grid grid-cols-2 gap-4">
                {/* Left Column: Participant Video */}
                <ParticipantVideo 
                  room={roomInstance} 
                  userName={user?.full_name || 'You'}
                />
                
                {/* Right Column: Interviewer Avatar with Waves */}
                <AvatarWithWaves room={roomInstance} />
              </div>
              
              {/* Room Controls (Mute/Video) - Only show when connected */}
              {isConnected && (
                <div className="px-4 pb-2">
                  <RoomControls room={roomInstance} />
                </div>
              )}
              
              {/* Bottom: Real-time Transcription */}
              <div className="flex-1 min-h-0 p-4 pt-0">
                <TranscriptionDisplay room={roomInstance} />
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col p-4 space-y-4">
              {/* Placeholder state */}
              <div className="h-64 grid grid-cols-2 gap-4">
                <Card className="flex items-center justify-center">
                  <CardContent className="text-center">
                    <p className="text-sm font-medium mb-2">Your Video</p>
                    <p className="text-xs text-muted-foreground">
                      {canRespond ? 'Enable video to start' : 'Start interview to begin'}
                    </p>
                  </CardContent>
                </Card>
                    <Card className="flex items-center justify-center bg-primary/5">
                      <CardContent className="text-center">
                        <p className="text-sm font-medium mb-2">Interviewer</p>
                        <p className="text-xs text-muted-foreground">Will appear when connected</p>
                      </CardContent>
                    </Card>
              </div>
              
              {canRespond && !showVoiceVideo && (
                <div className="flex justify-center">
                  <Button
                    onClick={() => voiceTokenMutation.mutate()}
                    disabled={voiceTokenMutation.isPending}
                  >
                    {voiceTokenMutation.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Connecting...
                      </>
                    ) : (
                      <>
                        <Video className="mr-2 h-4 w-4" />
                        Enable Video
                      </>
                    )}
                  </Button>
                </div>
              )}
              
              <div className="flex-1">
                <Card>
                  <CardContent className="h-full flex items-center justify-center">
                    <p className="text-sm text-muted-foreground text-center">
                      Transcription will appear here once the interview starts
                    </p>
                  </CardContent>
                </Card>
              </div>
            </div>
              )}
            </div>

            {/* Right Side - 2/3 width (Sandbox) */}
            <div className="w-2/3 min-w-0 p-4">
              {canRespond ? (
                <CodeSandbox interviewId={interviewId} />
              ) : (
                <div className="h-full flex items-center justify-center">
                  <Card>
                    <CardContent className="py-12 text-center">
                      <p className="text-muted-foreground">
                        Start the interview to access the code editor
                      </p>
                    </CardContent>
                  </Card>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
