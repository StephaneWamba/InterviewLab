'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/lib/store/auth-store';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Collapsible, CollapsibleContent, CollapsibleHeader } from '@/components/ui/collapsible';
import { FileText, MessageSquare, Code, TrendingUp, CheckCircle2, XCircle, Loader2, AlertCircle, BarChart3, Target, Clock, ChevronDown } from 'lucide-react';
import Link from 'next/link';
import { resumesApi } from '@/lib/api/resumes';
import { interviewsApi, Interview } from '@/lib/api/interviews';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { SkillAveragesCard } from '@/components/analytics/skill-averages-card';
import { SkillProgressionChart } from '@/components/analytics/skill-progression-chart';
import { InterviewSkillCard } from '@/components/analytics/interview-skill-card';
import { SkillComparison } from '@/components/analytics/skill-comparison';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';

interface Resume {
  id: number;
  file_name: string;
  file_size: number;
  file_type: string;
  analysis_status: 'pending' | 'processing' | 'completed' | 'failed';
  created_at: string;
  extracted_data?: any;
}

export default function DashboardPage() {
  const { user } = useAuthStore();
  const [isStatsOpen, setIsStatsOpen] = useState(false); // Collapsed by default
  const [selectedInterviewIds, setSelectedInterviewIds] = useState<number[]>([]);
  const queryClient = useQueryClient();

  // Fetch data
  const { data: resumes, isLoading: resumesLoading } = useQuery<Resume[]>({
    queryKey: ['resumes'],
    queryFn: () => resumesApi.list(),
  });

  const { data: interviews, isLoading: interviewsLoading } = useQuery({
    queryKey: ['interviews'],
    queryFn: () => interviewsApi.list(),
  });

  // Fetch skill analytics
  const { data: skillProgression, isLoading: progressionLoading } = useQuery({
    queryKey: ['skill-progression'],
    queryFn: () => interviewsApi.getSkillProgression(),
    enabled: !!interviews,
  });

  const { data: skillAverages, isLoading: averagesLoading } = useQuery({
    queryKey: ['skill-averages'],
    queryFn: () => interviewsApi.getSkillAverages(),
    enabled: !!interviews,
  });

  const { data: skillComparison, isLoading: comparisonLoading } = useQuery({
    queryKey: ['skill-comparison', selectedInterviewIds],
    queryFn: () => interviewsApi.compareSkillInterviews(selectedInterviewIds),
    enabled: selectedInterviewIds.length >= 2,
  });


  const completedInterviews = interviews?.filter((i) => i.status === 'completed') || [];
  const inProgressInterviews = interviews?.filter((i) => i.status === 'in_progress') || [];
  const totalTurns = interviews?.reduce((sum, i) => sum + i.turn_count, 0) || 0;
  const avgTurns = interviews && interviews.length > 0 
    ? Math.round(totalTurns / interviews.length) 
    : 0;

  const avgScore = completedInterviews.length > 0
    ? completedInterviews.reduce((sum, i) => {
        const score = i.feedback?.overall_score || 0;
        return sum + score;
      }, 0) / completedInterviews.length
    : 0;

  // Stats for collapsible section
  const stats = [
    {
      title: 'Total Interviews',
      value: interviews?.length || 0,
      icon: MessageSquare,
      description: 'All time',
    },
    {
      title: 'Completed',
      value: completedInterviews.length,
      icon: CheckCircle2,
      description: 'Finished interviews',
    },
    {
      title: 'In Progress',
      value: inProgressInterviews.length,
      icon: Clock,
      description: 'Active sessions',
    },
    {
      title: 'Average Score',
      value: `${Math.round(avgScore * 100)}%`,
      icon: Target,
      description: 'Based on completed',
    },
    {
      title: 'Total Turns',
      value: totalTurns,
      icon: TrendingUp,
      description: 'Conversation turns',
    },
    {
      title: 'Avg Turns',
      value: avgTurns,
      icon: BarChart3,
      description: 'Per interview',
    },
  ];

  const recentInterviews = interviews
    ?.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 3) || [];

  const toggleInterviewSelection = (interviewId: number) => {
    setSelectedInterviewIds(prev => {
      if (prev.includes(interviewId)) {
        return prev.filter(id => id !== interviewId);
      } else {
        if (prev.length >= 3) {
          return prev.slice(1).concat(interviewId);
        }
        return [...prev, interviewId];
      }
    });
  };

  const clearSelection = () => {
    setSelectedInterviewIds([]);
  };

  return (
    <div className="p-8 space-y-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          Welcome back, {user?.full_name?.split(' ')[0] || 'User'}!
        </h1>
        <p className="text-muted-foreground mt-2">
          Get ready for your next interview with AI-powered practice sessions.
        </p>
      </div>

      {/* Basic Stats Grid - Always Visible */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-8">
        {[
          {
            title: 'Resumes',
            value: resumesLoading ? '...' : (resumes?.length || 0).toString(),
            description: 'Uploaded resumes',
            icon: FileText,
            color: 'text-blue-600',
            bgColor: 'bg-blue-50 dark:bg-blue-950',
          },
          {
            title: 'Interviews',
            value: interviewsLoading ? '...' : (interviews?.length || 0).toString(),
            description: 'Practice sessions',
            icon: MessageSquare,
            color: 'text-green-600',
            bgColor: 'bg-green-50 dark:bg-green-950',
          },
          {
            title: 'Completed',
            value: interviewsLoading ? '...' : completedInterviews.length.toString(),
            description: 'Finished interviews',
            icon: Code,
            color: 'text-purple-600',
            bgColor: 'bg-purple-50 dark:bg-purple-950',
          },
          {
            title: 'Average Score',
            value: avgScore === 0 ? '--' : `${Math.round(avgScore * 100)}%`,
            description: 'Overall performance',
            icon: TrendingUp,
            color: 'text-orange-600',
            bgColor: 'bg-orange-50 dark:bg-orange-950',
          },
        ].map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.title} className="hover:shadow-md transition-shadow">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
                <div className={`${stat.bgColor} p-2 rounded-lg`}>
                  <Icon className={`h-4 w-4 ${stat.color}`} />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stat.value}</div>
                <p className="text-xs text-muted-foreground mt-1">{stat.description}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Collapsible Detailed Stats Section */}
      <Collapsible open={isStatsOpen} onOpenChange={setIsStatsOpen}>
        <CollapsibleHeader className="group cursor-pointer flex items-center justify-between p-4 rounded-lg hover:bg-muted/50 transition-colors">
          <span className="text-lg font-semibold">Detailed Statistics</span>
          <ChevronDown className={`h-5 w-5 text-muted-foreground transition-transform ${isStatsOpen ? 'rotate-180' : ''}`} />
        </CollapsibleHeader>
        <CollapsibleContent className="pt-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {stats.map((stat) => {
              const Icon = stat.icon;
              return (
                <Card key={stat.title}>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
                    <Icon className="h-4 w-4 text-muted-foreground" />
                  </CardHeader>
                  <CardContent>
                    {interviewsLoading ? (
                      <Skeleton className="h-8 w-20" />
                    ) : (
                      <>
                        <div className="text-2xl font-bold">{stat.value}</div>
                        <p className="text-xs text-muted-foreground mt-1">
                          {stat.description}
                        </p>
                      </>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-1">
        {/* Recent Interviews */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
            <CardDescription>Your latest interview sessions</CardDescription>
          </CardHeader>
          <CardContent>
            {interviewsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : recentInterviews.length > 0 ? (
              <div className="space-y-3">
                {recentInterviews.map((interview) => (
                  <Link
                    key={interview.id}
                    href={`/dashboard/interviews/${interview.id}`}
                    className="block p-3 border rounded-lg hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <h4 className="font-medium text-sm">{interview.title}</h4>
                        <p className="text-xs text-muted-foreground mt-1">
                          {format(new Date(interview.created_at), 'MMM d, yyyy')}
                        </p>
                      </div>
                      <div className="text-right">
                        <div className="text-xs font-medium">
                          {interview.status === 'completed' ? '✓' : interview.status === 'in_progress' ? '→' : '○'}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {interview.turn_count} turns
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
                <Button asChild variant="outline" className="w-full mt-2">
                  <Link href="/dashboard/interviews">View All Interviews</Link>
                </Button>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <p>No recent activity</p>
                <p className="text-sm mt-2">Start your first interview to see activity here</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Skill Analytics Section - Charts */}
      <div className="space-y-6 mt-8">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Skill Analytics</h2>
          <p className="text-muted-foreground mt-1">
            Track your performance and skill progression
          </p>
        </div>
        
        {completedInterviews.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <BarChart3 className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <h3 className="text-lg font-semibold mb-2">No completed interviews yet</h3>
              <p className="text-muted-foreground mb-4">
                Complete an interview to see your skill analytics and progression charts.
              </p>
              <Button asChild>
                <Link href="/dashboard/interviews">
                  Start an Interview
                </Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
        <div className="space-y-6">

          <Tabs defaultValue="overview" className="space-y-4">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="progression">Progression</TabsTrigger>
              <TabsTrigger value="comparison">Comparison</TabsTrigger>
              <TabsTrigger value="interviews">Interviews</TabsTrigger>
            </TabsList>

            {/* Overview Tab */}
            <TabsContent value="overview" className="space-y-6">
              {/* Skill Averages */}
              {averagesLoading ? (
                <Card>
                  <CardContent className="p-6">
                    <Skeleton className="h-64 w-full" />
                  </CardContent>
                </Card>
              ) : skillAverages ? (
                <SkillAveragesCard
                  averages={skillAverages}
                  title="Average Skill Scores"
                  description="Your average performance across all completed interviews"
                />
              ) : (
                <Card>
                  <CardContent className="p-6 text-center text-muted-foreground">
                    <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>No skill data available yet. Complete an interview to see your skill scores.</p>
                  </CardContent>
                </Card>
              )}

              {/* Skill Progression Chart */}
              {progressionLoading ? (
                <Card>
                  <CardContent className="p-6">
                    <Skeleton className="h-96 w-full" />
                  </CardContent>
                </Card>
              ) : skillProgression && (
                Object.values(skillProgression).some(skill => skill.length > 0) ? (
                  <SkillProgressionChart
                    data={skillProgression}
                    title="Skill Progression Over Time"
                    description="Track how your skills improve across interviews"
                  />
                ) : (
                  <Card>
                    <CardContent className="p-6 text-center text-muted-foreground">
                      <TrendingUp className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>Complete more interviews to see progression over time.</p>
                    </CardContent>
                  </Card>
                )
              )}
            </TabsContent>

            {/* Progression Tab */}
            <TabsContent value="progression" className="space-y-6">
              {progressionLoading ? (
                <Card>
                  <CardContent className="p-6">
                    <Skeleton className="h-96 w-full" />
                  </CardContent>
                </Card>
              ) : skillProgression && (
                Object.values(skillProgression).some(skill => skill.length > 0) ? (
                  <SkillProgressionChart
                    data={skillProgression}
                    title="Skill Progression Over Time"
                    description="Track how your skills improve across interviews"
                  />
                ) : (
                  <Card>
                    <CardContent className="p-6 text-center text-muted-foreground">
                      <TrendingUp className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>Complete more interviews to see progression over time.</p>
                    </CardContent>
                  </Card>
                )
              )}
            </TabsContent>

            {/* Comparison Tab */}
            <TabsContent value="comparison" className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Compare Interviews</CardTitle>
                  <CardDescription>
                    Select 2-3 completed interviews to compare skill scores
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {completedInterviews.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No completed interviews to compare.
                    </p>
                  ) : (
                    <>
                      <div className="max-h-64 overflow-y-auto space-y-2 border rounded-lg p-4">
                        {completedInterviews.map((interview) => (
                          <div key={interview.id} className="flex items-center space-x-2">
                            <Checkbox
                              id={`interview-${interview.id}`}
                              checked={selectedInterviewIds.includes(interview.id)}
                              onCheckedChange={() => toggleInterviewSelection(interview.id)}
                              disabled={!selectedInterviewIds.includes(interview.id) && selectedInterviewIds.length >= 3}
                            />
                            <Label
                              htmlFor={`interview-${interview.id}`}
                              className="flex-1 cursor-pointer flex items-center justify-between"
                            >
                              <span className="font-medium">{interview.title}</span>
                              <span className="text-sm text-muted-foreground">
                                {interview.completed_at 
                                  ? format(new Date(interview.completed_at), 'MMM d, yyyy')
                                  : format(new Date(interview.created_at), 'MMM d, yyyy')}
                              </span>
                            </Label>
                          </div>
                        ))}
                      </div>
                      
                      {selectedInterviewIds.length > 0 && (
                        <div className="flex items-center justify-between">
                          <p className="text-sm text-muted-foreground">
                            {selectedInterviewIds.length} interview(s) selected
                          </p>
                          <Button variant="outline" size="sm" onClick={clearSelection}>
                            Clear Selection
                          </Button>
                        </div>
                      )}

                      {selectedInterviewIds.length < 2 && (
                        <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg dark:bg-yellow-950 dark:border-yellow-900">
                          <p className="text-sm text-yellow-800 dark:text-yellow-200">
                            Select at least 2 interviews to compare.
                          </p>
                        </div>
                      )}
                    </>
                  )}
                </CardContent>
              </Card>

              {comparisonLoading ? (
                <Card>
                  <CardContent className="p-6">
                    <Skeleton className="h-96 w-full" />
                  </CardContent>
                </Card>
              ) : skillComparison && selectedInterviewIds.length >= 2 ? (
                <SkillComparison
                  comparison={skillComparison}
                  title="Interview Skill Comparison"
                  description="Compare your performance across selected interviews"
                />
              ) : selectedInterviewIds.length >= 2 ? (
                <Card>
                  <CardContent className="p-6 text-center text-muted-foreground">
                    <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>Loading comparison data...</p>
                  </CardContent>
                </Card>
              ) : null}
            </TabsContent>

            {/* Individual Interviews Tab */}
            <TabsContent value="interviews" className="space-y-6">
              {completedInterviews.length === 0 ? (
                <Card>
                  <CardContent className="p-12 text-center">
                    <MessageSquare className="h-12 w-12 text-muted-foreground mx-auto mb-4 opacity-50" />
                    <h3 className="text-lg font-semibold mb-2">No completed interviews</h3>
                    <p className="text-muted-foreground">
                      Complete an interview to see detailed skill breakdowns
                    </p>
                  </CardContent>
                </Card>
              ) : (
                completedInterviews.map((interview) => (
                  <InterviewSkillBreakdown key={interview.id} interviewId={interview.id} />
                ))
              )}
            </TabsContent>
          </Tabs>
        </div>
        )}
      </div>
    </div>
  );
}

// Component to fetch and display individual interview skill breakdown
function InterviewSkillBreakdown({ interviewId }: { interviewId: number }) {
  const { data: skillBreakdown, isLoading } = useQuery({
    queryKey: ['interview-skills', interviewId],
    queryFn: () => interviewsApi.getInterviewSkills(interviewId),
  });

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!skillBreakdown) {
    return (
      <Card>
        <CardContent className="p-6 text-center text-muted-foreground">
          <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>Skill breakdown not available for this interview.</p>
        </CardContent>
      </Card>
    );
  }

  return <InterviewSkillCard breakdown={skillBreakdown} />;
}
