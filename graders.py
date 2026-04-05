"""
Task graders for Supply Chain Chaos environment.

Each grader takes a final state and returns a normalized score in [0.0, 1.0].
Meta requires deterministic, reproducible graders with clear success criteria.

Scoring methodology:
- Primary: delivered orders percentage
- Secondary: late order penalties
- Tertiary: efficiency (steps used)
- Normalization: score = (delivered_ratio - late_penalty + efficiency_bonus) clamped to [0.0, 1.0]
"""

from __future__ import annotations

from typing import List

from models import Order, OrderStatus, TaskName


# Max possible score represents perfect performance on each task
MAX_REWARD_BY_TASK = {
    TaskName.steady_state: 350.0,    # 3 orders × 50 + early bonus 50 + misc 100 = ~300-350
    TaskName.port_strike: 420.0,     # 4 orders × 50 + early bonus 50 + misc 120 = ~300-420
    TaskName.black_swan: 500.0,      # 5 orders × 50 + early bonus 50 + misc 150 = ~300-500
}


class TaskGrader:
    """Base class for task graders."""

    def grade(
        self,
        task_name: TaskName,
        orders: List[Order],
        total_steps_taken: int,
        max_steps: int,
        final_reward: float,
    ) -> float:
        """
        Grade task performance on normalized [0.0, 1.0] scale.

        Args:
            task_name: The task that was attempted
            orders: Final order states
            total_steps_taken: Steps consumed in episode
            max_steps: Maximum steps allowed
            final_reward: Final cumulative reward

        Returns:
            Score in [0.0, 1.0]:
            - 1.0 = perfect (all orders delivered on time, max reward)
            - 0.8-0.99 = excellent (≥80% delivered, strong reward)
            - 0.6-0.79 = good (≥60% delivered, meaningful progress)
            - 0.4-0.59 = partial (≥40% delivered, some recovery)
            - 0.0-0.39 = poor (insufficient delivery or losses)
        """
        raise NotImplementedError


class SteadyStateGrader(TaskGrader):
    """Grader for steady_state task (baseline, no disruptions)."""

    def grade(
        self,
        task_name: TaskName,
        orders: List[Order],
        total_steps_taken: int,
        max_steps: int,
        final_reward: float,
    ) -> float:
        """
        steady_state scoring (easy task):
        - 3 orders with zero disruptions
        - Expected: agent delivers all on time
        - Perfect: all delivered + no lates + early = 1.0
        - Reward-normalized: reward / 350
        """
        delivered = sum(1 for o in orders if o.status == OrderStatus.delivered)
        late = sum(1 for o in orders if o.status == OrderStatus.late)
        total = len(orders)

        if total == 0:
            return 0.0

        # Reward-based normalization
        max_reward = MAX_REWARD_BY_TASK.get(task_name, 350.0)
        reward_score = min(final_reward / max_reward, 1.0)

        # Order-based metrics as secondary validation
        delivered_ratio = min(delivered / total, 1.0)
        late_penalty = 0.0 if late == 0 else (late / total) * 0.15

        # Blend: 70% reward, 30% order metrics
        blended = (0.7 * reward_score) + (0.3 * (delivered_ratio - late_penalty))
        return max(0.0, min(blended, 1.0))


class PortStrikeGrader(TaskGrader):
    """Grader for port_strike task (route blockage, +1 order)."""

    def grade(
        self,
        task_name: TaskName,
        orders: List[Order],
        total_steps_taken: int,
        max_steps: int,
        final_reward: float,
    ) -> float:
        """
        port_strike scoring (medium task):
        - 4 orders, R3 blocked at step 5
        - Expected: agent reroutes and adapts
        - Perfect: all 4 delivered despite blockage = 1.0
        - Reward-normalized: reward / 420
        """
        delivered = sum(1 for o in orders if o.status == OrderStatus.delivered)
        late = sum(1 for o in orders if o.status == OrderStatus.late)
        total = len(orders)

        if total == 0:
            return 0.0

        # Reward-based normalization
        max_reward = MAX_REWARD_BY_TASK.get(task_name, 420.0)
        reward_score = min(final_reward / max_reward, 1.0)

        # Order-based metrics
        delivered_ratio = min(delivered / total, 1.0)
        late_penalty = 0.0 if late == 0 else (late / total) * 0.20  # Harsher penalty

        # Medium task: reward weighted higher (difficulty spike)
        blended = (0.75 * reward_score) + (0.25 * (delivered_ratio - late_penalty))
        return max(0.0, min(blended, 1.0))


class BlackSwanGrader(TaskGrader):
    """Grader for black_swan task (hardest: cascading disruptions)."""

    def grade(
        self,
        task_name: TaskName,
        orders: List[Order],
        total_steps_taken: int,
        max_steps: int,
        final_reward: float,
    ) -> float:
        """
        black_swan scoring (hard task):
        - 5 orders, cascading disruptions (route block, demand spike, fuel surge)
        - Partial success expected and rewarded
        - Graceful degradation: 1 order delivered = 0.3, 5 orders = 1.0
        - Reward-normalized: reward / 500
        """
        delivered = sum(1 for o in orders if o.status == OrderStatus.delivered)
        late = sum(1 for o in orders if o.status == OrderStatus.late)
        total = len(orders)

        if total == 0:
            return 0.0

        # Reward-based normalization (primary for hard task)
        max_reward = MAX_REWARD_BY_TASK.get(task_name, 500.0)
        reward_score = min(final_reward / max_reward, 1.0)

        # Order-based graceful degradation scale
        # 5→1.0, 4→0.90, 3→0.75, 2→0.55, 1→0.30, 0→0.0
        delivered_ratio = min(delivered / total, 1.0)
        graceful_scale = {5: 1.0, 4: 0.90, 3: 0.75, 2: 0.55, 1: 0.30, 0: 0.0}
        order_score = graceful_scale.get(delivered, 0.0)

        # Late penalty (harsh)
        late_penalty = 0.0 if late == 0 else (late / total) * 0.25

        # Hard task: equal weight on reward vs graceful degradation
        blended = (0.5 * reward_score) + (0.5 * (order_score - late_penalty))
        return max(0.0, min(blended, 1.0))


def grade_task(
    task_name: TaskName,
    orders: List[Order],
    total_steps_taken: int,
    max_steps: int,
    final_reward: float,
) -> float:
    """
    Public grading interface.

    Args:
        task_name: Task identifier
        orders: Final order states
        total_steps_taken: Steps consumed
        max_steps: Maximum steps allowed
        final_reward: Final cumulative episode reward (NOT per-step)

    Returns:
        Normalized score in [0.0, 1.0]
    """
    if task_name == TaskName.steady_state:
        grader = SteadyStateGrader()
    elif task_name == TaskName.port_strike:
        grader = PortStrikeGrader()
    elif task_name == TaskName.black_swan:
        grader = BlackSwanGrader()
    else:
        grader = SteadyStateGrader()

    return grader.grade(task_name, orders, total_steps_taken, max_steps, final_reward)

