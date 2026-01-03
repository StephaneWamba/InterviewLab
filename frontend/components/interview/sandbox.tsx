'use client';

import { useState, useEffect, useRef } from 'react';
import { useParams } from 'next/navigation';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Code, Play, Loader2, CheckCircle2, XCircle, Copy, Download, Send } from 'lucide-react';
import { toast } from 'sonner';
import dynamic from 'next/dynamic';
import { interviewsApi, Interview } from '@/lib/api/interviews';

// Dynamically import Monaco Editor to avoid SSR issues
const MonacoEditor = dynamic(() => import('@monaco-editor/react'), {
  ssr: false,
  loading: () => (
    <div className="h-full flex items-center justify-center bg-muted rounded-md">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  ),
});

interface ExecutionResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  execution_time_ms: number;
  success: boolean;
  error?: string;
}

interface CodeSandboxProps {
  interviewId?: number;
}

export function CodeSandbox({ interviewId }: CodeSandboxProps) {
  const params = useParams();
  const id = interviewId || parseInt(params.id as string);
  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('python');
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [exerciseDescription, setExerciseDescription] = useState<string | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const lastCodeRef = useRef<string>('');

  // Fetch interview to get exercise if available
  const { data: interview } = useQuery<Interview>({
    queryKey: ['interview', id],
    queryFn: () => interviewsApi.get(id),
    enabled: !!id,
    refetchInterval: (query) => {
      return query.state.data?.status === 'in_progress' ? 2000 : false;
    },
  });

  // Initialize code from exercise or default (only once when interview starts)
  const [codeInitialized, setCodeInitialized] = useState(false);
  
  useEffect(() => {
    if (interview && interview.status === 'in_progress' && !codeInitialized) {
      // Check if there's an exercise in conversation history
      // Look for sandbox_guidance messages with exercise metadata
      const exerciseMessage = interview.conversation_history?.find(
        (msg) => msg.role === 'assistant' && 
                 (msg.metadata?.type === 'sandbox_guidance' || 
                  msg.content?.toLowerCase().includes('exercise') ||
                  msg.content?.toLowerCase().includes('sandbox'))
      );
      
      // For now, use default code - exercise will be set by agent via state
      // In production, agent would set initial_code in state which frontend would fetch
      const defaultCode = `def fibonacci(n):
    """Calculate the nth Fibonacci number."""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

# Test the function
print(fibonacci(10))`;
      
      setCode(defaultCode);
      lastCodeRef.current = defaultCode;
      setCodeInitialized(true);
    }
    
    // Reset when interview changes
    if (interview?.status !== 'in_progress') {
      setCodeInitialized(false);
    }
  }, [interview?.status, interview?.id, codeInitialized]);

  // Poll for code changes when sandbox is active
  useEffect(() => {
    if (interview?.status === 'in_progress' && id) {
      pollingIntervalRef.current = setInterval(async () => {
        const currentCode = code.trim();
        if (currentCode && currentCode !== lastCodeRef.current) {
          try {
            const response = await interviewsApi.updateSandboxCode(id, currentCode);
            lastCodeRef.current = currentCode;
            // If agent provided guidance, show it
            if (response.has_guidance) {
              // Guidance would be in interview.current_message
              // Frontend should refetch interview to get updated message
            }
          } catch (error) {
            // Silently fail - polling is best effort
            console.debug('Polling update failed:', error);
          }
        }
      }, 10000); // Poll every 10 seconds

      return () => {
        if (pollingIntervalRef.current) {
          clearInterval(pollingIntervalRef.current);
        }
      };
    }
  }, [interview?.status, id, code]);

  // Execute code in sandbox to show results
  const executeCodeMutation = useMutation({
    mutationFn: async (data: { code: string; language: string }) => {
      const { apiClient } = await import('@/lib/api/client');
      return apiClient.post<ExecutionResult>('/api/v1/sandbox/execute', {
        code: data.code,
        language: data.language,
      });
    },
    onSuccess: (data: ExecutionResult) => {
      // Always show execution result in the right pane
      setResult(data);
      if (data.success && data.exit_code === 0) {
        toast.success('Code executed successfully!');
      } else {
        toast.error(data.error || 'Code execution failed');
      }
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to execute code');
      setResult({
        stdout: '',
        stderr: error.message || 'Execution failed',
        exit_code: 1,
        execution_time_ms: 0,
        success: false,
        error: error.message,
      });
    },
  });

  // Submit code to interview (for review by agent) - only if interview ID exists
  const submitCodeMutation = useMutation({
    mutationFn: async (data: { code: string; language: string }) => {
      if (id) {
        return interviewsApi.submitCode(id, data.code, data.language);
      }
      return Promise.resolve(null);
    },
    onSuccess: () => {
      if (id) {
        toast.success('Code submitted to interviewer for review!');
      }
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to submit code to interviewer');
    },
  });

  const handleRun = async () => {
    if (!code.trim()) {
      toast.error('Please enter some code');
      return;
    }
    
    // Execute code to show results in right pane
    executeCodeMutation.mutate({ code, language });
  };

  const handleSubmit = async () => {
    if (!code.trim()) {
      toast.error('Please enter some code');
      return;
    }
    
    // Only submit to interview (for agent review) - don't execute
    if (id) {
      submitCodeMutation.mutate({ code, language });
    } else {
      toast.error('No interview ID found');
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    toast.success('Code copied to clipboard!');
  };

  const handleDownload = () => {
    const extension = language === 'python' ? 'py' : 'js';
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `code.${extension}`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Code downloaded!');
  };

  const languageOptions = [
    { value: 'python', label: 'Python' },
    { value: 'javascript', label: 'JavaScript' },
  ];

  const getLanguageForEditor = (lang: string) => {
    return lang === 'python' ? 'python' : 'javascript';
  };

  return (
    <div className="h-full flex flex-col">
      <Card className="flex-1 flex flex-col">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <CardTitle className="flex items-center">
                <Code className="mr-2 h-5 w-5" />
                Code Sandbox
              </CardTitle>
              {exerciseDescription && (
                <p className="text-sm text-muted-foreground mt-1">
                  {exerciseDescription}
                </p>
              )}
            </div>
            <div className="flex items-center space-x-2">
              <Select value={language} onValueChange={setLanguage}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {languageOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm" onClick={handleCopy}>
                <Copy className="h-4 w-4" />
              </Button>
              <Button variant="outline" size="sm" onClick={handleDownload}>
                <Download className="h-4 w-4" />
              </Button>
              <Button
                onClick={handleRun}
                disabled={executeCodeMutation.isPending || !code.trim()}
                size="sm"
                variant="default"
              >
                {executeCodeMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-1" />
                    Run
                  </>
                )}
              </Button>
              {id && (
                <Button
                  onClick={handleSubmit}
                  disabled={submitCodeMutation.isPending || !code.trim()}
                  size="sm"
                  variant="outline"
                >
                  {submitCodeMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <Send className="h-4 w-4 mr-1" />
                      Submit
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col min-h-0">
          <div className="grid gap-4 flex-1 min-h-0" style={{ gridTemplateColumns: '2fr 1fr' }}>
            {/* Code Editor - 2/3 width */}
            <div className="border rounded-md overflow-hidden min-h-0">
              <MonacoEditor
                height="100%"
                language={getLanguageForEditor(language)}
                value={code}
                onChange={(value) => setCode(value || '')}
                theme="vs-dark"
                options={{
                  minimap: { enabled: false },
                  fontSize: 14,
                  lineNumbers: 'on',
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                  tabSize: 2,
                  wordWrap: 'on',
                }}
              />
            </div>

            {/* Output - 1/3 width */}
            <div className="min-h-0 flex flex-col">
              {result ? (
                <Tabs defaultValue="stdout" className="w-full h-full flex flex-col">
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="stdout">Output</TabsTrigger>
                    <TabsTrigger value="stderr">Errors</TabsTrigger>
                  </TabsList>
                  <TabsContent value="stdout" className="flex-1 min-h-0 mt-2">
                    <div className="bg-muted rounded-md p-4 h-full overflow-auto">
                      <pre className="text-sm font-mono whitespace-pre-wrap">
                        {result.stdout || '(no output)'}
                      </pre>
                    </div>
                    <div className="mt-2 flex flex-col space-y-1 text-sm text-muted-foreground">
                      <div className="flex items-center space-x-2">
                        <span>Exit Code: {result.exit_code}</span>
                        {result.exit_code === 0 ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-500" />
                        )}
                      </div>
                      <span>Time: {(result.execution_time_ms / 1000).toFixed(3)}s</span>
                    </div>
                  </TabsContent>
                  <TabsContent value="stderr" className="flex-1 min-h-0 mt-2">
                    <div className="bg-destructive/10 border border-destructive/20 rounded-md p-4 h-full overflow-auto">
                      <pre className="text-sm font-mono whitespace-pre-wrap text-destructive">
                        {result.stderr || '(no errors)'}
                      </pre>
                    </div>
                  </TabsContent>
                </Tabs>
              ) : (
                <div className="bg-muted rounded-md p-4 h-full flex items-center justify-center">
                  <p className="text-muted-foreground text-center text-sm">Run your code to see the output here</p>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

