from __future__ import annotations

from fastapi import FastAPI, HTTPException

from env import SupplyChainEnv
from models import Action, TaskName

app = FastAPI(title="Supply Chain Chaos Env", version="0.1.0")
env = SupplyChainEnv()


@app.get("/")
def root() -> dict:
    return {"name": "Supply Chain Chaos Env", "status": "ok"}


@app.get("/reset")
def reset(task: TaskName = TaskName.steady_state) -> dict:
    observation = env.reset(task)
    return observation.model_dump()


@app.post("/step")
def step(action: Action) -> dict:
    try:
        result = env.step(action)
        return result.model_dump()
    except (ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
