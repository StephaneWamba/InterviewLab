'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Briefcase, GraduationCap, Code, User, FileText, Calendar, MapPin } from 'lucide-react';

interface ResumeData {
  profile?: string;
  experience?: string;
  education?: string;
  projects?: string;
  hobbies?: string;
  skills?: string[];
}

interface ResumeDisplayProps {
  resumeData: ResumeData | any;
  fileName: string;
}

export function ResumeDisplay({ resumeData, fileName }: ResumeDisplayProps) {
  // Parse resume data - handle both string and object formats
  const data: ResumeData = typeof resumeData === 'string' 
    ? JSON.parse(resumeData) 
    : resumeData || {};

  // Extract profile/summary
  const profile = data.profile || '';

  // Parse experience entries (split by newlines or company patterns)
  const parseExperience = (exp: string | undefined): Array<{
    company?: string;
    role?: string;
    period?: string;
    location?: string;
    description?: string;
  }> => {
    if (!exp) return [];
    
    // Try to split by company name patterns or newlines
    const entries: Array<{ company?: string; role?: string; period?: string; location?: string; description?: string }> = [];
    const lines = exp.split('\n').filter(l => l.trim());
    
    let currentEntry: any = {};
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      
      // Check if line looks like a company name (capitalized, short)
      if (trimmed.length < 50 && /^[A-Z]/.test(trimmed) && !trimmed.includes('•') && !trimmed.includes('-')) {
        if (currentEntry.company) entries.push(currentEntry);
        currentEntry = { company: trimmed };
      }
      // Check if line looks like a role (contains common role keywords)
      else if (/Senior|Junior|Lead|Engineer|Developer|Manager|Consultant|Director/i.test(trimmed) && trimmed.length < 100) {
        currentEntry.role = trimmed;
      }
      // Check if line looks like a period (contains dates or months)
      else if (/\d{4}|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/i.test(trimmed) && trimmed.length < 50) {
        currentEntry.period = trimmed;
      }
      // Check if line looks like location
      else if (/Remote|Bangalore|Mumbai|Delhi|Pune|Hyderabad|Chennai|USA|India/i.test(trimmed) && trimmed.length < 50) {
        currentEntry.location = trimmed;
      }
      // Otherwise, it's likely description
      else {
        if (!currentEntry.description) {
          currentEntry.description = trimmed;
        } else {
          currentEntry.description += ' ' + trimmed;
        }
      }
    }
    if (currentEntry.company) entries.push(currentEntry);
    
    // Fallback: if no structured parsing worked, show as paragraphs
    if (entries.length === 0) {
      return lines.map((line, idx) => ({ description: line }));
    }
    
    return entries;
  };

  // Parse education
  const parseEducation = (edu: string | undefined): Array<{
    institution?: string;
    degree?: string;
    period?: string;
    location?: string;
  }> => {
    if (!edu) return [];
    const lines = edu.split('\n').filter(l => l.trim());
    return lines.map(line => {
      // Try to extract institution, degree, period
      const parts = line.split(',').map(p => p.trim());
      return {
        institution: parts[0] || line,
        degree: parts[1] || undefined,
        period: parts[2] || undefined,
      };
    });
  };

  // Extract skills from hobbies or separate skills field
  const extractSkills = (): string[] => {
    if (data.skills && Array.isArray(data.skills)) {
      return data.skills;
    }
    if (data.hobbies) {
      // Try to extract skills from hobbies field (often contains "Skills: ...")
      const skillsMatch = data.hobbies.match(/Skills?:\s*([^,\n]+(?:,\s*[^,\n]+)*)/i);
      if (skillsMatch) {
        return skillsMatch[1].split(',').map(s => s.trim()).filter(Boolean);
      }
    }
    return [];
  };

  const experienceEntries = parseExperience(data.experience);
  const educationEntries = parseEducation(data.education);
  const skills = extractSkills();

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <Card className="border-2">
        <CardHeader className="pb-4">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <CardTitle className="text-3xl font-bold mb-2">{fileName.replace('.pdf', '')}</CardTitle>
              <div className="flex items-center gap-4 text-sm text-muted-foreground">
                <div className="flex items-center gap-1">
                  <FileText className="h-4 w-4" />
                  <span>Resume</span>
                </div>
                <Separator orientation="vertical" className="h-4" />
                <span>Analyzed and Formatted</span>
              </div>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Profile/Summary */}
      {profile && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <User className="h-5 w-5 text-primary" />
              <CardTitle className="text-xl">Professional Summary</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-base leading-relaxed text-foreground whitespace-pre-wrap">
              {profile}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Skills */}
      {skills.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Code className="h-5 w-5 text-primary" />
              <CardTitle className="text-xl">Skills & Technologies</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {skills.map((skill, idx) => (
                <Badge key={idx} variant="secondary" className="text-sm px-3 py-1">
                  {skill}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Experience */}
      {experienceEntries.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Briefcase className="h-5 w-5 text-primary" />
              <CardTitle className="text-xl">Work Experience</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              {experienceEntries.map((entry, idx) => (
                <div key={idx} className="relative pl-8 pb-6 last:pb-0">
                  {/* Timeline indicator */}
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full bg-primary border-2 border-background" />
                  {idx < experienceEntries.length - 1 && (
                    <div className="absolute left-1.5 top-5 bottom-0 w-0.5 bg-border" />
                  )}
                  
                  <div className="space-y-2">
                    {entry.role && (
                      <h3 className="text-lg font-semibold text-foreground">{entry.role}</h3>
                    )}
                    <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                      {entry.company && (
                        <div className="flex items-center gap-1 font-medium text-foreground">
                          <Briefcase className="h-3 w-3" />
                          <span>{entry.company}</span>
                        </div>
                      )}
                      {entry.period && (
                        <div className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          <span>{entry.period}</span>
                        </div>
                      )}
                      {entry.location && (
                        <div className="flex items-center gap-1">
                          <MapPin className="h-3 w-3" />
                          <span>{entry.location}</span>
                        </div>
                      )}
                    </div>
                    {entry.description && (
                      <p className="text-sm text-foreground leading-relaxed mt-2 whitespace-pre-wrap">
                        {entry.description}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Fallback: Raw experience if parsing didn't work */}
      {data.experience && experienceEntries.length === 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Briefcase className="h-5 w-5 text-primary" />
              <CardTitle className="text-xl">Work Experience</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm max-w-none">
              <p className="text-base leading-relaxed whitespace-pre-wrap text-foreground">
                {data.experience}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Education */}
      {educationEntries.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <GraduationCap className="h-5 w-5 text-primary" />
              <CardTitle className="text-xl">Education</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {educationEntries.map((entry, idx) => (
                <div key={idx} className="space-y-1">
                  {entry.degree && (
                    <h3 className="text-lg font-semibold text-foreground">{entry.degree}</h3>
                  )}
                  <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                    {entry.institution && (
                      <span className="font-medium text-foreground">{entry.institution}</span>
                    )}
                    {entry.period && (
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {entry.period}
                      </span>
                    )}
                    {entry.location && (
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3 w-3" />
                        {entry.location}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Fallback: Raw education */}
      {data.education && educationEntries.length === 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <GraduationCap className="h-5 w-5 text-primary" />
              <CardTitle className="text-xl">Education</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-base leading-relaxed whitespace-pre-wrap text-foreground">
              {data.education}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Projects */}
      {data.projects && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Code className="h-5 w-5 text-primary" />
              <CardTitle className="text-xl">Projects</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="prose prose-sm max-w-none">
              <p className="text-base leading-relaxed whitespace-pre-wrap text-foreground">
                {data.projects}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Additional Information / Hobbies */}
      {data.hobbies && !data.hobbies.includes('Skills:') && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <User className="h-5 w-5 text-primary" />
              <CardTitle className="text-xl">Additional Information</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-base leading-relaxed whitespace-pre-wrap text-foreground">
              {data.hobbies.replace(/Skills?:\s*/i, '')}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

