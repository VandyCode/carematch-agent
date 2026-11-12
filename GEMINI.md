# CareMatch — Repository Context for AI Assistants

## Project Summary
CareMatch (`carematch-agent`) is an open-source, multi-agent Healthcare Quality & Medicare Coverage Navigator built with Python, FastAPI, Pydantic v2, Google ADK, and the A2A protocol.

## Layout
- `tools.py` & `app/tools.py`: 9 Pydantic-validated domain tools + `TOOL_JSON_SCHEMAS`.
- `memory.py` & `app/memory.py`: Thread-safe SQLite store, rolling compaction, `AsyncMemoryWorker`.
- `app/agent.py`: ADK Supervisor (`carematch`) + 3 specialist sub-agents (`hospital_quality_agent`, `surgeon_outcomes_agent`, `medicare_coverage_agent`).
- `app/orchestration.py`: `ModelRouter`, `InputGuardrail` (injection + 911 emergency), `OutputGuardrail`, `HITLController`.
- `app/telemetry.py`: `PIIRedactor` (HIPAA Safe-Harbor) & `AgentTracer` (OpenTelemetry spans).
- `app/cms_data.py` & `app/cms_connector.py`: Public federal CMS.gov & HHS NPPES datasets and optional live connectors.
- `app/fast_api_app.py`: FastAPI REST + A2A server and interactive `/dashboard` UI.
- `tests/`: Unit rubric suite (`test_rubric_95.py`), domain tests (`test_carematch.py`), FastAPI integration tests (`test_server_e2e.py`), and Golden Eval Harness (`tests/eval/eval_harness.py`).

## Engineering Rules
1. Never store or log real patient PHI/PII; pass all untrusted text through `PIIRedactor.redact()`.
2. Keep every data source grounded exclusively in public federal datasets (CMS.gov, Medicare Care Compare, HHS NPPES).
3. Run `pytest tests/unit tests/integration -v` and `python tests/eval/eval_harness.py` after any code change.
