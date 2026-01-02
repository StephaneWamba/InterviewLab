# Backend Enhancements for Skill Competency Analytics

## Current State Analysis

### ✅ What Works (Can Use Now)

1. **Skill Scores Available**: All 4 skills stored per interview

   - `communication_score`, `technical_score`, `problem_solving_score`, `code_quality_score`
   - Stored in `interview.feedback` JSON field
   - Accessible via `get_interview_insights()`

2. **Basic Analytics**:
   - User analytics aggregation exists
   - Interview insights extraction exists

### ❌ What Needs Enhancement

## Required Backend Changes

### 1. Enhance `InterviewFeedback` Model (feedback_generator.py)

**Current:**

```python
strengths: List[str]  # Global list
weaknesses: List[str]  # Global list
recommendations: List[str]  # Global list
```

**Needed:**

```python
skill_breakdown: Dict[str, SkillBreakdown] = {
    "communication": {
        "score": 0.85,
        "strengths": ["Clear explanations", "Engaging"],
        "weaknesses": ["Could be more concise"],
        "recommendations": ["Practice summarizing answers"]
    },
    "technical": {...},
    "problem_solving": {...},
    "code_quality": {...}
}
```

### 2. Add Methods to `InterviewAnalytics` Service

**New Methods Needed:**

```python
async def get_skill_progression(
    self, user_id: int, db: AsyncSession
) -> Dict[str, List[SkillDataPoint]]:
    """Get skill scores over time for progression charts."""
    # Returns: {
    #   "communication": [{interview_id, date, score}, ...],
    #   "technical": [...],
    #   "problem_solving": [...],
    #   "code_quality": [...]
    # }

async def get_skill_averages(
    self, user_id: int, db: AsyncSession
) -> Dict[str, float]:
    """Get average scores per skill across all interviews."""
    # Returns: {
    #   "communication": 0.85,
    #   "technical": 0.72,
    #   ...
    # }

async def get_skill_comparison(
    self, interview_ids: List[int], db: AsyncSession
) -> Dict[str, Dict[int, float]]:
    """Compare skills across multiple interviews."""
    # Returns: {
    #   "communication": {interview_id: score, ...},
    #   "technical": {...},
    #   ...
    # }

async def get_skill_breakdown(
    self, interview_id: int, db: AsyncSession
) -> Dict[str, SkillBreakdown]:
    """Get detailed skill breakdown for one interview."""
    # Returns skill-specific strengths, weaknesses, recommendations
```

### 3. Enhance `FeedbackGenerator.generate_feedback()`

**Update LLM prompt** to extract skill-specific insights:

```python
prompt = f"""
Generate skill-specific feedback:

For each skill (Communication, Technical, Problem-Solving, Code Quality):
- Score (0-1)
- 2-3 specific strengths
- 2-3 specific weaknesses
- 2-3 specific recommendations

Return structured breakdown per skill.
"""
```

### 4. Add API Endpoints

**New endpoints needed:**

```python
@router.get("/analytics/skills/progression")
async def get_skill_progression(...):
    """Get skill progression over time for charts."""

@router.get("/analytics/skills/averages")
async def get_skill_averages(...):
    """Get average skill scores."""

@router.get("/analytics/skills/compare")
async def compare_interview_skills(interview_ids: List[int], ...):
    """Compare skills across interviews."""

@router.get("/{interview_id}/skills")
async def get_interview_skill_breakdown(interview_id: int, ...):
    """Get detailed skill breakdown for one interview."""
```

## Implementation Priority

### Phase 1: Minimal (Works with current data)

- ✅ Extract skill scores from existing feedback
- ✅ Build skill progression chart data from existing scores
- ✅ Calculate skill averages
- **Can build charts immediately** (just scores, no skill-specific details)

### Phase 2: Enhanced (Requires LLM enhancement)

- Add skill-specific strengths/weaknesses
- Add skill-specific recommendations
- Enhance feedback generation prompt

### Phase 3: Advanced

- Skill comparison tool
- Trend analysis (improving/declining skills)
- Skill-based recommendations

## Recommendation

**Start with Phase 1** - backend can support basic charts NOW:

1. Skill scores already exist ✅
2. Can extract progression data from existing interviews ✅
3. Can calculate averages ✅
4. Frontend can build charts with current data ✅

**Then enhance Phase 2** - add skill-specific details in feedback generation.
