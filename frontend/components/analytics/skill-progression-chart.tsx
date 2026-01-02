'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { format } from 'date-fns';

interface SkillProgressionChartProps {
  data: {
    communication: Array<{ interview_id: number; interview_title: string; date: string; score: number }>;
    technical: Array<{ interview_id: number; interview_title: string; date: string; score: number }>;
    problem_solving: Array<{ interview_id: number; interview_title: string; date: string; score: number }>;
    code_quality: Array<{ interview_id: number; interview_title: string; date: string; score: number }>;
  };
  title?: string;
  description?: string;
}

export function SkillProgressionChart({ data, title = 'Skill Progression Over Time', description }: SkillProgressionChartProps) {
  // Combine all skills into single timeline
  const allDates = new Set<string>();
  
  Object.values(data).forEach(skillData => {
    skillData.forEach(point => allDates.add(point.date));
  });

  const sortedDates = Array.from(allDates).sort();

  // Build combined data points
  const chartData = sortedDates.map(date => {
    const point: any = { date, formattedDate: format(new Date(date), 'MMM d, yyyy') };

    // Find scores for each skill at this date
    const commPoint = data.communication.find(p => p.date === date);
    const techPoint = data.technical.find(p => p.date === date);
    const probPoint = data.problem_solving.find(p => p.date === date);
    const codePoint = data.code_quality.find(p => p.date === date);

    point['Communication'] = commPoint ? Math.round(commPoint.score * 100) : null;
    point['Technical'] = techPoint ? Math.round(techPoint.score * 100) : null;
    point['Problem Solving'] = probPoint ? Math.round(probPoint.score * 100) : null;
    point['Code Quality'] = codePoint ? Math.round(codePoint.score * 100) : null;

    return point;
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
          <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis 
              dataKey="formattedDate" 
              tick={{ fontSize: 12, fill: '#6b7280' }}
              angle={-45}
              textAnchor="end"
              height={80}
            />
            <YAxis 
              domain={[0, 100]}
              tick={{ fontSize: 12, fill: '#6b7280' }}
              label={{ value: 'Score (%)', angle: -90, position: 'insideLeft', style: { fill: '#6b7280' } }}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px' }}
              formatter={(value: number) => [`${value}%`, 'Score']}
              labelFormatter={(label) => `Date: ${label}`}
            />
            <Legend />
            <Line 
              type="monotone" 
              dataKey="Communication" 
              stroke={colors['Communication']} 
              strokeWidth={2}
              dot={{ r: 4 }}
              connectNulls
            />
            <Line 
              type="monotone" 
              dataKey="Technical" 
              stroke={colors['Technical']} 
              strokeWidth={2}
              dot={{ r: 4 }}
              connectNulls
            />
            <Line 
              type="monotone" 
              dataKey="Problem Solving" 
              stroke={colors['Problem Solving']} 
              strokeWidth={2}
              dot={{ r: 4 }}
              connectNulls
            />
            <Line 
              type="monotone" 
              dataKey="Code Quality" 
              stroke={colors['Code Quality']} 
              strokeWidth={2}
              dot={{ r: 4 }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

