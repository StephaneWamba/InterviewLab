"""Test PDF extraction and analysis using pdfplumber."""

from src.services.resume_parser import ResumeParser
import asyncio
import sys
import json
from pathlib import Path
import pdfplumber

sys.path.insert(0, str(Path(__file__).parent))


async def test():
    """Test extraction and analysis from CV."""
    file_path = Path("assets/13.pdf")

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        return

    print("=" * 80)
    print("EXTRACTING AND ANALYZING CV (ONE STEP)")
    print("=" * 80)
    print(f"File: {file_path}\n")

    parser = ResumeParser()

    # Test text extraction first
    print("\n" + "=" * 80)
    print("STEP 1: EXTRACTING TEXT FROM PDF (pdfplumber)")
    print("=" * 80)

    # Extract text using pdfplumber
    loop = asyncio.get_event_loop()

    def extract_text():
        text_parts = []
        with pdfplumber.open(str(file_path)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)

    extracted_text = await loop.run_in_executor(None, extract_text)
    print(f"Extracted text length: {len(extracted_text)} chars")
    print(f"First 800 chars:\n{extracted_text[:800]}\n...")

    # Save extracted text
    Path("extracted_text_step1.txt").write_text(
        extracted_text, encoding="utf-8")
    print("Saved to: extracted_text_step1.txt")

    print("\n" + "=" * 80)
    print("STEP 2: ANALYZING EXTRACTED TEXT")
    print("=" * 80)
    print(f"Using extracted text ({len(extracted_text)} chars)")
    print("Sample of text being analyzed:")
    print(extracted_text[:500])
    print("\n...\n")

    analysis = await parser.parse_and_analyze(str(file_path), "pdf")

    print("=" * 80)
    print("PYDANTIC MODEL CONTENTS")
    print("=" * 80)

    print(f"\n📋 PROFILE:")
    if analysis.profile:
        print(
            f"   {analysis.profile[:500]}{'...' if len(analysis.profile) > 500 else ''}")
    else:
        print("   (None)")

    print(f"\n💼 EXPERIENCE:")
    if analysis.experience:
        print(
            f"   {analysis.experience[:500]}{'...' if len(analysis.experience) > 500 else ''}")
    else:
        print("   (None)")

    print(f"\n🎓 EDUCATION:")
    if analysis.education:
        print(
            f"   {analysis.education[:500]}{'...' if len(analysis.education) > 500 else ''}")
    else:
        print("   (None)")

    print(f"\n🚀 PROJECTS:")
    if analysis.projects:
        print(
            f"   {analysis.projects[:500]}{'...' if len(analysis.projects) > 500 else ''}")
    else:
        print("   (None)")

    print(f"\n🎯 HOBBIES:")
    if analysis.hobbies:
        print(
            f"   {analysis.hobbies[:500]}{'...' if len(analysis.hobbies) > 500 else ''}")
    else:
        print("   (None)")

    print("\n" + "=" * 80)
    print("FULL MODEL DUMP (JSON)")
    print("=" * 80)
    print(json.dumps(analysis.model_dump(), indent=2, ensure_ascii=False))

    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    print(f"{'✅' if analysis.profile else '❌'} Profile: {'Yes' if analysis.profile else 'No'}")
    print(f"{'✅' if analysis.experience else '❌'} Experience: {'Yes' if analysis.experience else 'No'}")
    print(f"{'✅' if analysis.education else '❌'} Education: {'Yes' if analysis.education else 'No'}")
    print(f"{'✅' if analysis.projects else '❌'} Projects: {'Yes' if analysis.projects else 'No'}")
    print(f"{'✅' if analysis.hobbies else '❌'} Hobbies: {'Yes' if analysis.hobbies else 'No'}")

    if analysis.profile and analysis.experience and analysis.education and analysis.projects:
        print("\n✅ SAFE TO PROCEED - All sections extracted!")
    else:
        print("\n⚠️  WARNING - Some sections may be missing. Review above.")


if __name__ == "__main__":
    asyncio.run(test())
