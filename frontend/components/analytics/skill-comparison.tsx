'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { SkillComparisonResponse } from '@/lib/api/interviews';
import { format } from 'date-fns';

interface SkillComparisonProps {
  comparison: SkillComparisonResponse;
  title?: string;
  description?: string;
}

export function SkillComparison({ comparison, title = 'Interview Comparison', description }: SkillComparisonProps) {
  // Build chart data
  const chartData = comparison.interviews.map(interview => {
    const interviewId = interview.id.toString();
    return {
      interview: interview.title.length > 20 
        ? `${interview.title.substring(0, 20)}...` 
        : interview.title,
      interviewId,
      date: interview.completed_at 
        ? format(new Date(interview.completed_at), 'MMM d')
        : 'N/A',
      'Communication': comparison.comparison.communication[interview.id] 
        ? Math.round(comparison.comparison.communication[interview.id] * 100)
        : 0,
      'Technical': comparison.comparison.technical[interview.id]
        ? Math.round(comparison.comparison.technical[interview.id] * 100)
        : 0,
      'Problem Solving': comparison.comparison.problem_solving[interview.id]
        ? Math.round(comparison.comparison.problem_solving[interview.id] * 100)
        : 0,
      'Code Quality': comparison.comparison.code_quality[interview.id]
        ? Math.round(comparison.comparison.code_quality[interview.id] * 100)
        : 0,
    };
  });

  const colors = {
    'Communication': '#3b82f6',
    'Technical': '#10b981',
    'Problem Solving': '#f59e0b',
    'Code Quality': '#ef4444',
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis 
              dataKey="interview"
              angle={-45}
              textAnchor="end"
              height={100}
              tick={{ fontSize: 12, fill: '#6b7280' }}
            />
            <YAxis 
              domain={[0, 100]}
              tick={{ fontSize: 12, fill: '#6b7280' }}
              label={{ value: 'Score (%)', angle: -90, position: 'insideLeft', style: { fill: '#6b7280' } }}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px' }}
              formatter={(value: number) => [`${value}%`, 'Score']}
            />
            <Legend />
            <Bar dataKey="Communication" fill={colors['Communication']} radius={[4, 4, 0, 0]} />
            <Bar dataKey="Technical" fill={colors['Technical']} radius={[4, 4, 0, 0]} />
            <Bar dataKey="Problem Solving" fill={colors['Problem Solving']} radius={[4, 4, 0, 0]} />
            <Bar dataKey="Code Quality" fill={colors['Code Quality']} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}


