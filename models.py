from __future__ import annotations

from enum import Enum
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict


class Warehouse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    stock: int = Field(ge=0)
    capacity: int = Field(gt=0)


class RouteStatus(str, Enum):
    active = "active"
    blocked = "blocked"
    congested = "congested"


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    destination: str
    lead_time: float = Field(gt=0)
    cost: float = Field(ge=0)
    status: RouteStatus = RouteStatus.active
    carbon_cost: float = Field(default=0.0, ge=0)


class OrderStatus(str, Enum):
    pending = "pending"
    in_transit = "in_transit"
    delivered = "delivered"
    late = "late"
    cancelled = "cancelled"


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    origin: str
    destination: str
    quantity: int = Field(gt=0)
    due_date: int = Field(ge=0)
    route_id: Optional[str] = None
    status: OrderStatus = OrderStatus.pending
    progress: float = Field(default=0.0, ge=0.0)


class ChaosEventType(str, Enum):
    route_block = "route_block"
    demand_spike = "demand_spike"
    fuel_surge = "fuel_surge"
    supplier_delay = "supplier_delay"
    customs_hold = "customs_hold"
    warehouse_outage = "warehouse_outage"


class ChaosEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ChaosEventType
    target_id: Optional[str] = None
    magnitude: float = Field(default=1.0, gt=0)
    description: str


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_name: "TaskName"
    task_description: str
    warehouses: List[Warehouse]
    routes: List[Route]
    orders: List[Order]
    time_step: int = Field(ge=0)
    active_events: List[ChaosEvent] = Field(default_factory=list)
    carbon_footprint: float = Field(default=0.0, ge=0)


class ActionType(str, Enum):
    reroute = "reroute"
    expedite = "expedite"
    adjust_stock = "adjust_stock"
    wait = "wait"


class WaitAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ActionType.wait]


class RerouteAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ActionType.reroute]
    order_id: str
    route_id: str


class ExpediteAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ActionType.expedite]
    order_id: str


class AdjustStockAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ActionType.adjust_stock]
    warehouse_id: str
    amount: int = Field(gt=0)


Action = Annotated[
    Union[WaitAction, RerouteAction, ExpediteAction, AdjustStockAction],
    Field(discriminator="type"),
]


class TaskName(str, Enum):
    steady_state = "steady_state"
    port_strike = "port_strike"
    black_swan = "black_swan"


class TaskPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TaskName
    description: str
    max_steps: int = Field(gt=0)
    initial_warehouses: List[Warehouse]
    initial_routes: List[Route]
    initial_orders: List[Order]
    route_block_step: Optional[int] = Field(default=None, ge=0)
    route_block_route_id: Optional[str] = None
    demand_spike_step: Optional[int] = Field(default=None, ge=0)
    demand_spike_order_id: Optional[str] = None
    demand_spike_multiplier: float = Field(default=3.0, gt=1)
    fuel_surge_step: Optional[int] = Field(default=None, ge=0)
    fuel_surge_multiplier: float = Field(default=1.5, gt=1)
    route_block_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    demand_spike_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    fuel_surge_probability: float = Field(default=0.0, ge=0.0, le=1.0)


class Reward(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float
    delivered: int
    operating_cost: float
    late_penalties: float
    storage_fees: float
    carbon_penalty: float
    disruption_penalty: float = 0.0


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation: Observation
    reward: Reward
    done: bool
    info: dict = Field(default_factory=dict)
