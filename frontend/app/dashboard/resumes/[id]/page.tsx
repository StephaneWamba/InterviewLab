'use client';

import { useParams, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowLeft, FileText, AlertCircle } from 'lucide-react';
import { resumesApi } from '@/lib/api/resumes';
import { ResumeDisplay } from '@/components/resume/resume-display';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2 } from 'lucide-react';

interface Resume {
  id: number;
  file_name: string;
  file_size: number;
  file_type: string;
  analysis_status: 'pending' | 'processing' | 'completed' | 'failed';
  created_at: string;
  extracted_data?: any;
}

export default function ResumeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const resumeId = parseInt(params.id as string);

  // Fetch resume
  const { data: resume, isLoading } = useQuery<Resume>({
    queryKey: ['resume', resumeId],
    queryFn: () => resumesApi.get(resumeId),
    enabled: !!resumeId,
  });

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-5xl mx-auto space-y-6">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  if (!resume) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-5xl mx-auto">
          <Card>
            <CardContent className="py-12 text-center">
              <AlertCircle className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <p className="text-muted-foreground">Resume not found</p>
              <Button asChild className="mt-4" variant="outline">
                <Link href="/dashboard/resumes">Back to Resumes</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  if (resume.analysis_status !== 'completed') {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-5xl mx-auto">
          <div className="mb-6">
            <Button variant="ghost" size="sm" asChild>
              <Link href="/dashboard/resumes">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Resumes
              </Link>
            </Button>
          </div>
          <Card>
            <CardContent className="py-12 text-center">
              <AlertCircle className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <p className="text-muted-foreground">
                Resume analysis is {resume.analysis_status === 'processing' ? 'in progress' : resume.analysis_status}.
                Please check back later.
              </p>
              <Button asChild className="mt-4" variant="outline">
                <Link href="/dashboard/resumes">Back to Resumes</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  if (!resume.extracted_data) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="max-w-5xl mx-auto">
          <div className="mb-6">
            <Button variant="ghost" size="sm" asChild>
              <Link href="/dashboard/resumes">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Resumes
              </Link>
            </Button>
          </div>
          <Card>
            <CardContent className="py-12 text-center">
              <AlertCircle className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <p className="text-muted-foreground">
                No extracted data available for this resume.
              </p>
              <Button asChild className="mt-4" variant="outline">
                <Link href="/dashboard/resumes">Back to Resumes</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header Bar */}
      <div className="border-b border-border bg-background sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button variant="ghost" size="sm" asChild>
                <Link href="/dashboard/resumes">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back
                </Link>
              </Button>
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-muted-foreground" />
                <h1 className="text-lg font-semibold">{resume.file_name}</h1>
              </div>
            </div>
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span>{formatFileSize(resume.file_size)}</span>
              <span>•</span>
              <span>{new Date(resume.created_at).toLocaleDateString()}</span>
              <Badge variant="default" className="bg-green-500">
                <CheckCircle2 className="mr-1 h-3 w-3" />
                Analyzed
              </Badge>
            </div>
          </div>
        </div>
      </div>

      {/* Resume Content */}
      <div className="p-8">
        <ResumeDisplay 
          resumeData={resume.extracted_data} 
          fileName={resume.file_name}
        />
      </div>
    </div>
  );
}





