import importlib.util
import os
import pathlib
import sys as _sys

# ── Compatibility fix ────────────────────────────────────────────────────────
# Old 'six' versions (<1.16) register _SixMetaPathImporter without find_spec().
# pytest's --import-mode=importlib calls find_spec() on every sys.meta_path entry.
# Eagerly import moto here (it pulls six/requests) so _SixMetaPathImporter is
# installed now, then add the missing method before collection begins.
try:
    import moto as _moto  # noqa: F401
    for _mp in _sys.meta_path:
        if not hasattr(_mp, "find_spec"):
            _mp.__class__.find_spec = lambda self, name, path, target=None: None
except Exception:
    pass
# ────────────────────────────────────────────────────────────────────────────

import pytest
import requests as _requests

# Set env vars before any handler module is imported so module-level reads pick them up.
os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "S3_BUCKET_NAME": "racetrack-test-sessions",
    "S3_ENDPOINT": "",
    "EVENTS_ENDPOINT": "",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
    "DB_NAME": "racetrack",
    "DB_USER": "racetrack",
    "DB_PASSWORD": "racetrack",
})

_LAMBDAS_ROOT = pathlib.Path(__file__).parent.parent / "lambdas"
_CONTAINERS_ROOT = pathlib.Path(__file__).parent.parent / "containers"

API_BASE_URL = os.environ.get("API_BASE_URL", "").rstrip("/")


def _load_lambda(name: str):
    path = _LAMBDAS_ROOT / name / "handler.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_container_module(container: str, module: str):
    """Load a single .py module from a container dir (e.g. f1_consumer/metrics.py).

    Uses a unique import name so two containers can both define `app`/`metrics`
    without colliding in sys.modules.
    """
    path = _CONTAINERS_ROOT / container / f"{module}.py"
    spec = importlib.util.spec_from_file_location(f"{container}.{module}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Unit test fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def ingest_mod():
    return _load_lambda("ingest_session")


@pytest.fixture(scope="session")
def ingest_worker_mod():
    return _load_lambda("ingest_worker")


@pytest.fixture(scope="session")
def save_mod():
    return _load_lambda("save_session")


@pytest.fixture(scope="session")
def list_session_mod():
    return _load_lambda("list_session")


@pytest.fixture(scope="session")
def list_drivers_mod():
    return _load_lambda("list_drivers")


@pytest.fixture(scope="session")
def driver_summary_mod():
    return _load_lambda("driver_summary")


@pytest.fixture(scope="session")
def driver_laps_mod():
    return _load_lambda("driver_laps")


@pytest.fixture(scope="session")
def consumer_metrics_mod():
    return _load_container_module("f1_consumer", "metrics")


@pytest.fixture(scope="session")
def exporter_clock_mod():
    return _load_container_module("metrics_exporter", "clock")


@pytest.fixture
def apigw_event():
    def _make(params=None):
        return {
            "requestContext": {"http": {"method": "GET"}},
            "queryStringParameters": params or {},
        }
    return _make


@pytest.fixture
def eb_event():
    def _make(bucket, key, session_key):
        return {"detail": {"bucket": bucket, "key": key, "session_key": session_key}}
    return _make


# ── E2E fixtures ───────────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring a live API endpoint")


@pytest.fixture(scope="session")
def api_base():
    if not API_BASE_URL:
        pytest.skip("API_BASE_URL not set — skipping e2e tests")
    return API_BASE_URL


@pytest.fixture(scope="session")
def http():
    """Requests session with a short timeout for e2e calls."""
    session = _requests.Session()
    session.headers.update({"Accept": "application/json"})
    yield session
    session.close()
