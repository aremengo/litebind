# Dependency Injection Container — How-To Guide
A lightweight DI container with constructor injection, supporting:

- Registrations via concrete implementations, factories, or pre-built instances.
- Lifetimes: SINGLETON and TRANSIENT.
- Autowiring by type hints and name-based tokens.
- Overrides at resolve-time.
- Protocol runtime checks for @runtime_checkable Protocols.

# Resolve Rules (Constructor Injection)

## Overview

Resolution maps a token to a concrete instance. A token may be:

- A registered abstraction (class or protocol)
- A concrete class eligible for auto-wiring

The container supports:

- Factory-based construction
- Constructor-based injection
- Auto-wiring via type hints
- Runtime protocol validation
- Singleton caching

## Algorithm

When calling `resolve` on a container:

1. If a registration exists for the token:
    - If it has a cached singleton instance, it returns it immediately.
    - If it defines a factory, the container invokes it
    - If it defines an impl, the container constructs it using constructor injection


2. If no registration exists and the token is a class, the container tries auto-wiring using the constructor type hints.



3. Runtime validation checks:
    - When resolving a token that is a `@runtime_checkable` Protocol, the returned instance is checked with isinstance. If it doesn't conform, a TypeError is raised.
    - Non runtime-checkable protocols are not checked at runtime.


4. Caching: If the registration’s lifetime is SINGLETON, the instance is cached and reused.

# Lifetimes

- `Lifetime.SINGLETON`: One instance per token registration. Cached after first resolution.
- `Lifetime.TRANSIENT`: A new instance is created for each resolve(...) call.


# Tests

```bash
PYTHONPATH=./src uvx -p 3.10 pytest --show-capture=all -s --log-cli-level=WARNING -- tests/test_*.py
```

# mypy

```bash
uvx mypy src/**
```

# ruff

```bash
uvx ruff check src/**
```