import unittest

from litebind import Container


class TestVariadicConstructorInjection(unittest.TestCase):
    cont: Container

    def setUp(self):
        self.cont = Container()

    def test_resolve_ignores_inherited_variadic_args_and_kwargs(self):
        class Base:
            def __init__(self, value: int = 7, *args, **kwargs):
                self.value = value
                self.args = args
                self.kwargs = kwargs

        class Derived(Base):
            ...
            # No explicit __init__; inherits Base.__init__ with *args/**kwargs

        child = self.cont.resolve(Derived)  # should ignore *args/**kwargs and use default for 'value'
        assert isinstance(child, Derived)
        assert child.value == 7
        assert child.args == ()
        assert child.kwargs == {}

    def test_resolve_forwards_unmatched_kwargs_through_variadic_kwargs(self):
        class Base:
            def __init__(self, value: int = 7, **kwargs):
                self.value = value
                self.kwargs = kwargs

        class Derived(Base):
            def __init__(self, name: str, **kwargs):
                super().__init__(**kwargs)
                self.name = name

        child = self.cont.resolve(Derived, a=5, name="abc")

        assert isinstance(child, Derived)
        assert child.kwargs["a"] == 5
        assert child.value == 7
        assert child.name == "abc"
