"""Service for interview analytics and metrics tracking with skill-specific analysis."""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.models.interview import Interview
from src.models.user import User


class InterviewAnalytics:
    """Service for analyzing interview data and generating insights."""

    async def get_user_analytics(
        self, user_id: int, db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get analytics for a specific user.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            Dictionary with user analytics
        """
        # Get all interviews for user
        result = await db.execute(
            select(Interview)
            .where(Interview.user_id == user_id)
            .order_by(Interview.created_at.desc())
        )
        interviews = result.scalars().all()

        if not interviews:
            return {
                "total_interviews": 0,
                "completed_interviews": 0,
                "average_turn_count": 0,
                "average_quality": 0.0,
                "topics_covered": [],
                "improvement_trend": [],
            }

        completed = [i for i in interviews if i.status == "completed"]
        total = len(interviews)
        completed_count = len(completed)

        # Calculate average turn count
        turn_counts = [i.turn_count for i in completed if i.turn_count]
        avg_turn_count = sum(turn_counts) / len(turn_counts) if turn_counts else 0

        # Calculate average quality from feedback
        quality_scores = []
        for interview in completed:
            if interview.feedback and isinstance(interview.feedback, dict):
                score = interview.feedback.get("overall_score")
                if score is not None:
                    quality_scores.append(score)
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        # Collect all topics covered
        all_topics = []
        for interview in completed:
            if interview.feedback and isinstance(interview.feedback, dict):
                topics = interview.feedback.get("topics_covered", [])
                all_topics.extend(topics)
        unique_topics = list(set(all_topics))

        # Calculate improvement trend (last 5 interviews)
        recent_interviews = completed[:5]
        improvement_trend = []
        for interview in reversed(recent_interviews):
            if interview.feedback and isinstance(interview.feedback, dict):
                score = interview.feedback.get("overall_score")
                if score is not None:
                    improvement_trend.append({
                        "interview_id": interview.id,
                        "score": score,
                        "date": interview.completed_at.isoformat() if interview.completed_at else None,
                    })

        # Code submission stats
        code_submissions_total = 0
        code_quality_scores = []
        for interview in completed:
            if interview.conversation_history:
                for msg in interview.conversation_history:
                    if msg.get("metadata", {}).get("type") == "code_review":
                        code_submissions_total += 1
                        quality = msg.get("metadata", {}).get("code_quality", {}).get("quality_score")
                        if quality is not None:
                            code_quality_scores.append(quality)

        avg_code_quality = sum(code_quality_scores) / len(code_quality_scores) if code_quality_scores else 0.0

        return {
            "total_interviews": total,
            "completed_interviews": completed_count,
            "in_progress_interviews": len([i for i in interviews if i.status == "in_progress"]),
            "average_turn_count": round(avg_turn_count, 1),
            "average_quality": round(avg_quality, 2),
            "average_code_quality": round(avg_code_quality, 2),
            "total_code_submissions": code_submissions_total,
            "topics_covered": unique_topics,
            "improvement_trend": improvement_trend,
            "recent_interviews": [
                {
                    "id": i.id,
                    "title": i.title,
                    "status": i.status,
                    "completed_at": i.completed_at.isoformat() if i.completed_at else None,
                    "quality_score": i.feedback.get("overall_score") if i.feedback and isinstance(i.feedback, dict) else None,
                }
                for i in completed[:5]
            ],
        }

    async def get_skill_progression(
        self, user_id: int, db: AsyncSession
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get skill scores over time for progression charts.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            Dictionary with skill progression data:
            {
                "communication": [{interview_id, date, score}, ...],
                "technical": [...],
                "problem_solving": [...],
                "code_quality": [...]
            }
        """
        # Get all completed interviews for user
        result = await db.execute(
            select(Interview)
            .where(
                Interview.user_id == user_id,
                Interview.status == "completed"
            )
            .order_by(Interview.completed_at.asc())
        )
        interviews = result.scalars().all()

        progression = {
            "communication": [],
            "technical": [],
            "problem_solving": [],
            "code_quality": [],
        }

        for interview in interviews:
            if not interview.feedback or not isinstance(interview.feedback, dict):
                continue

            date = interview.completed_at.isoformat() if interview.completed_at else interview.created_at.isoformat()

            # Extract skill scores
            comm_score = interview.feedback.get("communication_score")
            tech_score = interview.feedback.get("technical_score")
            prob_score = interview.feedback.get("problem_solving_score")
            code_score = interview.feedback.get("code_quality_score")

            if comm_score is not None:
                progression["communication"].append({
                    "interview_id": interview.id,
                    "interview_title": interview.title,
                    "date": date,
                    "score": round(comm_score, 2),
                })

            if tech_score is not None:
                progression["technical"].append({
                    "interview_id": interview.id,
                    "interview_title": interview.title,
                    "date": date,
                    "score": round(tech_score, 2),
                })

            if prob_score is not None:
                progression["problem_solving"].append({
                    "interview_id": interview.id,
                    "interview_title": interview.title,
                    "date": date,
                    "score": round(prob_score, 2),
                })

            if code_score is not None:
                progression["code_quality"].append({
                    "interview_id": interview.id,
                    "interview_title": interview.title,
                    "date": date,
                    "score": round(code_score, 2),
                })

        return progression

    async def get_skill_averages(
        self, user_id: int, db: AsyncSession
    ) -> Dict[str, float]:
        """
        Get average scores per skill across all completed interviews.

        Args:
            user_id: User ID
            db: Database session

        Returns:
            Dictionary with average scores per skill:
            {
                "communication": 0.85,
                "technical": 0.72,
                "problem_solving": 0.80,
                "code_quality": 0.68
            }
        """
        # Get all completed interviews
        result = await db.execute(
            select(Interview)
            .where(
                Interview.user_id == user_id,
                Interview.status == "completed"
            )
        )
        interviews = result.scalars().all()

        skill_scores = {
            "communication": [],
            "technical": [],
            "problem_solving": [],
            "code_quality": [],
        }

        for interview in interviews:
            if not interview.feedback or not isinstance(interview.feedback, dict):
                continue

            comm_score = interview.feedback.get("communication_score")
            tech_score = interview.feedback.get("technical_score")
            prob_score = interview.feedback.get("problem_solving_score")
            code_score = interview.feedback.get("code_quality_score")

            if comm_score is not None:
                skill_scores["communication"].append(comm_score)
            if tech_score is not None:
                skill_scores["technical"].append(tech_score)
            if prob_score is not None:
                skill_scores["problem_solving"].append(prob_score)
            if code_score is not None:
                skill_scores["code_quality"].append(code_score)

        averages = {}
        for skill, scores in skill_scores.items():
            if scores:
                averages[skill] = round(sum(scores) / len(scores), 2)
            else:
                averages[skill] = 0.0

        return averages

    async def get_skill_comparison(
        self, interview_ids: List[int], db: AsyncSession
    ) -> Dict[str, Dict[int, float]]:
        """
        Compare skills across multiple interviews.

        Args:
            interview_ids: List of interview IDs to compare
            db: Database session

        Returns:
            Dictionary with scores per skill per interview:
            {
                "communication": {interview_id: score, ...},
                "technical": {...},
                "problem_solving": {...},
                "code_quality": {...}
            }
        """
        if not interview_ids:
            return {
                "communication": {},
                "technical": {},
                "problem_solving": {},
                "code_quality": {},
            }

        result = await db.execute(
            select(Interview).where(Interview.id.in_(interview_ids))
        )
        interviews = result.scalars().all()

        comparison = {
            "communication": {},
            "technical": {},
            "problem_solving": {},
            "code_quality": {},
        }

        for interview in interviews:
            if not interview.feedback or not isinstance(interview.feedback, dict):
                continue

            comm_score = interview.feedback.get("communication_score")
            tech_score = interview.feedback.get("technical_score")
            prob_score = interview.feedback.get("problem_solving_score")
            code_score = interview.feedback.get("code_quality_score")

            if comm_score is not None:
                comparison["communication"][interview.id] = round(comm_score, 2)
            if tech_score is not None:
                comparison["technical"][interview.id] = round(tech_score, 2)
            if prob_score is not None:
                comparison["problem_solving"][interview.id] = round(prob_score, 2)
            if code_score is not None:
                comparison["code_quality"][interview.id] = round(code_score, 2)

        return comparison

    async def get_skill_breakdown(
        self, interview_id: int, db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get detailed skill breakdown for a specific interview.

        Args:
            interview_id: Interview ID
            db: Database session

        Returns:
            Dictionary with detailed skill breakdown:
            {
                "communication": {
                    "score": 0.85,
                    "strengths": [...],
                    "weaknesses": [...],
                    "recommendations": [...]
                },
                ...
            }
        """
        result = await db.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = result.scalar_one_or_none()

        if not interview or not interview.feedback or not isinstance(interview.feedback, dict):
            return {
                "communication": {"score": 0.0, "strengths": [], "weaknesses": [], "recommendations": []},
                "technical": {"score": 0.0, "strengths": [], "weaknesses": [], "recommendations": []},
                "problem_solving": {"score": 0.0, "strengths": [], "weaknesses": [], "recommendations": []},
                "code_quality": {"score": 0.0, "strengths": [], "weaknesses": [], "recommendations": []},
            }

        feedback = interview.feedback

        # Extract skill breakdown if available (new format)
        skill_breakdown = feedback.get("skill_breakdown", {})

        # Build breakdown dict with fallbacks to scores if breakdown not available
        breakdown = {}

        for skill in ["communication", "technical", "problem_solving", "code_quality"]:
            skill_key = skill if skill != "problem_solving" else "problem_solving"
            score_key = f"{skill_key}_score" if skill != "problem_solving" else "problem_solving_score"

            if skill in skill_breakdown and isinstance(skill_breakdown[skill], dict):
                # Use detailed breakdown if available
                breakdown[skill] = {
                    "score": skill_breakdown[skill].get("score", feedback.get(score_key, 0.0)),
                    "strengths": skill_breakdown[skill].get("strengths", []),
                    "weaknesses": skill_breakdown[skill].get("weaknesses", []),
                    "recommendations": skill_breakdown[skill].get("recommendations", []),
                }
            else:
                # Fallback to score only (backward compatibility)
                score = feedback.get(score_key, 0.0)
                breakdown[skill] = {
                    "score": round(score, 2) if score else 0.0,
                    "strengths": [],
                    "weaknesses": [],
                    "recommendations": [],
                }

        return breakdown

    async def get_interview_insights(
        self, interview_id: int, db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Get detailed insights for a specific interview.

        Args:
            interview_id: Interview ID
            db: Database session

        Returns:
            Dictionary with interview insights
        """
        result = await db.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = result.scalar_one_or_none()

        if not interview:
            return {}

        insights = {
            "interview_id": interview.id,
            "title": interview.title,
            "status": interview.status,
            "turn_count": interview.turn_count,
            "duration_minutes": None,
            "topics_covered": [],
            "code_submissions": 0,
            "average_code_quality": 0.0,
            "conversation_quality": {},
        }

        # Calculate duration
        if interview.started_at and interview.completed_at:
            duration = interview.completed_at - interview.started_at
            insights["duration_minutes"] = round(duration.total_seconds() / 60, 1)

        # Extract topics
        if interview.feedback and isinstance(interview.feedback, dict):
            insights["topics_covered"] = interview.feedback.get("topics_covered", [])
            insights["conversation_quality"] = {
                "overall_score": interview.feedback.get("overall_score"),
                "communication_score": interview.feedback.get("communication_score"),
                "technical_score": interview.feedback.get("technical_score"),
                "problem_solving_score": interview.feedback.get("problem_solving_score"),
                "code_quality_score": interview.feedback.get("code_quality_score"),
            }

        # Code submission analysis
        code_qualities = []
        if interview.conversation_history:
            for msg in interview.conversation_history:
                if msg.get("metadata", {}).get("type") == "code_review":
                    insights["code_submissions"] += 1
                    quality = msg.get("metadata", {}).get("code_quality", {}).get("quality_score")
                    if quality is not None:
                        code_qualities.append(quality)

        if code_qualities:
            insights["average_code_quality"] = round(sum(code_qualities) / len(code_qualities), 2)

        return insights

    async def get_global_stats(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Get global statistics across all interviews.

        Args:
            db: Database session

        Returns:
            Dictionary with global statistics
        """
        # Total interviews
        total_result = await db.execute(select(func.count(Interview.id)))
        total_interviews = total_result.scalar() or 0

        # Completed interviews
        completed_result = await db.execute(
            select(func.count(Interview.id)).where(Interview.status == "completed")
        )
        completed_interviews = completed_result.scalar() or 0

        # Unique users
        users_result = await db.execute(select(func.count(func.distinct(Interview.user_id))))
        unique_users = users_result.scalar() or 0

        # Average turn count
        avg_turns_result = await db.execute(
            select(func.avg(Interview.turn_count)).where(Interview.status == "completed")
        )
        avg_turns = avg_turns_result.scalar() or 0

        return {
            "total_interviews": total_interviews,
            "completed_interviews": completed_interviews,
            "in_progress_interviews": total_interviews - completed_interviews,
            "unique_users": unique_users,
            "average_turn_count": round(avg_turns, 1) if avg_turns else 0,
            "completion_rate": round(completed_interviews / total_interviews * 100, 1) if total_interviews > 0 else 0,
        }
