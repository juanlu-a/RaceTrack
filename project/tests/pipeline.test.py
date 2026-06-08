"""
Smoke tests that verify the CI pipeline itself works end-to-end.
These tests always pass — their purpose is to confirm the test runner
is correctly wired up and all lambda modules can be imported.
"""
import importlib.util
import pathlib


_LAMBDAS = [
    "ingest_session",
    "save_session",
    "list_session",
    "list_drivers",
    "driver_summary",
    "driver_laps",
]

_LAMBDAS_ROOT = pathlib.Path(__file__).parent.parent / "lambdas"


def test_all_lambda_handlers_importable():
    for name in _LAMBDAS:
        path = _LAMBDAS_ROOT / name / "handler.py"
        assert path.exists(), f"handler.py missing for {name}"
        spec = importlib.util.spec_from_file_location(f"smoke_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.handler), f"{name}.handler is not callable"


def test_handler_signature():
    for name in _LAMBDAS:
        path = _LAMBDAS_ROOT / name / "handler.py"
        spec = importlib.util.spec_from_file_location(f"sig_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        import inspect
        sig = inspect.signature(mod.handler)
        params = list(sig.parameters)
        assert params == ["event", "context"], \
            f"{name}.handler must accept (event, context), got {params}"
