"""User intent detection for interview orchestrator."""

import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
import instructor

from src.core.config import settings
from src.services.orchestrator.types import InterviewState, UserIntent, UserIntentDetection
from src.services.orchestrator.context_builders import build_conversation_context

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.services.interview_logger import InterviewLogger


async def detect_user_intent(
    state: InterviewState,
    openai_client: AsyncOpenAI,
    interview_logger=None
) -> InterviewState:
    """Detect user intent from their last response."""
    state["last_node"] = "detect_user_intent"

    last_response = state.get("last_response")
    if not last_response:
        state["active_user_request"] = None
        return state

    # Build conversation context for better understanding
    conversation_context = build_conversation_context(state, interview_logger)
    recent_context = conversation_context[-500:] if len(conversation_context) > 500 else conversation_context

    # Get the last question asked to understand what user might be responding to
    last_question = ""
    if state.get("conversation_history"):
        for msg in reversed(state["conversation_history"]):
            if msg.get("role") == "assistant":
                last_question = msg.get("content", "")
                break

    prompt = f"""You are analyzing a user's response in an interview conversation to understand their TRUE INTENT.

CONVERSATION CONTEXT:
{recent_context}

LAST QUESTION ASKED: {last_question if last_question else "None (initial greeting)"}

USER'S CURRENT RESPONSE: "{last_response}"

YOUR TASK:
Understand what the user is TRYING TO ACCOMPLISH with this response. Think about:
1. What ACTION do they want the interviewer to take?
2. What is their GOAL or PURPOSE in saying this?
3. Are they making a REQUEST or just ANSWERING a question?
4. What would happen if we IGNORED their intent? Would the conversation flow naturally?

CRITICAL: Don't match keywords. Understand the user's GOAL. People express the same intent in many different ways.

INTENT TYPES - Understand the GOAL, not the words:

1. **write_code**: User wants to CREATE/WRITE code in the sandbox
   - GOAL: Demonstrate coding ability by writing code
   - SIGNALS: Proactive request to code, wants to show technical skills
   - VARIATIONS: "I'd like to write code", "Can I code something?", "Let me show you my approach", "I want to demonstrate", "Can I use the editor?"
   - NOT: Just mentioning code in an answer

2. **review_code**: User wants to SHARE/DISCUSS existing code
   - GOAL: Get feedback on code they have or want to walk through
   - SIGNALS: Has code ready, wants to show/share code
   - VARIATIONS: "Here's my code", "Can you review this?", "Let me show you the implementation", "I have some code to share"
   - NOT: Asking to write new code

3. **change_topic**: User wants to REDIRECT the conversation
   - GOAL: Move discussion to a different subject/topic
   - SIGNALS: Explicit redirection, wants to discuss something else, correcting direction
   - VARIATIONS: "Actually, let's talk about X", "Can we discuss Y instead?", "I'd rather talk about Z", "Let's change topics", "What about X?", "Instead, I want to discuss Y"
   - KEY: User is REDIRECTING, not just answering differently. Look for correction/redirection intent.
   - NOT: Just providing a different answer or example

4. **clarify**: User is CONFUSED and needs help understanding
   - GOAL: Get clarification on what was asked
   - SIGNALS: Doesn't understand, needs explanation, asking for help
   - VARIATIONS: "What do you mean?", "I don't understand", "Can you clarify?", "Could you explain?", "I'm not sure what you're asking"
   - NOT: Just asking a follow-up question

5. **technical_assessment**: User wants DIFFERENT TYPE of interview
   - GOAL: Switch to technical/coding questions format
   - SIGNALS: Requesting different interview style
   - VARIATIONS: "Give me coding questions", "I want technical assessment", "Ask me technical questions"

6. **stop**: User wants to END the interview
   - GOAL: Terminate or pause the conversation
   - SIGNALS: Clear request to stop
   - VARIATIONS: "Let's stop", "That's enough", "I want to end", "Can we finish?"

7. **continue**: User is AFFIRMING willingness to continue
   - GOAL: Express agreement/willingness
   - SIGNALS: Brief affirmative response
   - VARIATIONS: "Yes", "Sure", "Okay", "Continue", "Go ahead"

8. **no_intent**: User is just ANSWERING normally
   - GOAL: Provide information, answer the question
   - SIGNALS: Normal conversational response, providing information
   - DEFAULT: When user is just answering or having normal conversation

ANALYSIS FRAMEWORK - Think through this:

Step 1: What is the user's GOAL?
- Are they trying to DO something (request an action)?
- Are they trying to SAY something (provide information)?
- Are they trying to CHANGE something (redirect/clarify)?

Step 2: What would happen if we IGNORED this?
- If ignoring it would break the conversation flow → It's a request (write_code, change_topic, clarify, etc.)
- If ignoring it is fine → It's just an answer (no_intent)

Step 3: Look at the CONTEXT
- What was just discussed?
- What question was just asked?
- How does this response relate to the conversation flow?

EXAMPLES OF GOOD INTENT DETECTION:

Example 1:
Context: Interviewer asked "What challenges did you face?"
User: "Actually, let's talk about my team leadership instead"
Analysis: User is REDIRECTING (goal: change topic). They're not answering the question, they're changing direction.
Intent: change_topic (confidence: 0.95)

Example 2:
Context: Interviewer asked "Tell me about your project"
User: "I'd like to write some code to show you my approach"
Analysis: User wants to DEMONSTRATE (goal: write code). Proactive request to code.
Intent: write_code (confidence: 0.9)

Example 3:
Context: Interviewer asked "How did you solve that?"
User: "What do you mean by 'solve'?"
Analysis: User is CONFUSED (goal: get clarification). They need help understanding.
Intent: clarify (confidence: 0.9)

Example 4:
Context: Interviewer asked "What tools did you use?"
User: "I've worked with Python, Docker, and Kubernetes"
Analysis: User is ANSWERING (goal: provide information). Normal response.
Intent: no_intent (confidence: 0.9)

Example 5:
Context: Interviewer asked "Tell me about microservices"
User: "I've built microservices using Go. Can I show you the code?"
Analysis: User is ANSWERING but also making a REQUEST (goal: share code). The request is clear.
Intent: review_code (confidence: 0.85)

CONFIDENCE SCORING:
- 0.9+: Very clear intent, user is explicitly requesting something
- 0.7-0.89: Clear intent, but some ambiguity
- <0.7: Ambiguous, likely no_intent

Return your analysis with:
- intent_type: The best matching intent (one of: write_code, review_code, change_topic, clarify, technical_assessment, stop, continue, no_intent)
- confidence: How certain you are (0.0-1.0, float)
- reasoning: Brief explanation of WHY you chose this intent (what goal did you identify?)
- metadata: A JSON object/dict with any additional context (e.g. {{"topic": "leadership", "reason": "user redirected"}}), NOT a string"""

    try:
        client = instructor.patch(openai_client)
        detection = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_model=UserIntentDetection,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at understanding human intent through conversation analysis. Your job is to identify what the user is TRYING TO ACCOMPLISH, not match keywords. Think about their GOAL, their PURPOSE, and what ACTION they want. Consider the conversation context, the flow, and what would happen if their intent was ignored. Be thoughtful and holistic in your analysis.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )

        # Store intent
        intent: UserIntent = {
            "type": detection.intent_type,
            "confidence": detection.confidence,
            "extracted_from": last_response,
            "turn": state["turn_count"],
            "metadata": detection.metadata,
        }

        state["detected_intents"] = state.get("detected_intents", [])
        state["detected_intents"].append(intent)

        # Set active request if confidence is high
        if detection.confidence > 0.7:
            state["active_user_request"] = intent
            logger.info(
                f"Detected user intent: {detection.intent_type} (confidence: {detection.confidence})")
        else:
            state["active_user_request"] = None

    except Exception as e:
        logger.warning(f"Failed to detect user intent: {e}")
        state["active_user_request"] = None

    return state

