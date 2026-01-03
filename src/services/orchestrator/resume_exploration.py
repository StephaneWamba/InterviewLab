"""Resume exploration helpers for interview orchestrator."""

from typing import TYPE_CHECKING, Optional

# Configurable limits for resume exploration
MAX_PROJECTS = 15  # Increased from 10
MAX_SKILLS = 20  # Increased from 15
MAX_EXPERIENCES = 8  # Increased from 5

if TYPE_CHECKING:
    from src.services.orchestrator.types import InterviewState, ResumeExploration


def initialize_resume_exploration(state: "InterviewState") -> "InterviewState":
    """Initialize resume exploration anchors from resume context."""
    if "resume_exploration" in state and state["resume_exploration"]:
        return state  # Already initialized

    resume_ctx = state.get("resume_structured", {})
    exploration: dict[str, ResumeExploration] = {}

    # Extract projects
    if resume_ctx.get("projects"):
        projects = resume_ctx["projects"] if isinstance(
            resume_ctx["projects"], list) else []
        for i, project in enumerate(projects[:MAX_PROJECTS], 1):
            anchor_id = f"project_{i}"
            exploration[anchor_id] = {
                "anchor_id": anchor_id,
                "anchor_type": "project",
                "aspects_covered": set(),
                "depth_score": 0,
                "last_explored_turn": -1,
            }

    # Extract skills
    if resume_ctx.get("skills"):
        skills = resume_ctx["skills"] if isinstance(
            resume_ctx["skills"], list) else []
        for i, skill in enumerate(skills[:MAX_SKILLS], 1):
            anchor_id = f"skill_{skill.lower().replace(' ', '_')}"
            exploration[anchor_id] = {
                "anchor_id": anchor_id,
                "anchor_type": "skill",
                "aspects_covered": set(),
                "depth_score": 0,
                "last_explored_turn": -1,
            }

    # Extract experiences (jobs/internships)
    if resume_ctx.get("experience"):
        experience_text = resume_ctx["experience"] if isinstance(
            resume_ctx["experience"], str) else str(resume_ctx.get("experience", ""))
        # Simple heuristic: extract company names or roles
        experiences = experience_text.split("\n")[:MAX_EXPERIENCES]
        for i, exp in enumerate(experiences[:MAX_EXPERIENCES], 1):
            anchor_id = f"experience_{i}"
            exploration[anchor_id] = {
                "anchor_id": anchor_id,
                "anchor_type": "experience",
                "aspects_covered": set(),
                "depth_score": 0,
                "last_explored_turn": -1,
            }

    state["resume_exploration"] = exploration
    return state


def find_unexplored_anchor(state: "InterviewState") -> Optional[str]:
    """Find an anchor with unexplored aspects."""
    exploration = state.get("resume_exploration", {})
    if not exploration:
        return None

    # Prefer anchors with low depth_score and many unexplored aspects
    candidates = []
    all_aspects = {"challenges", "impact", "design", "tools",
                   "team", "results", "tradeoffs", "implementation"}

    for anchor_id, anchor_data in exploration.items():
        covered = anchor_data.get("aspects_covered", set())
        uncovered = all_aspects - covered
        depth = anchor_data.get("depth_score", 0)

        if uncovered:
            candidates.append((anchor_id, len(uncovered), depth))

    if not candidates:
        return None

    # Sort by: most uncovered aspects, then lowest depth
    candidates.sort(key=lambda x: (-x[1], x[2]))
    return candidates[0][0]


def extract_topics_from_exploration(state: "InterviewState") -> list[str]:
    """Extract topic names from resume_exploration anchors.

    Extracts human-readable topic names from the resume_exploration anchors
    that have been explored.
    """
    exploration = state.get("resume_exploration", {})
    if not exploration:
        return []

    topics = []
    for anchor_id, anchor_data in exploration.items():
        depth_score = anchor_data.get("depth_score", 0)
        aspects_covered = anchor_data.get("aspects_covered", set())

        # Only include anchors that have been explored (depth > 0 or aspects covered)
        if depth_score > 0 or aspects_covered:
            anchor_type = anchor_data.get("anchor_type", "unknown")

            # Convert anchor_id to human-readable topic name
            if anchor_type == "project":
                topic_name = anchor_id.replace("_", " ").title()
            elif anchor_type == "skill":
                topic_name = anchor_id.replace(
                    "skill_", "").replace("_", " ").title()
            elif anchor_type == "experience":
                topic_name = anchor_id.replace("_", " ").title()
            else:
                topic_name = anchor_id.replace("_", " ").title()

            topics.append(topic_name)

    return topics
