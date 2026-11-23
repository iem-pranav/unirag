# * Picks the router named in settings (router.type) and routes one question.
from unirag.config.settings import get_settings
from unirag.router.base import RouteDecision
from unirag.router.llm_router import route_llm
from unirag.router.semantic import route_semantic

ROUTERS = {"llm": route_llm, "semantic": route_semantic}


def route(question: str, role: str) -> RouteDecision:
    return ROUTERS[get_settings().router_type](question, role)
