'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

interface SkillAveragesCardProps {
  averages: {
    communication: number;
    technical: number;
    problem_solving: number;
    code_quality: number;
  };
  previousAverages?: {
    communication: number;
    technical: number;
    problem_solving: number;
    code_quality: number;
  };
  title?: string;
  description?: string;
}

export function SkillAveragesCard({ 
  averages, 
  previousAverages,
  title = 'Average Skill Scores',
  description 
}: SkillAveragesCardProps) {
  const skills = [
    { key: 'communication' as const, label: 'Communication', color: 'bg-blue-500' },
    { key: 'technical' as const, label: 'Technical', color: 'bg-green-500' },
    { key: 'problem_solving' as const, label: 'Problem Solving', color: 'bg-yellow-500' },
    { key: 'code_quality' as const, label: 'Code Quality', color: 'bg-red-500' },
  ];

  const getTrend = (current: number, previous?: number) => {
    if (!previous) return null;
    const diff = current - previous;
    if (Math.abs(diff) < 0.01) return 'stable';
    return diff > 0 ? 'up' : 'down';
  };

  const getTrendIcon = (trend: 'up' | 'down' | 'stable' | null) => {
    if (trend === 'up') return <TrendingUp className="h-4 w-4 text-green-500" />;
    if (trend === 'down') return <TrendingDown className="h-4 w-4 text-red-500" />;
    if (trend === 'stable') return <Minus className="h-4 w-4 text-gray-500" />;
    return null;
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600';
    if (score >= 0.6) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {skills.map((skill) => {
            const score = averages[skill.key];
            const percentage = Math.round(score * 100);
            const previousScore = previousAverages?.[skill.key];
            const trend = getTrend(score, previousScore);
            const trendDiff = previousScore ? Math.round((score - previousScore) * 100) : null;

            return (
              <div
                key={skill.key}
                className="p-4 border rounded-lg hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <div className={`w-3 h-3 rounded-full ${skill.color}`} />
                    <span className="font-medium">{skill.label}</span>
                  </div>
                  {trend && trendDiff !== null && (
                    <div className="flex items-center space-x-1">
                      {getTrendIcon(trend)}
                      <span className={`text-sm ${trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : 'text-gray-600'}`}>
                        {Math.abs(trendDiff)}%
                      </span>
                    </div>
                  )}
                </div>
                <div className="flex items-baseline space-x-2">
                  <span className={`text-3xl font-bold ${getScoreColor(score)}`}>
                    {percentage}%
                  </span>
                  {previousScore && (
                    <span className="text-sm text-muted-foreground">
                      (was {Math.round(previousScore * 100)}%)
                    </span>
                  )}
                </div>
                {/* Progress bar */}
                <div className="mt-2 w-full bg-gray-200 rounded-full h-2">
                  <div
                    className={`${skill.color} h-2 rounded-full transition-all duration-300`}
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}





