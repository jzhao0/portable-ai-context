import unittest

from portable_ai_context.compiler import BackendConfig, create_backend, register_backend
from portable_ai_context.errors import CompilerError


class CompilerBackendFactoryContractTests(unittest.TestCase):
    def test_factory_result_must_implement_callable_complete(self):
        name = "test-invalid-backend-result"
        register_backend(name, lambda config: object())

        with self.assertRaises(CompilerError) as caught:
            create_backend(name, BackendConfig())

        self.assertEqual(
            str(caught.exception),
            "compiler backend factory returned an invalid backend",
        )

    def test_none_factory_result_fails_at_construction_seam(self):
        name = "test-none-backend-result"
        register_backend(name, lambda config: None)

        with self.assertRaisesRegex(
            CompilerError,
            "factory returned an invalid backend",
        ):
            create_backend(name, BackendConfig())


if __name__ == "__main__":
    unittest.main()
