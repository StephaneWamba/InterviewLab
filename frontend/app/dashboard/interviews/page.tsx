'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { MessageSquare, Plus, Play, CheckCircle2, Clock, XCircle, Loader2, Trash2 } from 'lucide-react';
import { interviewsApi, Interview } from '@/lib/api/interviews';
import { resumesApi } from '@/lib/api/resumes';
import { toast } from 'sonner';
import { format } from 'date-fns';

export default function InterviewsPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newInterview, setNewInterview] = useState({ title: '', resume_id: 'none', job_description: '' });
  const queryClient = useQueryClient();

  // Fetch interviews
  const { data: interviews, isLoading } = useQuery<Interview[]>({
    queryKey: ['interviews'],
    queryFn: () => interviewsApi.list(),
  });

  // Fetch resumes for dropdown
  const { data: resumes } = useQuery({
    queryKey: ['resumes'],
    queryFn: () => resumesApi.list(),
  });

  // Create interview mutation
  const createMutation = useMutation({
    mutationFn: (data: { title: string; resume_id?: number; job_description?: string }) =>
      interviewsApi.create(data),
    onSuccess: () => {
      toast.success('Interview created successfully!');
      queryClient.invalidateQueries({ queryKey: ['interviews'] });
      setIsCreateOpen(false);
      setNewInterview({ title: '', resume_id: 'none', job_description: '' });
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create interview');
    },
  });

  // Delete interview mutation
  const deleteMutation = useMutation({
    mutationFn: (interviewId: number) => interviewsApi.delete(interviewId),
    onSuccess: () => {
      toast.success('Interview deleted successfully');
      queryClient.invalidateQueries({ queryKey: ['interviews'] });
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to delete interview');
    },
  });

  const handleDelete = (interviewId: number, interviewTitle: string) => {
    if (confirm(`Are you sure you want to delete "${interviewTitle}"? This action cannot be undone.`)) {
      deleteMutation.mutate(interviewId);
    }
  };

  const handleCreate = () => {
    if (!newInterview.title.trim()) {
      toast.error('Please enter an interview title');
      return;
    }
    createMutation.mutate({
      title: newInterview.title,
      resume_id: newInterview.resume_id && newInterview.resume_id !== 'none' 
        ? parseInt(newInterview.resume_id) 
        : undefined,
      job_description: newInterview.job_description.trim() || undefined,
    });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <Badge variant="default" className="bg-green-500">
            <CheckCircle2 className="mr-1 h-3 w-3" />
            Completed
          </Badge>
        );
      case 'in_progress':
        return (
          <Badge variant="secondary">
            <Play className="mr-1 h-3 w-3" />
            In Progress
          </Badge>
        );
      case 'pending':
        return (
          <Badge variant="outline">
            <Clock className="mr-1 h-3 w-3" />
            Pending
          </Badge>
        );
      default:
        return (
          <Badge variant="destructive">
            <XCircle className="mr-1 h-3 w-3" />
            Cancelled
          </Badge>
        );
    }
  };

  return (
    <div className="p-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Interviews</h1>
          <p className="text-muted-foreground mt-2">
            Practice interviews with AI-powered questions
          </p>
        </div>
        <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Interview
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Interview</DialogTitle>
              <DialogDescription>
                Start a new practice interview session
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Interview Title</Label>
                <Input
                  id="title"
                  placeholder="e.g., Software Engineer Practice"
                  value={newInterview.title}
                  onChange={(e) =>
                    setNewInterview({ ...newInterview, title: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="resume">Resume (Optional)</Label>
                <Select
                  value={newInterview.resume_id}
                  onValueChange={(value) =>
                    setNewInterview({ ...newInterview, resume_id: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a resume" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No resume</SelectItem>
                    {resumes?.map((resume) => (
                      <SelectItem key={resume.id} value={resume.id.toString()}>
                        {resume.file_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="job_description">Job Description (Optional)</Label>
                <textarea
                  id="job_description"
                  className="flex min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  placeholder="Paste the job description here. The AI will use this to ask relevant questions and provide appropriate coding exercises."
                  value={newInterview.job_description}
                  onChange={(e) =>
                    setNewInterview({ ...newInterview, job_description: e.target.value })
                  }
                />
              </div>
              <Button
                onClick={handleCreate}
                disabled={createMutation.isPending}
                className="w-full"
              >
                {createMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Interview'
                )}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-4 w-1/2 mt-2" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-4 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : interviews && interviews.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {interviews.map((interview) => (
            <Card
              key={interview.id}
              className="hover:shadow-md transition-shadow"
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center space-x-2 flex-1 min-w-0">
                    <MessageSquare className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                    <CardTitle className="text-lg truncate">{interview.title}</CardTitle>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive flex-shrink-0"
                    onClick={() => handleDelete(interview.id, interview.title)}
                    disabled={deleteMutation.isPending}
                    title="Delete interview"
                  >
                    {deleteMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                <CardDescription>
                  {format(new Date(interview.created_at), 'MMM d, yyyy')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  {getStatusBadge(interview.status)}
                  <span className="text-sm text-muted-foreground">
                    {interview.turn_count} turns
                  </span>
                </div>
                {interview.status === 'pending' && (
                  <Button asChild className="w-full" size="sm">
                    <Link href={`/dashboard/interviews/${interview.id}`}>
                      <Play className="mr-2 h-4 w-4" />
                      Start Interview
                    </Link>
                  </Button>
                )}
                {interview.status === 'in_progress' && (
                  <Button asChild className="w-full" size="sm">
                    <Link href={`/dashboard/interviews/${interview.id}`}>
                      Continue Interview
                    </Link>
                  </Button>
                )}
                {interview.status === 'completed' && (
                  <div className="space-y-2">
                    <Button asChild variant="outline" className="w-full" size="sm">
                      <Link href={`/dashboard/interviews/${interview.id}`}>
                        View Details
                      </Link>
                    </Button>
                    {interview.feedback && (
                      <div className="text-xs text-muted-foreground">
                        Score: {interview.feedback.overall_score
                          ? `${Math.round(interview.feedback.overall_score * 100)}%`
                          : 'N/A'}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <MessageSquare className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No interviews yet</h3>
            <p className="text-muted-foreground text-center mb-4">
              Create your first interview to start practicing
            </p>
            <Button onClick={() => setIsCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Create Interview
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

