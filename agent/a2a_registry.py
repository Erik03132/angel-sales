"""Реестр агентов для диспетчера A2A-шины.

Новый агент подключается за минуты: register_agent(...) или декоратор @agent.
Это реализация обещания роадмапа «новый агент подключается за часы, не дни».
"""
from dataclasses import dataclass, field
from typing import Callable, Optional


REGISTRY: dict = {}


@dataclass
class AgentSpec:
    id: str
    name: str
    project: str
    handler: Optional[Callable] = None
    capabilities: list = field(default_factory=list)
    description: str = ""


def register_agent(id: str, name: str, project: str, handler: Optional[Callable] = None,
                   capabilities: Optional[list] = None, description: str = "") -> AgentSpec:
    REGISTRY[id] = AgentSpec(id, name, project, handler, capabilities or [], description)
    return REGISTRY[id]


def agent(id: str, name: str, project: str, capabilities: Optional[list] = None,
          description: str = ""):
    """Декоратор: @agent("scanner", "Bitrix Scanner", "ai-eggs")"""
    def deco(fn: Callable):
        register_agent(id, name, project, handler=fn,
                       capabilities=capabilities, description=description)
        return fn
    return deco


def get_agent(aid: str) -> Optional[AgentSpec]:
    return REGISTRY.get(aid)


def list_agents() -> list:
    return [{
        "id": a.id, "name": a.name, "project": a.project,
        "capabilities": a.capabilities, "description": a.description,
        "has_handler": a.handler is not None,
    } for a in REGISTRY.values()]
