from __future__ import annotations

import inspect
import logging
import threading
import typing
from dataclasses import dataclass
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    ParamSpec,
    Protocol,
    TypeVar,
    cast,
    get_type_hints,
    overload,
)


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    T = TypeVar("T")
    # Parameter spec for factories
    P = ParamSpec("P")

    Token = type[T] | str


class Lifetime(Enum):
    SINGLETON = "singleton"
    TRANSIENT = "transient"


@dataclass
class Registration:
    factory: Callable[..., object] | None
    impl: type | None
    lifetime: Lifetime
    cached_instance: object | None = None  # cached singleton


class ResolutionError(RuntimeError):
    pass


class Container:
    """Minimal DI container.

    - register types or factories
    - resolve with constructor injection
    - lifetimes: singleton / transient
    - optional scoping.
    """

    def __init__(self) -> None:
        self._registrations: dict[Any, Registration] = {}
        self._lock = threading.RLock()

    @overload
    def register(
        self,
        token: type[T],
        impl: type[T],
        *,
        factory: None = ...,
        lifetime: Lifetime = Lifetime.SINGLETON,
    ) -> None: ...

    @overload
    def register(
        self,
        token: type[T],
        impl: None = ...,
        *,
        factory: Callable[P, T],
        lifetime: Lifetime = Lifetime.SINGLETON,
    ) -> None: ...

    @overload
    def register(
        self,
        token: str,
        impl: type | None = ...,
        *,
        factory: Callable[..., Any] | None = ...,
        lifetime: Lifetime = Lifetime.SINGLETON,
    ) -> None: ...

    def register(
        self,
        token: Token[T],
        impl: type | None = None,
        *,
        factory: Callable[..., Any] | None = None,
        lifetime: Lifetime = Lifetime.SINGLETON,
    ) -> None:
        """Register a concrete type or a factory for a token.

        Example:
          container.register(IFoo, FooImpl)
          container.register("db", factory=create_db, lifetime=Lifetime.SINGLETON)

        """
        if impl is not None and factory is not None:
            msg = "Provide either `impl` or `factory`, not both."
            raise ValueError(msg)

        if impl is None and factory is None:
            msg = "Either `impl` or `factory` must be provided."
            raise ValueError(msg)

        if impl is not None:  # noqa: SIM102
            # Only validate type tokens. Non-type tokens (like strings) cannot validate statically.
            if inspect.isclass(token):
                self._validate_impl(cls=token, impl=impl)

        with self._lock:
            self._registrations[token] = Registration(factory=factory, impl=impl, lifetime=lifetime)

    def register_instance(
        self,
        token: Token[T],
        instance: object,
        *,
        replace: bool = False,
    ) -> None:
        """Register a pre-built instance (always singleton)."""
        if inspect.isclass(token):
            # Non-type tokens (like strings): cannot validate statically.
            self._validate_impl(cls=token, impl=type(instance))

        # Registration
        with self._lock:
            if not replace and token in self._registrations:
                msg = f"Token {token!r} is already registered. Pass replace=True to overwrite."
                raise KeyError(msg)
            self._registrations[token] = Registration(
                factory=None,
                impl=None,
                lifetime=Lifetime.SINGLETON,
                cached_instance=instance,
            )

    @overload
    def resolve(self, token: type[T], **overrides: Any) -> T: ...

    @overload
    def resolve(self, token: str, **overrides: Any) -> object: ...

    def resolve(self, token: Token[T], **overrides: Any) -> object:  # noqa: C901
        """Resolve the token to an instance.

        - If a registration exists: use it (factory/impl).
        - If no registration and token is a concrete class: attempt auto-wiring by type hints.
        `overrides` lets you explicitly supply constructor args.
        """
        with self._lock:
            reg = self._registrations.get(token)

            # Return cached singleton if present
            if reg and reg.lifetime == Lifetime.SINGLETON and reg.cached_instance is not None:
                return reg.cached_instance

            # Build instance either via factory or constructor
            if reg and reg.factory:
                instance = reg.factory(self, **overrides)
            else:
                if reg and reg.impl:
                    instance = self._construct(reg.impl, **overrides)
                else:
                    if inspect.isclass(token):
                        # If no registration found and token is a class type, try auto-wiring
                        instance = self._construct(token, **overrides)
                    else:
                        msg = f"No registration found for token: {token!r}"
                        raise KeyError(msg)

            if inspect.isclass(token):
                if self._is_protocol(token):
                    try:
                        self._validate_protocol_impl(proto_cls=token, impl=type(instance))
                    except TypeError as e:
                        msg = (
                            f"Resolved instance {type(instance).__name__} does not conform to protocol {token.__name__}"
                        )
                        raise TypeError(msg) from e

                    if self._is_runtime_checkable_protocol(token) and not isinstance(instance, token):
                        # can use 'isinstance' with runtime checkable protocols
                        msg = f"Resolved instance {type(instance).__name__} does not implement runtime protocol {token.__name__}"
                        raise TypeError(msg)

                else:
                    if reg and reg.factory:
                        # factory path; can use isinstance with non-protocol tokens
                        if not isinstance(instance, token):
                            msg = f"Resolved instance {type(instance).__name__} is not an instance of {token.__name__}"
                            raise TypeError(msg)
                    elif reg and reg.impl:
                        # impl path was validated with issubclass at register time,
                        # and auto-wiring constructs the token class itself.
                        pass

            # Cache if singleton
            if reg and reg.lifetime == Lifetime.SINGLETON:
                reg.cached_instance = instance

            return instance

    def _construct(self, cls: type[T], **overrides: Any) -> T:
        return Constructor(self).construct(cls, **overrides)

    def resolve_param(
        self,
        cls: type[T],
        name: str,
        p: inspect.Parameter,
        bound: inspect.BoundArguments,
        hints: dict[str, Any],
    ) -> Any:
        """Resolving param.

        Resolution precedence:
        1. explicit override
        2. type-based registration
        3. name-based registration
        4. default
        5. error.
        """
        # Skip var-positional/var-keyword here; filled only by explicit extras
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            return inspect.Signature.empty

        # 0) already explicitly bound
        if name in bound.arguments:
            return bound.arguments[name]

        # 1) type-based
        ann = hints.get(name, inspect.Signature.empty)
        if ann is not inspect.Signature.empty:
            try_type = False
            if ann in self._registrations or (inspect.isclass(ann) and getattr(ann, "__module__", "") != "builtins"):
                try_type = True

            if try_type:
                try:
                    return self.resolve(ann)
                except KeyError:
                    if name in self._registrations:
                        return self.resolve(name)

        # 2) name-based
        if name in self._registrations:
            return self.resolve(name)

        # 3) default
        if p.default is not inspect.Parameter.empty:
            return p.default

        # 4) error
        ann_repr = getattr(ann, "__name__", repr(ann)) if ann is not inspect.Signature.empty else "no-annotation"
        msg = (
            f"Cannot satisfy constructor parameter '{name}' for {cls.__name__}'. "
            f"No override/registration/default found (annotation: {ann_repr})."
        )
        raise ResolutionError(msg)

    def create_scope(self) -> Scope:
        """Create a scope that prefers its own registrations/instances, falls back to parent."""
        return Scope(self, _from_parent=True)

    def _is_protocol(self, tp: type) -> bool:
        """Detect whether 'tp' is a typing.Protocol subclass (safe)."""
        raise NotImplementedError

    def _is_runtime_checkable_protocol(self, tp: type) -> bool:
        if not self._is_protocol(tp):
            return False

        try:
            isinstance(None, tp)
        except TypeError:
            return False
        else:
            return True

    def _validate_impl(self, cls: type, impl: type) -> None:
        """Validate that 'impl' implements 'cls' when cls is a class/protocol.

        - For normal classes/ABCs: require issubclass(impl, token).
        - For Protocols: avoid issubclass/isinstance unless runtime-checkable.
          Check nominal via MRO; otherwise perform structural conformance.

        Raise ValueError when a non-type cls is passed.
        """
        if not inspect.isclass(cls):
            msg = "Non-type tokens (like strings): cannot validate statically"
            raise ValueError(msg)

        # If token is a normal class or ABC, enforce subclassing strictly
        if not self._is_protocol(cls):
            if not issubclass(impl, cls):
                msg = f"Implementation {impl.__name__} must be a subclass of {cls.__name__}"
                raise TypeError(msg)
            return

        self._validate_protocol_impl(cls, impl)

    def _validate_protocol_impl(self, proto_cls: type, impl: type) -> None:
        # Try nominal conformance without issubclass
        if proto_cls in getattr(impl, "__mro__", ()):
            return

        # Otherwise, check structural conformance
        self._validate_protocol_structural_conformance(proto_cls, impl)

    def _validate_protocol_structural_conformance(self, proto_cls: type, impl: type) -> None:  # noqa: C901
        """Best-effort structural conformance: presence + basic callable arity + return type checks."""
        missing: list[str] = []
        signature_mismatches: list[str] = []

        try:
            proto_hints = get_type_hints(proto_cls, include_extras=True)
        except TypeError:
            proto_hints = {}

        # Attributes required by annotations
        for name in proto_hints:
            if name.startswith("_"):
                continue
            if not hasattr(impl, name):
                missing.append(name)

        for name, proto_attr in proto_cls.__dict__.items():
            if name.startswith("_") or not inspect.isfunction(proto_attr):
                continue

            if not hasattr(impl, name):
                missing.append(name)
                continue

            impl_attr = getattr(impl, name)
            if not callable(impl_attr):
                signature_mismatches.append(f"{name}: not Callable on {impl.__name__}")
                continue

            try:
                proto_sig = inspect.signature(proto_attr)
                impl_sig = inspect.signature(impl_attr)

                proto_params = [p for p in proto_sig.parameters.values() if p.name != "self"]
                impl_params = [p for p in impl_sig.parameters.values() if p.name != "self"]

                def positional_arity(params: list[inspect.Parameter]) -> int:
                    return sum(
                        1
                        for p in params
                        if p.kind
                        in (
                            inspect.Parameter.POSITIONAL_ONLY,
                            inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        )
                        and p.default is inspect.Parameter.empty
                    )

                if positional_arity(impl_params) < positional_arity(proto_params):
                    signature_mismatches.append(
                        f"{name}: impl has fewer required positional params "
                        f"({positional_arity(impl_params)}) than protocol "
                        f"({positional_arity(proto_params)})"
                    )

                # --- NEW: return annotation validation ---
                proto_ret = proto_sig.return_annotation
                impl_ret = impl_sig.return_annotation

                if (
                    proto_ret is not inspect.Signature.empty
                    and impl_ret is not inspect.Signature.empty
                    and proto_ret is not Any
                    and impl_ret is not Any
                ):
                    if not _is_return_type_compatible(impl_ret, proto_ret):
                        signature_mismatches.append(
                            f"{name}: return type {impl_ret!r} is not compatible with "
                            f"protocol return type {proto_ret!r}"
                        )

            except Exception as e:  # noqa: BLE001
                signature_mismatches.append(f"{name}: unable to compare signatures ({e})")

        if missing or signature_mismatches:
            msgs = []
            if missing:
                msgs.append(f"missing members: {', '.join(missing)}")
            if signature_mismatches:
                msgs.append(f"signature mismatches: {', '.join(signature_mismatches)}")

            msg = (
                f"Implementation {impl.__name__} does not structurally conform to protocol "
                f"{proto_cls.__name__}: {'; '.join(msgs)}"
            )
            raise TypeError(msg)


