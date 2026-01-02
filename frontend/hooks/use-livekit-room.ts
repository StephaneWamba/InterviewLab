import { useEffect, useRef, useState, useCallback } from 'react';
import { Room, RoomEvent } from 'livekit-client';

type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'error';

interface UseLiveKitRoomOptions {
  token?: string | null;
  url?: string | null;
  onConnected?: (room: Room) => void;
  onDisconnected?: (reason?: string) => void;
  onError?: (error: Error) => void;
}

export function useLiveKitRoom({
  token,
  url,
  onConnected,
  onDisconnected,
  onError,
}: UseLiveKitRoomOptions) {
  const roomRef = useRef<Room | null>(null);
  const mountedRef = useRef(false);
  const connectingRef = useRef(false);
  const remoteAudioElementRef = useRef<HTMLAudioElement | null>(null);

  const [state, setState] = useState<ConnectionState>('idle');
  const [error, setError] = useState<Error | null>(null);

  /** Create room only once */
  const getOrCreateRoom = useCallback(() => {
    if (!roomRef.current) {
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });

      // Set up audio element for remote participant (agent)
      if (!remoteAudioElementRef.current) {
        const audioElement = document.createElement('audio');
        audioElement.autoplay = true;
        audioElement.setAttribute('playsinline', 'true');
        document.body.appendChild(audioElement);
        remoteAudioElementRef.current = audioElement;
      }

      // Handle audio track subscription for agent
      room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
        if (track.kind === 'audio' && !participant.isLocal && remoteAudioElementRef.current) {
          track.attach(remoteAudioElementRef.current);
          remoteAudioElementRef.current.play().catch((e) => {
            console.warn('Audio autoplay prevented:', e);
          });
        }
      });

      room.on(RoomEvent.Connected, () => {
        console.log('✅ LiveKit connected');
        setState('connected');
        if (onConnected && roomRef.current) {
          onConnected(roomRef.current);
        }
      });

      room.on(RoomEvent.Disconnected, (reason) => {
        console.warn('⚠️ LiveKit disconnected', reason);
        setState('disconnected');
        if (onDisconnected) {
          onDisconnected(reason);
        }
      });

      room.on(RoomEvent.ConnectionStateChanged, (connectionState) => {
        console.log('🔁 Connection state changed:', connectionState);
        if (connectionState === 'disconnected') {
          setState('disconnected');
        }
      });

      roomRef.current = room;
    }

    return roomRef.current;
  }, [onConnected, onDisconnected]);

  /** Connect */
  const connect = useCallback(async () => {
    if (!token || !url) return;
    if (connectingRef.current) {
      console.log('⏳ Already connecting, skipping...');
      return;
    }
    if (roomRef.current?.state === 'connected') {
      console.log('✅ Already connected, skipping...');
      return;
    }

    connectingRef.current = true;
    setState('connecting');
    setError(null);

    try {
      const room = getOrCreateRoom();
      await room.connect(url, token);
      // State will be updated by Connected event handler
    } catch (err) {
      console.error('❌ LiveKit connection failed', err);
      const error = err as Error;
      setError(error);
      setState('error');
      if (onError) {
        onError(error);
      }
    } finally {
      connectingRef.current = false;
    }
  }, [token, url, getOrCreateRoom, onError]);

  /** Manual reconnect */
  const reconnect = useCallback(async () => {
    console.log('🔄 Reconnecting...');
    if (roomRef.current) {
      roomRef.current.disconnect();
      roomRef.current = null;
    }
    // Clean up audio element
    if (remoteAudioElementRef.current?.parentNode) {
      remoteAudioElementRef.current.parentNode.removeChild(remoteAudioElementRef.current);
      remoteAudioElementRef.current = null;
    }
    await connect();
  }, [connect]);

  /** Disconnect manually */
  const disconnect = useCallback(() => {
    if (roomRef.current) {
      console.log('🔌 Disconnecting LiveKit room');
      roomRef.current.disconnect();
      roomRef.current = null;
      setState('disconnected');
    }
    // Clean up audio element
    if (remoteAudioElementRef.current?.parentNode) {
      remoteAudioElementRef.current.parentNode.removeChild(remoteAudioElementRef.current);
      remoteAudioElementRef.current = null;
    }
  }, []);

  /** Effect: connect when token appears */
  useEffect(() => {
    if (!token || !url) {
      setState('idle');
      return;
    }
    connect();
  }, [token, url, connect]);

  /** Effect: real unmount only - cleanup */
  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;

      if (roomRef.current) {
        console.log('🧹 Disconnecting LiveKit room (unmount)');
        roomRef.current.disconnect();
        roomRef.current = null;
      }

      // Clean up audio element
      if (remoteAudioElementRef.current?.parentNode) {
        remoteAudioElementRef.current.parentNode.removeChild(remoteAudioElementRef.current);
        remoteAudioElementRef.current = null;
      }
    };
  }, []);

  return {
    room: roomRef.current,
    state,
    error,
    connect,
    reconnect,
    disconnect,
    isConnected: state === 'connected',
    isConnecting: state === 'connecting',
  };
}

