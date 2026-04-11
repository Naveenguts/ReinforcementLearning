from __future__ import annotations

from fastapi import FastAPI, HTTPException

from env import SupplyChainEnv
from models import Action, TaskName
from graders import grade_task

app = FastAPI(title="Supply Chain Chaos Env", version="0.1.0")
env = SupplyChainEnv()


@app.get("/")
def root() -> dict:
    return {"name": "Supply Chain Chaos Env", "status": "ok"}


@app.get("/reset")
@app.post("/reset")
def reset(task: TaskName = TaskName.steady_state) -> dict:
    observation = env.reset(task)
    return observation.model_dump()


@app.get("/state")
def state() -> dict:
    """Return current environment state (OpenEnv state() endpoint)."""
    if env.state is None:
        raise HTTPException(status_code=400, detail="Environment must be reset before accessing state")
    return env.state.model_dump()


@app.post("/step")
def step(action: Action) -> dict:
    try:
        result = env.step(action)
        return result.model_dump()
    except (ValueError, KeyError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/grade")
def grade(task: TaskName = TaskName.steady_state) -> dict:
    """
    Grade current episode.
    
    Returns normalized score in [0.0, 1.0] for the given task.
    Uses the environment's final state and cumulative reward.
    """
    if env.state is None:
        raise HTTPException(status_code=400, detail="Environment must be reset before grading")
    
    score = grade_task(
        task_name=task,
        orders=env.state.orders,
        total_steps_taken=env.state.time_step,
        max_steps=env.max_steps,
        final_reward=env.episode_reward,  # Use cumulative reward from episode
        carbon_footprint=env.state.carbon_footprint,
    )
    
    return {
        "task": task.value,
        "score": round(score, 4),  # Normalize to 4 decimal places
        "normalized_score": f"{score:.2f}",  # Display as 0.XX
        "delivered": sum(1 for o in env.state.orders if o.status.value == "delivered"),
        "late": sum(1 for o in env.state.orders if o.status.value == "late"),
        "total_orders": len(env.state.orders),
        "steps_taken": env.state.time_step,
        "cumulative_reward": round(env.episode_reward_normalized, 2),
        "cumulative_reward_raw": round(env.episode_reward, 2),
    }

