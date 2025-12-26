"""Minimal dependency injection library.

This package provides a lightweight dependency injection library for Python,
allowing registration and resolution of types, factories, and pre-built instances
with configurable lifetimes and optional scoping.

Exports:
- `Container`: Main DI container supporting type/factory registration and resolution.
- `Lifetime`: Enum for controlling object lifetimes (e.g., singleton or transient).
- `Scope`: Scoped container that resolves within itself first, then falls back
  to a parent container. Useful for per-request or per-test lifetimes.
"""

from ._container import Container, Lifetime, ResolutionError, Scope


__all__ = ["Container", "Lifetime", "ResolutionError", "Scope"]