def _is_return_type_compatible(impl_ret: object, proto_ret: object) -> bool:
    # Exact match
    if impl_ret == proto_ret:
        return True

    # Handle class-based covariance
    if isinstance(impl_ret, type) and isinstance(proto_ret, type):
        return issubclass(impl_ret, proto_ret)

    # Everything else (Union, Protocol, TypeVar, etc.) → conservative failure
    return False


class Scope(Container):
    """A scoped container that looks up in itself first, then falls back to a parent container.

    Useful for per-request/per-test lifetimes without altering root registrations.
    """

    def __init__(self, parent: Container, *, _from_parent: bool = False) -> None:
        if not _from_parent:
            msg = "Scope instances must be created via Container.create_scope()"
            raise RuntimeError(msg)
        super().__init__()
        self._parent = parent

    @overload
    def resolve(self, token: type[T], **overrides: Any) -> T: ...

    @overload
    def resolve(self, token: str, **overrides: Any) -> object: ...

    def resolve(self, token: Token[T], **overrides: Any) -> object:  # noqa: C901
        """Resolve the token to an instance.

        Resolves the token using registrations in this scope. If the token is not
        registered locally, resolution falls back to the parent container.
        """
        with self._lock:
            reg = self._registrations.get(token)

            if not reg:
                # Fallback to parent
                return self._parent.resolve(token, **overrides)

            return super().resolve(token, **overrides)


