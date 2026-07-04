"""AI provider layer: embedding and LLM provider ports plus concrete adapters.

Reasoning and embeddings are selected independently through configuration,
so any combination of providers works (e.g. Gemini embeddings + Groq
reasoning, or Gemini for both).
"""
