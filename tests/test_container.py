from typing import Protocol, runtime_checkable

import pytest

from litebind import Container, Lifetime


def test_resolve_impl_derived_with_token_base_class():
    c = Container()

    class Base:
        def __init__(self): ...

    class Derived(Base): ...

    c.register(Base, impl=Derived, lifetime=Lifetime.SINGLETON)
    a = c.resolve(Base)
    b = c.resolve(Base)
    assert isinstance(a, Derived)
    assert a is b, "SINGLETON should return the cached instance"


def test_resolve_register_transient_returns_new_instances():
    c = Container()

    class Base: ...

    class Derived(Base): ...

    c.register(Base, impl=Derived, lifetime=Lifetime.TRANSIENT)
    a = c.resolve(Base)
    b = c.resolve(Base)
    assert isinstance(a, Derived)
    assert isinstance(b, Derived)
    assert a is not b, "TRANSIENT should return a new instance each time"


def test_register_instance_is_always_singleton():
    c = Container()

    class Base: ...

    class Derived(Base): ...

    inst = Derived()
    c.register_instance(Base, inst)
    a = c.resolve(Base)
    b = c.resolve(Base)
    assert a is inst
    assert b is inst


def test_register_impl_type_must_be_subclass():
    c = Container()

    class Base: ...

    class NotDerived: ...

    with pytest.raises(TypeError):
        c.register(Base, impl=NotDerived)  # Not a subclass of Base


def test_resolve_unregistered_non_class_token_raises():
    c = Container()
    with pytest.raises(KeyError):
        c.resolve("unknown-token")


def test_resolve_auto_wires_simple_class_without_registration():
    c = Container()

    class ClassNoDeps:
        def __init__(self) -> None:
            self.value = "ok"

    obj = c.resolve(ClassNoDeps)
    assert isinstance(obj, ClassNoDeps)
    assert obj.value == "ok"


def test_autowire_types_recursively():
    # No registrations
    c = Container()

    class DB: ...

    class Repo:
        def __init__(self, db: DB):
            self.db = db

    class Service:
        def __init__(self, repo: Repo):
            self.repo = repo

    svc = c.resolve(Service)
    assert isinstance(svc, Service)
    assert isinstance(svc.repo, Repo)
    assert isinstance(svc.repo.db, DB)


def test_name_based_resolution_without_annotation():
    c = Container()

    class DB: ...

    class RepoNoTypeAnnotation:
        def __init__(self, db):  # no annotation: relies on name-based token
            self.db = db

    c.register("db", factory=lambda _: DB())
    obj = c.resolve(RepoNoTypeAnnotation)
    assert isinstance(obj.db, DB)


def test_no_name_nor_annotation_resolution_fails():
    c = Container()

    class RepoNoTypeAnnotation:
        def __init__(self, db):  # no type annotation
            self.db = db

    # Try resolving without registering named argument
    with pytest.raises(RuntimeError):
        c.resolve(RepoNoTypeAnnotation)


def test_precedence_use_type_hint_over_named_param():
    c = Container()

    class DB: ...

    class Repo:
        def __init__(self, db: DB):
            self.db = db

    class AnotherClass: ...

    # Register by name
    c.register("db", factory=lambda _: AnotherClass())

    obj = c.resolve(Repo)
    # Use type hint without falling back to name
    assert isinstance(obj.db, DB)
    assert not isinstance(obj.db, AnotherClass)


def test_precedence_override_parameter():
    c = Container()

    class DB: ...

    class Repo:
        def __init__(self, db: DB):
            self.db = db

    override_db = DB()
    obj = c.resolve(Repo, db=override_db)
    assert obj.db is override_db


def test_name_registration_beats_default():
    c = Container()

    class WithDefault:
        def __init__(self, port: int = 5555):
            self.port = port

    c.register("port", factory=lambda _: 1234)
    obj = c.resolve(WithDefault)
    assert obj.port == 1234


def test_no_annotation_nor_name_uses_default():
    c = Container()

    class WithDefault:
        def __init__(self, port: int = 5555):
            self.port = port

    obj = c.resolve(WithDefault)
    assert obj.port == 5555


def test_override_default_argument():
    c = Container()

    class WithDefault:
        def __init__(self, port: int = 5555):
            self.port = port

    obj = c.resolve(WithDefault, port=9898)
    assert obj.port == 9898


def test_unsatisfied_constructor_param_raises():
    c = Container()

    class ClassWithParams:
        def __init__(self, missing: int):
            self.missing = missing

    with pytest.raises(RuntimeError) as ctx:
        c.resolve(ClassWithParams)
    assert "Cannot satisfy constructor parameter 'missing'" in str(ctx.value)


