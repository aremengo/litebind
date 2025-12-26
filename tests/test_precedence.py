import unittest

from litebind import Container


class TestResolutionPrecedence(unittest.TestCase):
    cont: Container

    def setUp(self):
        self.cont = Container()

    def test_resolve_uses_type_annotation_when_named_registration_factory_exists(self):
        class DB: ...

        class AnotherDB: ...

        class Repo:
            def __init__(self, db: DB):
                self.db = db

        # Register by name
        self.cont.register("db", factory=lambda _: AnotherDB())

        obj = self.cont.resolve(Repo)

        # Use type hint without falling back to name
        assert isinstance(obj.db, DB)
        assert not isinstance(obj.db, AnotherDB)


    def test_resolve_uses_type_annotation_when_named_registration_instance_exists(self):
        class DB: ...

        class AnotherDB: ...

        class Repo:
            def __init__(self, db: DB):
                self.db = db

        # Register by name
        self.cont.register_instance("db", AnotherDB())
        obj = self.cont.resolve(Repo)

        # Use type hint without falling back to name
        assert isinstance(obj.db, DB)
        assert not isinstance(obj.db, AnotherDB)


    def test_resolve_uses_resolve_override_argument_when_type_annotation_exists(self):
        class DB: ...

        class Repo:
            def __init__(self, db: DB):
                self.db = db

        override_db = DB()
        obj = self.cont.resolve(Repo, db=override_db)
        assert obj.db is override_db

    def test_resolve_uses_resolve_override_argument_when_named_registration_exists(self):
        class DB: ...

        class Repo:
            def __init__(self, db):
                self.db = db

        self.cont.register_instance("db", DB())
        override_db = DB()
        obj = self.cont.resolve(Repo, db=override_db)
        assert obj.db is override_db

    def test_resolve_prefers_named_registration_over_default_value(self):
        class WithDefault:
            def __init__(self, port: int = 5555):
                self.port = port

        self.cont.register_instance("port", 1234)
        obj = self.cont.resolve(WithDefault)
        assert obj.port == 1234

    def test_resolve_uses_type_registration_when_named_registration_factory_also_exists(self):
        class Repo: ...

        class NamedRepo(Repo):
            def __init__(self, name: str = ""):
                super().__init__()
                self.name = name

        class Service:
            def __init__(self, repo: Repo):
                self.repo = repo

        # Register both type and name; type should win for the annotated param
        self.cont.register(Repo, impl=NamedRepo)
        self.cont.register("repo", factory=lambda _: Repo())

        obj = self.cont.resolve(Service)

        assert type(obj.repo) is NamedRepo
        assert type(obj.repo) is not Repo

    def test_resolve_uses_type_registration_when_named_instance_registration_also_exists(self):
        class Repo: ...

        class NamedRepo(Repo):
            def __init__(self, name: str = ""):
                super().__init__()
                self.name = name

        class Service:
            def __init__(self, repo: Repo):
                self.repo = repo

        # Register both type and name; type should win for the annotated param
        self.cont.register(Repo, impl=NamedRepo)
        self.cont.register_instance("repo", Repo())

        obj = self.cont.resolve(Service)

        assert type(obj.repo) is NamedRepo
        assert type(obj.repo) is not Repo
