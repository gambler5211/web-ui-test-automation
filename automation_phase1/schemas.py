from __future__ import annotations
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field

Action = Literal[
    "open_url",
    "click",
    "type",
    "select",
    "wait",
    "get_text",
    "assert",
    "get_a11y_tree",
    "get_dom_distill",
    "exists",
    "count",
]

class Target(BaseModel):
    role: Optional[str] = None  # e.g., button, textbox, link
    name: Optional[str] = None  # accessible name
    label: Optional[str] = None
    placeholder: Optional[str] = None
    text: Optional[str] = None
    css: Optional[str] = None   # allowed but discouraged; runner may ignore

class Predicate(BaseModel):
    op: Literal["equals", "contains", "exists"]
    left: Optional[str] = None   # variable or literal
    right: Optional[str] = None  # variable or literal

class Step(BaseModel):
    action: Action
    target: Optional[Target] = None
    url: Optional[str] = None
    text: Optional[str] = None
    press_enter: Optional[bool] = None
    press_keys: Optional[List[str]] = None
    select_value: Optional[str] = None
    wait_ms: Optional[int] = None
    save_as: Optional[str] = None
    predicate: Optional[Predicate] = None

class ScenarioMeta(BaseModel):
    name: str
    base_url: Optional[str] = None
    device: Optional[str] = None

class Scenario(BaseModel):
    meta: ScenarioMeta
    steps: List[Step]

class CompileProvenance(BaseModel):
    line: str
    source: Literal["regex", "llm", "override"]
    step: Step

class CompileResult(BaseModel):
    scenario: Scenario
    provenance: List[CompileProvenance]