def test_factory_can_receive_container():
    c = Container()

    class DB: ...

    def make_db(cont: Container):
        assert isinstance(cont, Container)  # ensure same container arrives
        return DB()

    class RepoNoTypeAnnotation:
        def __init__(self, db):  # no annotation: relies on name-based token
            self.db = db

    c.register("db", factory=lambda _: make_db(c))
    obj = c.resolve(RepoNoTypeAnnotation)
    assert isinstance(obj.db, DB)


def test_factory_override_values():
    c = Container()

    def make_value(c: Container, value: int = 0):
        return value

    c.register("value", factory=make_value)
    got = c.resolve("value", value=42)
    assert got == 42


def test_runtime_protocol_check_passes_for_conforming_instance():
    c = Container()

    @runtime_checkable
    class RepoProtocol(Protocol):
        def get(self) -> int: ...

    class RepoImpl:
        def __init__(self): ...

        def get(self) -> int:
            return 1

    # Use factory to avoid static `_validate_impl` protocol path
    c.register(RepoProtocol, factory=lambda _: RepoImpl())
    repo = c.resolve(RepoProtocol)
    assert isinstance(repo, RepoImpl)
    assert repo.get() == 1


def test_runtime_protocol_check_raises_for_non_conforming_instance():
    c = Container()

    @runtime_checkable
    class RepoProtocol(Protocol):
        def get(self) -> int: ...

    class BadRepo:
        def __init__(self): ...

        # Missing `get`, does not conform to RepoProtocol
        def other(self) -> str:
            return "nope"

    c.register(RepoProtocol, factory=lambda _: BadRepo())
    with pytest.raises(TypeError):
        c.resolve(RepoProtocol)


def test_non_runtime_protocol_does_not_trigger_isinstance_check():
    c = Container()

    class NonRuntimeProtocol(Protocol):
        def do(self) -> None: ...

    c.register(NonRuntimeProtocol, factory=lambda _: object())
    obj = c.resolve(NonRuntimeProtocol)
    assert obj is not None


def test_type_hint_beats_name_when_type_is_registered():
    c = Container()

    class DB: ...

    class Repo:
        def __init__(self, db: DB):
            self.db = db

    class Service:
        def __init__(self, repo: Repo):
            self.repo = repo

    class NamedRepo(Repo):
        def __init__(self, db: DB, name: str = ""):
            super().__init__(db)
            self.name = name

    # Register both type and name; type should win for the annotated param
    c.register(Repo, impl=NamedRepo)
    c.register("repo", factory=lambda _: Repo(DB()))

    obj = c.resolve(Service)

    assert type(obj.repo) is NamedRepo


def test_name_based_factory():
    c = Container()

    class DB: ...

    class Repo:
        def __init__(self, db: DB):
            self.db = db

    class Service:
        def __init__(self, repo: Repo):
            self.repo = repo

    # Register name annotated param
    c.register("repo", factory=lambda _: Repo(DB()))

    obj = c.resolve(Service)
    assert type(obj.repo) is Repo


def test_name_is_used_when_type_not_registered_and_no_default():
    c = Container()

    class DB: ...

    class RepoNoTypeAnnotation:
        def __init__(self, db):
            self.db = db

    c.register("db", factory=lambda _: DB())
    obj = c.resolve(RepoNoTypeAnnotation)
    assert isinstance(obj.db, DB)


def test_resolve_class_inheriting_varargs_parent_init():
    c = Container()

    class Parent:
        def __init__(self, value: int = 7, *args, **kwargs):
            self.value = value
            self.args = args
            self.kwargs = kwargs

    class Child(Parent):
        ...
        # No explicit __init__; inherits Parent.__init__ with *args/**kwargs

    child = c.resolve(Child)  # should ignore *args/**kwargs and use default for 'value'
    assert isinstance(child, Child)
    assert child.value == 7
    assert child.args == ()
    assert child.kwargs == {}


def test_resolve_class_token_init_with_variadic_kwargs():
    c = Container()

    class Parent:
        def __init__(self, value: int = 7, **kwargs):
            self.value = value
            self.kwargs = kwargs

    class Child(Parent):
        def __init__(self, name: str, **kwargs):
            super().__init__(**kwargs)
            self.name = name

    child = c.resolve(Child, a=5, name="abc")

    assert isinstance(child, Child)
    assert child.kwargs["a"] == 5
    assert child.value == 7
    assert child.name == "abc"


def test_register_instance_twice_without_replace_raises_keyerror():
    c = Container()

    class A: ...

    a1, a2 = A(), A()

    c.register_instance("a_instance", instance=a1)
    with pytest.raises(KeyError):
        c.register_instance("a_instance", instance=a2)


