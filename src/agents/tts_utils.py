"""Text-to-speech utility functions for natural TTS delivery.

These utilities prepare and normalize text for better TTS pronunciation
and prosody in voice AI conversations.
"""

import re


def prepare_text_for_tts(text: str) -> str:
    """
    Prepare text for natural TTS delivery.

    Based on best practices:
    - Normalize punctuation for better prosody
    - Fix common formatting issues
    - Ensure proper sentence structure
    """
    if not text:
        return text

    # Strip whitespace
    text = text.strip()

    # Replace colons with periods (colons can sound awkward in TTS)
    text = text.replace(":", ".")

    # Normalize em dashes to commas (better for natural pauses)
    text = text.replace("—", ",")
    text = text.replace("–", ",")

    # Remove multiple spaces
    while "  " in text:
        text = text.replace("  ", " ")

    # Ensure sentences end with proper punctuation
    if text and text[-1] not in ".!?":
        text += "."

    return text


def normalize_numbers_and_symbols(text: str) -> str:
    """
    Normalize numbers and symbols for better TTS pronunciation.

    This helps with:
    - Percentage pronunciation (5% -> "5 percent")
    - Clean up common formatting issues
    """
    # Normalize percentages: 5% -> 5 percent (for better pronunciation)
    text = re.sub(r'(\d+)%', r'\1 percent', text)

    return text


def split_into_sentences(text: str, max_length: int = 200) -> list[str]:
    """
    Split text into sentences for chunked delivery.

    Shorter sentences = better TTS naturalness
    Max length ensures we don't send overly long chunks
    """
    # Split on sentence boundaries (. ! ?)
    sentences = re.split(r'([.!?]+)', text)

    # Recombine sentences with their punctuation
    result = []
    i = 0
    while i < len(sentences):
        sentence = sentences[i].strip()
        if i + 1 < len(sentences):
            punctuation = sentences[i + 1]
            sentence += punctuation
            i += 2
        else:
            i += 1

        if not sentence:
            continue

        # If sentence is too long, split on commas or conjunctions
        if len(sentence) > max_length:
            # Try splitting on commas first
            parts = re.split(r'(,+)', sentence)
            current = ""
            for part in parts:
                if len(current + part) > max_length and current:
                    result.append(current.strip())
                    current = part
                else:
                    current += part
            if current:
                result.append(current.strip())
        else:
            result.append(sentence)

    return [s.strip() for s in result if s.strip()]