class Constructor:
    def __init__(self, resolver: Container) -> None:
        self._resolver = resolver

    def construct(self, cls: type[T], **overrides: Any) -> T:
        if "__init__" not in cls.__dict__:
            return cls()

        sig = inspect.signature(cls)
        params = sig.parameters

        overrides = overrides or {}
        overrides.pop("self", None)  # never allow passing 'self'

        kw_overrides, posonly_overrides = self._split_positional_only(overrides, params)

        bound = self._bind_explicit(sig, kw_overrides, cls)

        self._inject_positional_only(bound, posonly_overrides)

        self._fill_missing_arguments(cls, sig, bound)

        args, kwargs = self._materialize_call(sig, bound)
        return cls(*args, **kwargs)

    def _materialize_call(
        self, sig: inspect.Signature, bound: inspect.BoundArguments
    ) -> tuple[list[Any], dict[str, Any]]:
        params = sig.parameters
        args, kwargs = [], {}

        # positional-only
        for name, p in params.items():
            if p.kind is p.POSITIONAL_ONLY:
                args.append(bound.arguments[name])

        # *args
        for name, p in params.items():
            if p.kind is p.VAR_POSITIONAL:
                captured = tuple(bound.arguments.get(name, ()))
                args.extend(captured)
                break

        # keywords
        for name, p in params.items():
            if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
                kwargs[name] = bound.arguments[name]

        # **kwargs
        for name, p in params.items():
            if p.kind is p.VAR_KEYWORD:
                kwargs.update(bound.arguments.get(name, {}))
                break

        return args, kwargs

    def _fill_missing_arguments(self, cls: type[T], sig: inspect.Signature, bound: inspect.BoundArguments) -> None:
        hints = _get_init_type_hints(cls)

        for name, p in sig.parameters.items():
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue

            if name not in bound.arguments:
                value = self._resolver.resolve_param(cls, name, p, bound, hints)
                if value is not inspect.Signature.empty:
                    bound.arguments[name] = value

    def _inject_positional_only(self, bound: inspect.BoundArguments, posonly_overrides: dict[str, Any]) -> None:
        for name, value in posonly_overrides.items():
            bound.arguments[name] = value

    def _split_positional_only(
        self,
        overrides: dict[str, Any],
        params: Mapping[str, inspect.Parameter],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        pos_only = {name for name, p in params.items() if p.kind is inspect.Parameter.POSITIONAL_ONLY}

        return (
            {k: v for k, v in overrides.items() if k not in pos_only},
            {k: v for k, v in overrides.items() if k in pos_only},
        )

    def _bind_explicit(self, sig: inspect.Signature, kw: dict[str, Any], cls: type[T]) -> inspect.BoundArguments:
        try:
            return sig.bind_partial(**kw)
        except TypeError as e:
            msg = f"Overrides don't match {cls.__name__} signature: {e}"
            raise TypeError(msg) from e


if hasattr(typing, "is_protocol"):
    # https://docs.python.org/3/library/typing.html#typing.is_protocol
    def _is_protocol_3_13(self: Any, tp: type) -> bool:
        return inspect.isclass(tp) and typing.is_protocol(tp)

    Container._is_protocol = _is_protocol_3_13  # type: ignore[method-assign] # noqa: SLF001
else:

    def _is_protocol_legacy(self: Any, tp: type) -> bool:
        """Detect whether 'tp' is a typing.Protocol subclass (safe)."""
        return inspect.isclass(tp) and issubclass(tp, cast("type", Protocol))

    Container._is_protocol = _is_protocol_legacy  # type: ignore[method-assign] # noqa: SLF001


def _get_init_type_hints(cls: type[T]) -> dict[str, Any]:
    try:
        init = inspect.getattr_static(cls, "__init__")
        hints = get_type_hints(init)
    except TypeError:
        hints = {}
    except NameError as exc:
        logger.warning("'%s' name error retrieving %s (%s) type hints", exc.name, cls.__name__, cls.__qualname__)
        hints = {}

    return hints