def test_register_instance_by_string_twice_with_replace_substitutes_instance():
    c = Container()

    class A: ...

    a1, a2 = A(), A()

    c.register_instance("a_instance", instance=a1)
    c.register_instance("a_instance", instance=a2, replace=True)

    obj = c.resolve("a_instance")
    assert obj == a2


def test_register_instance_by_type_twice_with_replace_substitutes_instance():
    c = Container()

    class A: ...

    a1, a2 = A(), A()

    c.register_instance(A, instance=a1)
    c.register_instance(A, instance=a2, replace=True)

    obj = c.resolve(A)
    assert obj == a2


def test_scope_prefers_own_registration_over_parent():
    parent = Container()
    scope = parent.create_scope()

    class Service: ...

    parent_instance = Service()
    scope_instance = Service()

    parent.register(
        Service,
        factory=lambda c: parent_instance,
        lifetime=Lifetime.SINGLETON,
    )

    scope.register(
        Service,
        factory=lambda c: scope_instance,
        lifetime=Lifetime.SINGLETON,
    )

    resolved = scope.resolve(Service)

    assert resolved is scope_instance


def test_scope_falls_back_to_parent_when_unregistered():
    parent = Container()
    scope = parent.create_scope()

    class Service: ...

    instance = Service()

    parent.register(
        Service,
        factory=lambda c: instance,
        lifetime=Lifetime.SINGLETON,
    )

    resolved = scope.resolve(Service)

    assert resolved is instance


def test_scope_register_runtime_checkable_proto_violation_raises_type_error():
    parent = Container()
    scope = parent.create_scope()

    @runtime_checkable
    class SupportsFoo(Protocol):
        def foo(self) -> int: ...

    class BadImpl: ...

    with pytest.raises(TypeError):
        scope.register(
            SupportsFoo,
            impl=BadImpl,
            lifetime=Lifetime.TRANSIENT,
        )


def test_resolve_proto_impl_with_less_args_raises_type_error():
    container = Container()

    class SupportsFoo(Protocol):
        def foo(self, a, b) -> int: ...

    class BadImpl:
        def foo(self, a) -> int: ...

    with pytest.raises(TypeError):
        container.register(
            SupportsFoo,
            impl=BadImpl,
        )


def test_resolve_proto_impl_with_more_args_does_not_raise():
    container = Container()

    class SupportsFoo(Protocol):
        def foo(self, a) -> int: ...

    class Impl:
        def foo(self, a, b) -> int: ...

    container.register(
        SupportsFoo,
        impl=Impl,
    )


def test_resolve_runtime_checkable_proto_impl_missing_member_func_raises_type_error():
    container = Container()

    @runtime_checkable
    class SupportsFoo(Protocol):
        def foo(self, a) -> int: ...
        def bar(self) -> int: ...

    class Impl:
        def foo(self, a, b) -> int: ...

    with pytest.raises(TypeError):
        container.register(
            SupportsFoo,
            impl=Impl,
        )


def test_resolve_proto_impl_missing_member_func_raises_type_error():
    container = Container()

    class SupportsFoo(Protocol):
        def foo(self, a) -> int: ...
        def bar(self) -> int: ...

    class Impl:
        def foo(self, a, b) -> int: ...

    with pytest.raises(TypeError):
        container.register(
            SupportsFoo,
            impl=Impl,
        )


def test_resolve_named_dependencies_factory():
    c = Container()

    class Repo1: ...

    class Repo2: ...

    class Service:
        def __init__(self, repo1: Repo1, repo2: Repo2, name: str = ""):
            self.repo1 = repo1
            self.repo2 = repo2
            self.name = name

    # Register by name
    c.register(
        "svc",
        factory=lambda c, r1="r1", r2="r2", name="name": Service(
            c.resolve(r1), c.resolve(r2), c.resolve(name)
        ),
    )
    c.register("r1", Repo1)
    c.register("r2", Repo2)
    c.register_instance("name", "hello")

    obj = c.resolve("svc", r1="r1", r2="r2")
    assert isinstance(obj.repo1, Repo1)
    assert isinstance(obj.repo2, Repo2)
    assert obj.name == "hello"




def test_resolve_named_dependencies_factory_xxxxx():
    c = Container()

    class A: ...

    class B:
        def __init__(self, a, /, b) -> None:
            self.a = a
            self.b = b

    c.register("a", A)
    c.register("b", str)
    obj = c.resolve(B)

    assert isinstance(obj.a, A)
    assert isinstance(obj.b, str)
