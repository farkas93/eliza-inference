from __future__ import annotations

import pathlib
import tomllib
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
STACK_PATH = ROOT_DIR / "configs" / "eliza-stack.toml"
PROFILE_DIR = ROOT_DIR / "configs" / "profiles"


class StackConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with STACK_PATH.open("rb") as handle:
            cls.config = tomllib.load(handle)

    def test_model_entries_are_flat_records(self) -> None:
        models = self.config.get("models", {})
        self.assertTrue(models)
        for name, model in models.items():
            with self.subTest(model=name):
                self.assertIsInstance(model, dict)
                self.assertIsInstance(model.get("service"), str)
                self.assertIsInstance(model.get("profile"), str)
                self.assertIsInstance(model.get("base_url"), str)

    def test_configured_profiles_exist(self) -> None:
        references: list[tuple[str, str]] = []
        for service in self.config.get("services", []):
            references.append((f"service:{service['name']}", service["profile"]))
        for name, model in self.config.get("models", {}).items():
            references.append((f"model:{name}", model["profile"]))

        for source, profile in references:
            with self.subTest(source=source, profile=profile):
                self.assertTrue((PROFILE_DIR / f"{profile}.env").is_file())

    def test_model_services_reference_configured_services(self) -> None:
        services = {service["name"] for service in self.config.get("services", [])}
        for name, model in self.config.get("models", {}).items():
            with self.subTest(model=name):
                self.assertIn(model["service"], services)


if __name__ == "__main__":
    unittest.main()
