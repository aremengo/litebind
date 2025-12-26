import unittest
from typing import Protocol, runtime_checkable

import pytest

from litebind import Container


class TestRuntimeProtocolNonConformance(unittest.TestCase):
    cont: Container

    @runtime_checkable
    class RepoProtocol(Protocol):
        def get(self) -> int: ...

    class BadRepo:
        # Missing `get`, does not conform to RepoProtocol
        def other(self) -> str:
            return "nope"

    def setUp(self):
        self.cont = Container()

    def test_resolve_raises_type_error_when_factory_returns_non_conforming_instance(self):
        self.cont.register(self.RepoProtocol, factory=lambda _: self.BadRepo())
        # factory path does not raise at register time, but fails at resolution.
        with pytest.raises(TypeError):
            self.cont.resolve(self.RepoProtocol)

    def test_register_instance_raises_type_error_for_non_conforming_instance(self):
        with pytest.raises(TypeError):
            self.cont.register_instance(self.RepoProtocol, self.BadRepo())

    def test_register_raises_type_error_for_non_conforming_class(self):
        with pytest.raises(TypeError):
            self.cont.register(self.RepoProtocol, self.BadRepo)


class TestRuntimeProtocolConformance(unittest.TestCase):
    cont: Container

    @runtime_checkable
    class RepoProtocol(Protocol):
        def get(self) -> int: ...

    class GoodRepo:
        def get(self) -> int:
            return 42

    def setUp(self):
        self.cont = Container()

    def test_resolve_succeeds_when_factory_returns_conforming_instance(self):
        self.cont.register(self.RepoProtocol, factory=lambda _: self.GoodRepo())

        repo = self.cont.resolve(self.RepoProtocol)

        assert isinstance(repo, self.GoodRepo)
        assert repo.get() == 42

    def test_register_instance_succeeds_for_conforming_instance(self):
        repo = self.GoodRepo()

        self.cont.register_instance(self.RepoProtocol, repo)
        resolved = self.cont.resolve(self.RepoProtocol)

        assert resolved is repo
        assert resolved.get() == 42

    def test_register_succeeds_for_conforming_class(self):
        self.cont.register(self.RepoProtocol, self.GoodRepo)

        repo = self.cont.resolve(self.RepoProtocol)

        assert isinstance(repo, self.GoodRepo)
        assert repo.get() == 42


class TestRuntimeProtocolSignatureNonConformance(unittest.TestCase):
    cont: Container

    @runtime_checkable
    class RepoProtocol(Protocol):
        def get(self, key: str) -> int: ...

    def setUp(self):
        self.cont = Container()

    def test_register_raises_type_error_for_method_with_wrong_arity(self):
        class GetNoArgs:
            # Wrong arity: missing an argument
            def get(self) -> int:
                return 1

        with pytest.raises(TypeError):
            self.cont.register(self.RepoProtocol, GetNoArgs)

    def test_register_instance_raises_type_error_for_non_callable_attribute(self):
        class GetIsNotCallable:
            # Attribute exists but is not callable
            get = 123

        with pytest.raises(TypeError):
            self.cont.register_instance(self.RepoProtocol, GetIsNotCallable())

    def test_resolve_raises_type_error_when_factory_returns_wrong_arity_instance(self):
        class GetNoArgs:
            # Wrong arity: missing an argument
            def get(self) -> int:
                return 1

        self.cont.register(self.RepoProtocol, factory=lambda _: GetNoArgs())

        with pytest.raises(TypeError):
            self.cont.resolve(self.RepoProtocol)

    def test_register_raises_type_error_for_wrong_return_type(self):
        class GetReturnsWrongType:
            # Return type mismatch
            def get(self, key: str) -> str:
                return "not an int"

        with pytest.raises(TypeError):
            self.cont.register(self.RepoProtocol, GetReturnsWrongType)


class TestRegisterImplTokenConstraints(unittest.TestCase):
    cont: Container

    def setUp(self):
        self.cont = Container()

    def test_register_impl_requires_impl_to_be_subclass_of_concrete_token(self):
        class Base: ...

        class NotDerived: ...

        with pytest.raises(TypeError):
            self.cont.register(Base, impl=NotDerived)  # Not a subclass of Base

    def test_register_any_impl_with_empty_protocol_succeeds(self):
        class EmptyProto(Protocol): ...

        class AnyClass: ...

        self.cont.register(EmptyProto, impl=AnyClass)

        resolved = self.cont.resolve(EmptyProto)
        assert isinstance(resolved, AnyClass)

    def test_register_impl_requires_impl_to_structurally_conform_to_protocol(self):
        c = Container()

        class Fooer(Protocol):
            def foo(self) -> None: ...

        class FooerImpl:
            def foo(self) -> None:
                pass

        c.register(Fooer, impl=FooerImpl)

        resolved = c.resolve(Fooer)
        assert isinstance(resolved, FooerImpl)


class TestRegisterInstanceReplacement(unittest.TestCase):
    cont: Container

    def setUp(self):
        self.cont = Container()

    def test_register_instance_twice_without_replace_raises_key_error(self):
        c = Container()

        class A: ...

        a1, a2 = A(), A()

        c.register_instance("a_instance", instance=a1)
        with pytest.raises(KeyError):
            c.register_instance("a_instance", instance=a2)

    def test_register_instance_by_string_twice_with_replace_option_substitutes_instance(self):
        c = Container()

        class A: ...

        a1, a2 = A(), A()

        c.register_instance("a_instance", instance=a1)
        c.register_instance("a_instance", instance=a2, replace=True)

        obj = c.resolve("a_instance")
        assert obj == a2

    def test_register_instance_by_type_twice_with_replace_option_substitutes_instance(self):
        c = Container()

        class A: ...

        a1, a2 = A(), A()

        c.register_instance(A, instance=a1)
        c.register_instance(A, instance=a2, replace=True)

        obj = c.resolve(A)
        assert obj == a2
