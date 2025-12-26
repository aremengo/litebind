from typing import Protocol, runtime_checkable

import pytest

from litebind import Container, Lifetime, ResolutionError


def test_resolve_unregistered_string_token_raises():
    c = Container()
    with pytest.raises(KeyError):
        c.resolve("unknown-token")


def test_resolve_register_singleton_impl_derived_with_token_base_class():
    c = Container()

    class Base: ...

    class Derived(Base): ...

    c.register(Base, impl=Derived, lifetime=Lifetime.SINGLETON)
    a = c.resolve(Base)
    assert isinstance(a, Derived)


def test_resolve_register_transient_impl_derived_with_token_base_class():
    c = Container()

    class Base: ...

    class Derived(Base): ...

    c.register(Base, impl=Derived, lifetime=Lifetime.TRANSIENT)
    a = c.resolve(Base)
    assert isinstance(a, Derived)


def test_resolve_autowires_simple_type():
    c = Container()

    class A: ...

    obj = c.resolve(A)
    assert isinstance(obj, A)


def test_resolve_autowires_recursively_from_annotations():
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


def test_resolve_register_factory_name_based_resolution_no_annotations():
    c = Container()

    class DB: ...

    class RepoNoTypeAnnotation:
        def __init__(self, db):  # no annotation: relies on name-based token
            self.db = db

    c.register("db", factory=lambda _: DB())
    obj = c.resolve(RepoNoTypeAnnotation)
    assert isinstance(obj.db, DB)


def test_resolve_impl_raises_when_dependencies_not_annotated_nor_registered_by_name():
    c = Container()

    class RepoNoTypeAnnotation:
        def __init__(self, db):  # no type annotation
            self.db = db

    # Try resolving without registering named argument
    with pytest.raises(RuntimeError):
        c.resolve(RepoNoTypeAnnotation)


def test_resolve_no_annotation_nor_name_uses_default():
    c = Container()

    class WithDefault:
        def __init__(self, port: int = 5555):
            self.port = port

    obj = c.resolve(WithDefault)
    assert obj.port == 5555


def test_resolve_override_default_argument():
    c = Container()

    class WithDefault:
        def __init__(self, port: int = 5555):
            self.port = port

    obj = c.resolve(WithDefault, port=9898)
    assert obj.port == 9898


def test_unsatisfied_constructor_param_raises():
    c = Container()

    class ClassWithParams:
        def __init__(self, param: int):
            self.param = param

    with pytest.raises(ResolutionError) as ctx:
        c.resolve(ClassWithParams)
    assert "Cannot satisfy constructor parameter 'param'" in str(ctx.value)


def test_factory_can_receive_container():
    c = Container()

    class DB: ...

    def make_db(cont: Container):
        assert isinstance(cont, Container)  # ensure same container arrives
        return DB()

    class RepoNoTypeAnnotation:
        def __init__(self, db):  # no annotation: relies on name-based token
            self.db = db

    c.register("db", factory=make_db)
    obj = c.resolve(RepoNoTypeAnnotation)
    assert isinstance(obj.db, DB)


def test_resolve_register_factory_overrides_values():
    c = Container()

    def make_value(container: Container, value: int = 0):
        assert c is container
        return value

    c.register("value", factory=make_value)
    got = c.resolve("value", value=42)
    assert got == 42


def test_resolve_register_factory_runtime_protocol_check_for_conforming_instance_passes():
    c = Container()

    @runtime_checkable
    class RepoProtocol(Protocol):
        def get(self) -> int: ...

    class RepoImpl:
        def get(self) -> int:
            return 1

    c.register(RepoProtocol, factory=lambda _: RepoImpl())
    repo = c.resolve(RepoProtocol)
    assert isinstance(repo, RepoImpl)
    assert repo.get() == 1


def test_resolve_register_instance_runtime_protocol_check_for_conforming_instance_passes():
    c = Container()

    @runtime_checkable
    class RepoProtocol(Protocol):
        def get(self) -> int: ...

    class RepoImpl:
        def get(self) -> int:
            return 1

    c.register_instance(RepoProtocol, RepoImpl())
    repo = c.resolve(RepoProtocol)
    assert isinstance(repo, RepoImpl)
    assert repo.get() == 1


def test_resolve_register_runtime_protocol_check_for_conforming_instance_passes():
    c = Container()

    @runtime_checkable
    class RepoProtocol(Protocol):
        def get(self) -> int: ...

    class RepoImpl:
        def get(self) -> int:
            return 1

    c.register(RepoProtocol, RepoImpl)
    repo = c.resolve(RepoProtocol)
    assert isinstance(repo, RepoImpl)
    assert repo.get() == 1


def test_resolve_register_factory__non_runtime_protocol_for_non_conforming_raises():
    c = Container()

    class NonRuntimeProtocol(Protocol):
        def do(self) -> None: ...

    c.register(NonRuntimeProtocol, factory=lambda _: object())

    with pytest.raises(TypeError):
        c.resolve(NonRuntimeProtocol)


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


def test_resolve_proto_token_impl_missing_member_func_raises_type_error():
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
        factory=lambda c, r1="r1", r2="r2", name="name": Service(c.resolve(r1), c.resolve(r2), c.resolve(name)),
    )
    c.register("r1", Repo1)
    c.register("r2", Repo2)
    c.register_instance("name", "hello")

    obj = c.resolve("svc", r1="r1", r2="r2")
    assert isinstance(obj.repo1, Repo1)
    assert isinstance(obj.repo2, Repo2)
    assert obj.name == "hello"
