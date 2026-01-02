'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Code, Play, Loader2, CheckCircle2, XCircle, Copy, Download } from 'lucide-react';
import { toast } from 'sonner';
import dynamic from 'next/dynamic';

// Dynamically import Monaco Editor to avoid SSR issues
const MonacoEditor = dynamic(() => import('@monaco-editor/react'), {
  ssr: false,
  loading: () => (
    <div className="h-[600px] flex items-center justify-center bg-muted rounded-md">
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

export default function SandboxPage() {
  const [code, setCode] = useState(`def fibonacci(n):
    """Calculate the nth Fibonacci number."""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

# Test the function
print(fibonacci(10))`);
  const [language, setLanguage] = useState('python');
  const [result, setResult] = useState<ExecutionResult | null>(null);

  const executeMutation = useMutation({
    mutationFn: async (data: { code: string; language: string }) => {
      const { apiClient } = await import('@/lib/api/client');
      return apiClient.post<ExecutionResult>('/api/v1/sandbox/execute', {
        code: data.code,
        language: data.language,
      });
    },
    onSuccess: (data: ExecutionResult) => {
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

  const handleExecute = () => {
    if (!code.trim()) {
      toast.error('Please enter some code');
      return;
    }
    executeMutation.mutate({ code, language });
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
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Code Sandbox</h1>
          <p className="text-muted-foreground mt-2">
            Write and test code in an isolated environment
          </p>
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
            <Copy className="mr-2 h-4 w-4" />
            Copy
          </Button>
          <Button variant="outline" size="sm" onClick={handleDownload}>
            <Download className="mr-2 h-4 w-4" />
            Download
          </Button>
          <Button
            onClick={handleExecute}
            disabled={executeMutation.isPending || !code.trim()}
          >
            {executeMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                Run Code
              </>
            )}
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Code Editor */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center">
              <Code className="mr-2 h-5 w-5" />
              Editor
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="border rounded-md overflow-hidden">
              <MonacoEditor
                height="600px"
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
          </CardContent>
        </Card>

        {/* Output */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Output</CardTitle>
          </CardHeader>
          <CardContent>
            {result ? (
              <Tabs defaultValue="stdout" className="w-full">
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="stdout">Output</TabsTrigger>
                  <TabsTrigger value="stderr">Errors</TabsTrigger>
                </TabsList>
                <TabsContent value="stdout" className="mt-4">
                  <div className="bg-muted rounded-md p-4 min-h-[500px] max-h-[500px] overflow-auto">
                    <pre className="text-sm font-mono whitespace-pre-wrap">
                      {result.stdout || '(no output)'}
                    </pre>
                  </div>
                  <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
                    <div className="flex items-center space-x-4">
                      <span>
                        Exit Code: {result.exit_code}
                        {result.exit_code === 0 ? (
                          <CheckCircle2 className="inline ml-2 h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="inline ml-2 h-4 w-4 text-red-500" />
                        )}
                      </span>
                      <span>Time: {(result.execution_time_ms / 1000).toFixed(3)}s</span>
                    </div>
                  </div>
                </TabsContent>
                <TabsContent value="stderr" className="mt-4">
                  <div className="bg-destructive/10 border border-destructive/20 rounded-md p-4 min-h-[500px] max-h-[500px] overflow-auto">
                    <pre className="text-sm font-mono whitespace-pre-wrap text-destructive">
                      {result.stderr || '(no errors)'}
                    </pre>
                  </div>
                </TabsContent>
              </Tabs>
            ) : (
              <div className="bg-muted rounded-md p-4 min-h-[500px] flex items-center justify-center">
                <p className="text-muted-foreground">
                  Run your code to see the output here
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

