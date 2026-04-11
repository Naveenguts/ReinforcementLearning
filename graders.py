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

import math
from typing import List

from models import Order, OrderStatus, TaskName


def _constrain_score(score: float, epsilon: float = 0.0001) -> float:
    """
    Constrain score to strictly between 0 and 1 (exclusive bounds).
    
    Maps [0, 1] to (epsilon, 1-epsilon) to ensure:
    - score > 0 and score < 1 (never exactly 0.0 or 1.0)
    - Linear scaling: 0.5 maps to 0.5, 0 maps to epsilon, 1 maps to 1-epsilon
    """
    clamped = max(0.0, min(float(score), 1.0))
    return round(epsilon + (clamped * (1.0 - 2.0 * epsilon)), 6)


CARBON_BUDGET_PER_DELIVERED = {
    TaskName.steady_state: 10.0,
    TaskName.port_strike: 12.0,
    TaskName.black_swan: 14.0,
}


def _nonlinear_late_penalty(late: int, total: int, max_penalty: float) -> float:
    """Apply exponential late penalties to reflect real-world cascade impact."""
    if total <= 0 or late <= 0:
        return 0.0
    late_ratio = min(max(late / total, 0.0), 1.0)
    # Smoothly maps [0,1] to [0,max_penalty] with stronger tail penalties.
    exp_ratio = (math.exp(3.0 * late_ratio) - 1.0) / (math.exp(3.0) - 1.0)
    return min(max_penalty, exp_ratio * max_penalty)


def _carbon_efficiency_score(task_name: TaskName, carbon_footprint: float, delivered: int) -> float:
    """Return [0,1] score favoring lower carbon usage per delivered order."""
    if delivered <= 0:
        return 0.0
    budget = CARBON_BUDGET_PER_DELIVERED.get(task_name, 12.0)
    carbon_per_delivery = max(float(carbon_footprint), 0.0) / delivered
    if carbon_per_delivery <= 0:
        return 1.0
    return max(0.0, min(1.0, budget / carbon_per_delivery))


def _critical_order_multiplier(orders: List[Order], critical_ids: set[str]) -> float:
    """Down-weight score if critical orders are late/cancelled/not delivered."""
    if not critical_ids:
        return 1.0
    status_by_id = {o.id: o.status for o in orders}
    multiplier = 1.0
    for order_id in critical_ids:
        status = status_by_id.get(order_id)
        if status is None:
            continue
        if status in {OrderStatus.late, OrderStatus.cancelled, OrderStatus.pending}:
            multiplier *= 0.55
        elif status != OrderStatus.delivered:
            multiplier *= 0.75
    return max(0.35, multiplier)


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
        carbon_footprint: float = 0.0,
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
        carbon_footprint: float = 0.0,
    ) -> float:
        """
        steady_state scoring (easy task):
        - 3 orders with zero disruptions
        - Expected: agent delivers all on time
        - Perfect: all delivered + no lates + early = 1.0
        - Reward-normalized: reward / 350
        """
        delivered = sum(1 for order in orders if order.status == OrderStatus.delivered)
        late = sum(1 for order in orders if order.status == OrderStatus.late)
        total = len(orders)

        if total == 0:
            return _constrain_score(0.0)

        # Reward-based normalization
        max_reward = MAX_REWARD_BY_TASK.get(task_name, 350.0)
        reward_score = max(0.0, min(float(final_reward) / max_reward, 1.0))

        # Order-based metrics as secondary validation
        delivered_ratio = min(delivered / total, 1.0)
        late_penalty = _nonlinear_late_penalty(late=late, total=total, max_penalty=0.35)
        efficiency_bonus = max(0.0, min(0.1, (max_steps - total_steps_taken) / max_steps * 0.1))
        carbon_score = _carbon_efficiency_score(task_name, carbon_footprint, delivered)

        # We keep reward slightly dominant here because the baseline task is meant to
        # reward stable execution first, while still acknowledging delivery quality.
        core = (0.7 * reward_score) + (0.3 * (delivered_ratio - late_penalty + efficiency_bonus))
        blended = (0.95 * core) + (0.05 * carbon_score)
        return _constrain_score(blended)


