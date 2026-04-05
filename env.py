from __future__ import annotations

import os
import random
from copy import deepcopy
from typing import Dict, List, Optional

from pydantic import TypeAdapter

from models import (
    Action,
    ActionType,
    ChaosEvent,
    ChaosEventType,
    Observation,
    Order,
    OrderStatus,
    Reward,
    Route,
    RouteStatus,
    TaskName,
    TaskPreset,
    StepResult,
    Warehouse,
)


ACTION_ADAPTER = TypeAdapter(Action)


class SupplyChainEnv:
    def __init__(self, seed: Optional[int] = None) -> None:
        # Deterministic seeding for reproducibility
        if seed is None:
            seed = 42  # Default seed for consistency
        self.random = random.Random(seed)
        self.seed = seed
        self.max_steps = 20
        self.state: Optional[Observation] = None
        self.task_name: TaskName = TaskName.steady_state
        self.task_preset: TaskPreset = self._build_task_presets()[TaskName.steady_state]
        self.base_demand = 1.0
        self.fuel_multiplier = 1.0
        self.last_info: Dict[str, object] = {}
        self.episode_reward = 0.0  # Track cumulative reward for scoring
        self.reward_min = float(os.getenv("SUPPLY_CHAIN_REWARD_MIN", "-50"))
        self.reward_max = float(os.getenv("SUPPLY_CHAIN_REWARD_MAX", "200"))
        self.episode_reward_normalized = 0.0

    def reset(self, task: TaskName | str = TaskName.steady_state) -> Observation:
        preset = self._get_task_preset(task)
        self.task_name = preset.name
        self.task_preset = preset
        self.max_steps = preset.max_steps
        self.episode_reward = 0.0  # Reset cumulative reward
        self.episode_reward_normalized = 0.0

        warehouses = deepcopy(preset.initial_warehouses)
        routes = deepcopy(preset.initial_routes)
        orders = deepcopy(preset.initial_orders)

        self.state = Observation(
            task_name=preset.name,
            task_description=preset.description,
            warehouses=warehouses,
            routes=routes,
            orders=orders,
            time_step=0,
            active_events=[],
            carbon_footprint=0.0,
        )
        self.base_demand = 1.0
        self.fuel_multiplier = 1.0
        self.last_info = {"task": preset.name.value}
        return deepcopy(self.state)

    def _build_task_presets(self) -> Dict[TaskName, TaskPreset]:
        base_warehouses = [
            Warehouse(id="W1", stock=140, capacity=200),
            Warehouse(id="W2", stock=90, capacity=160),
            Warehouse(id="W3", stock=60, capacity=120),
        ]
        base_routes = [
            Route(id="R1", source="W1", destination="W2", lead_time=2.0, cost=12.0, carbon_cost=6.0),
            Route(id="R2", source="W2", destination="W3", lead_time=3.0, cost=14.0, carbon_cost=5.0),
            Route(id="R3", source="W1", destination="W3", lead_time=4.0, cost=20.0, carbon_cost=9.0),
        ]
        base_orders = [
            Order(id="O1", origin="W1", destination="W3", quantity=25, due_date=6),
            Order(id="O2", origin="W2", destination="W3", quantity=18, due_date=5),
            Order(id="O3", origin="W1", destination="W2", quantity=30, due_date=7),
        ]
        port_strike_orders = deepcopy(base_orders) + [
            Order(id="O4", origin="W2", destination="W3", quantity=24, due_date=8),
        ]
        black_swan_orders = deepcopy(base_orders) + [
            Order(id="O4", origin="W2", destination="W3", quantity=28, due_date=6),
            Order(id="O5", origin="W1", destination="W3", quantity=35, due_date=7),
        ]

        return {
            TaskName.steady_state: TaskPreset(
                name=TaskName.steady_state,
                description="Baseline demand with no forced disruptions.",
                max_steps=20,
                initial_warehouses=base_warehouses,
                initial_routes=base_routes,
                initial_orders=base_orders,
            ),
            TaskName.port_strike: TaskPreset(
                name=TaskName.port_strike,
                description="Primary route blocked on step 5; one extra order must be rerouted under disruption.",
                max_steps=20,
                initial_warehouses=deepcopy(base_warehouses),
                initial_routes=deepcopy(base_routes),
                initial_orders=port_strike_orders,
                route_block_step=5,
                route_block_route_id="R3",
            ),
            TaskName.black_swan: TaskPreset(
                name=TaskName.black_swan,
                description="Route closure, demand spikes, and fuel surge must be absorbed across a larger order book.",
                max_steps=20,
                initial_warehouses=[
                    Warehouse(id="W1", stock=120, capacity=200),
                    Warehouse(id="W2", stock=80, capacity=160),
                    Warehouse(id="W3", stock=55, capacity=120),
                ],
                initial_routes=deepcopy(base_routes),
                initial_orders=black_swan_orders,
                route_block_step=5,
                route_block_route_id="R3",
                demand_spike_step=5,
                demand_spike_order_id="O1",
                demand_spike_multiplier=2.0,
                fuel_surge_step=5,
                fuel_surge_multiplier=2.0,
                route_block_probability=0.2,
                demand_spike_probability=0.15,
                fuel_surge_probability=0.15,
            ),
        }

    def _get_task_preset(self, task: TaskName | str) -> TaskPreset:
        task_name = task if isinstance(task, TaskName) else TaskName(task)
        return self._build_task_presets()[task_name]

    def step(self, action: Action | dict) -> StepResult:
        if self.state is None:
            raise RuntimeError("Environment must be reset before stepping.")

        if isinstance(action, dict):
            action = ACTION_ADAPTER.validate_python(action)

        self.last_info = {"applied_action": action.model_dump()}
        self._apply_action(action)
        self._apply_progress()
        self._apply_random_events()
        self._update_late_orders()

        self.state.time_step += 1
        reward = self._calculate_reward()
        self.episode_reward += reward.value  # Track cumulative reward
        # Keep cumulative normalized reward aligned with logged 2-decimal step rewards.
        self.episode_reward_normalized += round(self._normalize_reward(reward.value), 2)
        done = self._is_done()
        if not done and self.state.time_step >= self.max_steps:
            done = True
            self.last_info["termination"] = "max_steps_safety"

        result = StepResult(
            observation=deepcopy(self.state),
            reward=reward,
            done=done,
            info=deepcopy(self.last_info),
        )
        return result

    def _normalize_reward(self, raw_reward: float) -> float:
        """Normalize a raw step reward into [0.0, 1.0]."""
        if self.reward_max <= self.reward_min:
            return 0.0
        normalized = (raw_reward - self.reward_min) / (self.reward_max - self.reward_min)
        return max(0.0, min(1.0, normalized))

    def _apply_action(self, action: Action) -> None:
        if action.type == ActionType.wait:
            return

        if action.type == ActionType.adjust_stock:
            if action.warehouse_id is None or action.amount is None:
                raise ValueError("adjust_stock requires warehouse_id and amount")
            warehouse = self._get_warehouse(action.warehouse_id)
            warehouse.stock = min(warehouse.capacity, warehouse.stock + max(action.amount, 0))
            self.last_info["adjusted_stock"] = warehouse.id
            return

        if action.order_id is None:
            raise ValueError("reroute and expedite require order_id")
        order = self._get_order(action.order_id)

        if action.type == ActionType.reroute:
            if action.route_id is None:
                raise ValueError("reroute requires route_id")
            route = self._get_route(action.route_id)
            if route.status == RouteStatus.blocked:
                raise ValueError("cannot reroute through a blocked route")
            order.route_id = route.id
            order.status = OrderStatus.in_transit
            order.progress = 0.0
            self.state.carbon_footprint += route.carbon_cost
            self._consume_stock(order.origin, order.quantity)
            self.last_info["rerouted_order"] = order.id
            return

        if action.type == ActionType.expedite:
            if order.route_id is None:
                route = self._fallback_route(order)
            else:
                route = self._get_route(order.route_id)
            if route.status == RouteStatus.blocked:
                raise ValueError("cannot expedite a blocked route")
            route.lead_time = max(1.0, route.lead_time * 0.5)
            route.cost *= 3.0
            self.state.carbon_footprint += route.carbon_cost * 1.5
            order.status = OrderStatus.in_transit
            self.last_info["expedited_order"] = order.id
            return

        raise ValueError(f"Unsupported action type: {action.type}")

    def _apply_progress(self) -> None:
        assert self.state is not None
        for order in self.state.orders:
            if order.status != OrderStatus.in_transit or order.route_id is None:
                continue
            route = self._get_route(order.route_id)
            if route.status == RouteStatus.blocked:
                continue
            order.progress += 1.0 / max(route.lead_time, 1.0)
            if order.progress >= 1.0:
                order.progress = 1.0
                order.status = OrderStatus.delivered

    def _apply_random_events(self) -> None:
        assert self.state is not None
        self.state.active_events = []

        next_step = self.state.time_step + 1

        if self.task_preset.route_block_step == next_step and self.task_preset.route_block_route_id:
            route = self._get_route(self.task_preset.route_block_route_id)
            route.status = RouteStatus.blocked
            self.state.active_events.append(
                ChaosEvent(
                    type=ChaosEventType.route_block,
                    target_id=route.id,
                    magnitude=1.0,
                    description=f"Preset route block on {route.id}",
                )
            )

        if self.task_preset.demand_spike_step == next_step and self.task_preset.demand_spike_order_id:
            order = self._get_order(self.task_preset.demand_spike_order_id)
            order.quantity = int(order.quantity * self.task_preset.demand_spike_multiplier)
            self.state.active_events.append(
                ChaosEvent(
                    type=ChaosEventType.demand_spike,
                    target_id=order.id,
                    magnitude=self.task_preset.demand_spike_multiplier,
                    description=f"Preset demand spike on {order.id}",
                )
            )

        if self.task_preset.fuel_surge_step == next_step:
            self.fuel_multiplier = self.task_preset.fuel_surge_multiplier
            self.state.active_events.append(
                ChaosEvent(
                    type=ChaosEventType.fuel_surge,
                    magnitude=self.fuel_multiplier,
                    description="Preset fuel price surge",
                )
            )

        if self.random.random() < self.task_preset.route_block_probability and self.state.routes:
            route = self.random.choice(self.state.routes)
            route.status = RouteStatus.blocked
            self.state.active_events.append(
                ChaosEvent(
                    type=ChaosEventType.route_block,
                    target_id=route.id,
                    magnitude=1.0,
                    description=f"Route {route.id} blocked",
                )
            )

        if self.random.random() < self.task_preset.demand_spike_probability and self.state.orders:
            order = self.random.choice(self.state.orders)
            order.quantity = int(order.quantity * 3)
            self.state.active_events.append(
                ChaosEvent(
                    type=ChaosEventType.demand_spike,
                    target_id=order.id,
                    magnitude=3.0,
                    description=f"Demand spike on {order.id}",
                )
            )

        if self.random.random() < self.task_preset.fuel_surge_probability:
            self.fuel_multiplier = 1.0 + self.random.uniform(0.25, 1.0)
            self.state.active_events.append(
                ChaosEvent(
                    type=ChaosEventType.fuel_surge,
                    magnitude=self.fuel_multiplier,
                    description="Fuel price surge",
                )
            )

    def _update_late_orders(self) -> None:
        assert self.state is not None
        for order in self.state.orders:
            if order.status in {OrderStatus.delivered, OrderStatus.cancelled}:
                continue
            if self.state.time_step > order.due_date and order.status != OrderStatus.delivered:
                order.status = OrderStatus.late

    def _calculate_reward(self) -> Reward:
        assert self.state is not None
        delivered = sum(1 for order in self.state.orders if order.status == OrderStatus.delivered)
        total_orders = len(self.state.orders)
        operating_cost = 0.0
        late_penalties = 0.0
        storage_fees = 0.0
        carbon_penalty = self.state.carbon_footprint * 0.10

        for route in self.state.routes:
            if route.status != RouteStatus.blocked:
                operating_cost += route.cost * self.fuel_multiplier

        for order in self.state.orders:
            if order.status == OrderStatus.late:
                late_penalties += order.quantity * 8.0
            if order.status != OrderStatus.delivered:
                late_penalties += 1.0

        for warehouse in self.state.warehouses:
            unused = max(warehouse.stock, 0)
            storage_fees += unused * 0.03

        value = (delivered * 50.0) - (operating_cost * 0.2) - late_penalties - storage_fees - carbon_penalty

        if delivered == total_orders and total_orders > 0:
            latest_due = max(order.due_date for order in self.state.orders)
            if self.state.time_step <= latest_due:
                value += 50.0

        if total_orders > 0:
            delivered_ratio = delivered / total_orders
            if delivered_ratio >= 0.8 and delivered < total_orders:
                value += 50.0

        return Reward(
            value=value,
            delivered=delivered,
            operating_cost=operating_cost,
            late_penalties=late_penalties,
            storage_fees=storage_fees,
            carbon_penalty=carbon_penalty,
        )

    def _is_done(self) -> bool:
        assert self.state is not None
        all_delivered = all(order.status == OrderStatus.delivered for order in self.state.orders)
        if self.task_name == TaskName.black_swan:
            inventory_depleted = any(warehouse.stock <= 0 for warehouse in self.state.warehouses)
            if inventory_depleted:
                self.last_info["crash"] = "inventory_depleted"
                return True
        exhausted = self.state.time_step >= self.max_steps
        return all_delivered or exhausted

    def _get_warehouse(self, warehouse_id: str) -> Warehouse:
        assert self.state is not None
        for warehouse in self.state.warehouses:
            if warehouse.id == warehouse_id:
                return warehouse
        raise KeyError(f"Unknown warehouse: {warehouse_id}")

    def _get_route(self, route_id: str) -> Route:
        assert self.state is not None
        for route in self.state.routes:
            if route.id == route_id:
                return route
        raise KeyError(f"Unknown route: {route_id}")

    def _get_order(self, order_id: str) -> Order:
        assert self.state is not None
        for order in self.state.orders:
            if order.id == order_id:
                return order
        raise KeyError(f"Unknown order: {order_id}")

    def _fallback_route(self, order: Order) -> Route:
        assert self.state is not None
        for route in self.state.routes:
            if route.source == order.origin and route.destination == order.destination:
                return route
        for route in self.state.routes:
            if route.source == order.origin:
                return route
        return self.state.routes[0]

    def _consume_stock(self, warehouse_id: str, amount: int) -> None:
        warehouse = self._get_warehouse(warehouse_id)
        warehouse.stock = max(0, warehouse.stock - amount)
