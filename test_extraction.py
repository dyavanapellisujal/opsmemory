import asyncio
from opsmemory.core.config import get_settings
from opsmemory.ai.factory import build_llm_provider
from opsmemory.teaching.service import _EXTRACTION_PROMPT, _strip_fences, _heuristic_extract
import json

async def main():
    settings = get_settings()
    llm = build_llm_provider(settings)
    with open("samples/test_incidents/docs/incident-10.md") as f:
        content = f.read()
    
    print("=== HEURISTIC EXTRACT ===")
    print(_heuristic_extract(content))

    if llm:
        print("\n=== LLM EXTRACT ===")
        try:
            raw = await llm.complete(_EXTRACTION_PROMPT, content, max_tokens=1024)
            print("Raw LLM output:", raw)
            data = json.loads(_strip_fences(raw))
            print("Parsed JSON:", data)
        except Exception as e:
            print("Error:", e)
    else:
        print("No LLM configured")

asyncio.run(main())