class PortStrikeGrader(TaskGrader):
    """Grader for port_strike task (route blockage, +1 order)."""

    def grade(
        self,
        task_name: TaskName,
        orders: List[Order],
        total_steps_taken: int,
        max_steps: int,
        final_reward: float,
        carbon_footprint: float = 0.0,
    ) -> float:
        """
        port_strike scoring (medium task):
        - 4 orders, R3 blocked at step 5
        - Expected: agent reroutes and adapts
        - Perfect: all 4 delivered despite blockage = 1.0
        - Reward-normalized: reward / 420
        """
        delivered = sum(1 for order in orders if order.status == OrderStatus.delivered)
        late = sum(1 for order in orders if order.status == OrderStatus.late)
        total = len(orders)

        if total == 0:
            return _constrain_score(0.0)

        # Reward-based normalization
        max_reward = MAX_REWARD_BY_TASK.get(task_name, 420.0)
        reward_score = max(0.0, min(float(final_reward) / max_reward, 1.0))

        # Order-based metrics
        delivered_ratio = min(delivered / total, 1.0)
        late_penalty = _nonlinear_late_penalty(late=late, total=total, max_penalty=0.45)
        efficiency_bonus = max(0.0, min(0.08, (max_steps - total_steps_taken) / max_steps * 0.08))
        carbon_score = _carbon_efficiency_score(task_name, carbon_footprint, delivered)

        # The medium task should still privilege reward, but the penalty structure
        # makes late reroutes more visible to human reviewers.
        core = (0.75 * reward_score) + (0.25 * (delivered_ratio - late_penalty + efficiency_bonus))
        blended = (0.95 * core) + (0.05 * carbon_score)
        return _constrain_score(blended)


class BlackSwanGrader(TaskGrader):
    """Grader for black_swan task (hardest: cascading disruptions)."""

    def grade(
        self,
        task_name: TaskName,
        orders: List[Order],
        total_steps_taken: int,
        max_steps: int,
        final_reward: float,
        carbon_footprint: float = 0.0,
    ) -> float:
        """
        black_swan scoring (hard task):
        - 5 orders, cascading disruptions (route block, demand spike, fuel surge)
        - Partial success expected and rewarded
        - Graceful degradation: 1 order delivered = 0.3, 5 orders = 1.0
        - Reward-normalized: reward / 500
        """
        delivered = sum(1 for order in orders if order.status == OrderStatus.delivered)
        late = sum(1 for order in orders if order.status == OrderStatus.late)
        total = len(orders)

        if total == 0:
            return _constrain_score(0.0)

        # Reward-based normalization (primary for hard task)
        max_reward = MAX_REWARD_BY_TASK.get(task_name, 500.0)
        reward_score = max(0.0, min(float(final_reward) / max_reward, 1.0))

        # Order-based graceful degradation scale
        # 5→1.0, 4→0.90, 3→0.75, 2→0.55, 1→0.30, 0→0.0
        graceful_scale = {5: 1.0, 4: 0.90, 3: 0.75, 2: 0.55, 1: 0.30, 0: 0.0}
        order_score = graceful_scale.get(delivered, 0.0)

        # Late penalty (harsh and nonlinear for black swan realism)
        late_penalty = _nonlinear_late_penalty(late=late, total=total, max_penalty=0.60)
        carbon_score = _carbon_efficiency_score(task_name, carbon_footprint, delivered)

        # Critical order O5 models high-impact fulfillment dependency.
        critical_multiplier = _critical_order_multiplier(orders, {"O5"})

        # Hard task: equal weight on reward vs graceful degradation, then apply a small
        # carbon penalty and critical-order multiplier to reflect ESG and dependency risk.
        core = (0.5 * reward_score) + (0.5 * (order_score - late_penalty))
        carbon_penalty = min(0.05, max(0.0, carbon_footprint) / max(1000.0, float(total) * 250.0) * 0.05)
        blended = (((0.95 * core) + (0.05 * carbon_score)) - carbon_penalty) * critical_multiplier
        return _constrain_score(blended)


def grade_task(
    task_name: TaskName,
    orders: List[Order],
    total_steps_taken: int,
    max_steps: int,
    final_reward: float,
    carbon_footprint: float = 0.0,
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

    return grader.grade(
        task_name,
        orders,
        total_steps_taken,
        max_steps,
        final_reward,
        carbon_footprint=carbon_footprint,
    )

