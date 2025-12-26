import unittest

from litebind import Container, Lifetime


class TestLifetimeControl(unittest.TestCase):
    cont: Container

    def setUp(self):
        self.cont = Container()

    def test_resolve_register_singleton_returns_same_instance(self):
        class A: ...

        self.cont.register(A, impl=A, lifetime=Lifetime.SINGLETON)
        a1 = self.cont.resolve(A)
        a2 = self.cont.resolve(A)
        assert a2 is a1, "SINGLETON should return the cached instance"

    def test_resolve_register_transient_returns_new_instances(self):
        class A: ...

        self.cont.register(A, impl=A, lifetime=Lifetime.TRANSIENT)
        a1 = self.cont.resolve(A)
        a2 = self.cont.resolve(A)
        assert a2 is not a1, "TRANSIENT should return new instances"

    def test_register_instance_is_always_singleton(self):
        class A: ...

        inst = A()
        self.cont.register_instance(A, inst)
        a = self.cont.resolve(A)
        b = self.cont.resolve(A)
        assert a is inst
        assert b is inst
