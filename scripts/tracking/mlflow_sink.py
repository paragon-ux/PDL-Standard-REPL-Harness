from __future__ import annotations

from pathlib import Path
from typing import Any

import mlflow


class MlflowRunLogger:
    """Tracking-only run logger.

    This logger lives outside the observed semantic path. It indexes evidence
    after the fact.
    """

    def __init__(self, run_name: str, params: dict[str, Any] | None = None):
        self._mlflow = mlflow
        self._run = mlflow.start_run(run_name=run_name)
        if params:
            mlflow.log_params(params)

    @property
    def run_id(self) -> str:
        return self._run.info.run_id

    def log_params(self, params: dict[str, Any]) -> None:
        self._mlflow.log_params(params)

    def log_metrics(self, metrics: dict[str, float]) -> None:
        self._mlflow.log_metrics(metrics)

    def log_artifact(self, path: str | Path) -> None:
        self._mlflow.log_artifact(str(path))

    def finish(self) -> None:
        self._mlflow.end_run()


def log_experiment_run(
    run_name: str,
    *,
    params: dict[str, Any],
    metrics: dict[str, float],
    artifacts: list[str | Path],
) -> str:
    """Log one tracking-only run.

    This function is never called from the observed semantic path.
    """
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        for artifact in artifacts:
            path = Path(artifact)
            if not path.is_file():
                raise FileNotFoundError(f"required evidence pointer missing: {path}")
            mlflow.log_artifact(str(path))
        return run.info.run_id
