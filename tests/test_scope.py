import unittest
from typing import Protocol, runtime_checkable

import pytest

from litebind import Container, Lifetime, Scope


class TestContainerScopeBehavior(unittest.TestCase):
    parent: Container
    scope: Container

    def setUp(self):
        self.parent = Container()
        self.scope = self.parent.create_scope()

    def test_scope_registration_overrides_parent_registration(self):
        class Service: ...

        parent_instance = Service()
        scope_instance = Service()

        self.parent.register(
            Service,
            factory=lambda c: parent_instance,
            lifetime=Lifetime.SINGLETON,
        )

        self.scope.register(
            Service,
            factory=lambda c: scope_instance,
            lifetime=Lifetime.SINGLETON,
        )
        resolved = self.scope.resolve(Service)

        assert resolved is scope_instance

    def test_scope_resolves_from_parent_when_not_registered_locally(self):
        class Service: ...

        instance = Service()

        self.parent.register(
            Service,
            factory=lambda c: instance,
            lifetime=Lifetime.SINGLETON,
        )

        resolved = self.scope.resolve(Service)

        assert resolved is instance

    def test_scope_registering_invalid_runtime_checkable_protocol_raises_type_error(self):
        @runtime_checkable
        class SupportsFoo(Protocol):
            def foo(self) -> int: ...

        class BadImpl: ...

        with pytest.raises(TypeError):
            self.scope.register(
                SupportsFoo,
                impl=BadImpl,
                lifetime=Lifetime.TRANSIENT,
            )


    def test_scope_constructor_direct_call_raises_runtime_error(self):
        with pytest.raises(RuntimeError):
            Scope(self.parent)

