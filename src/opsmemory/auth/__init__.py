"""Authentication: users, sessions, and a provider-agnostic auth service.

The service depends on an :class:`AuthProvider` interface so future OAuth
providers (Google, GitHub, Microsoft) slot in without touching the session,
route-protection, or API layers.
"""
