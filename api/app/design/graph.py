"""Architecture graph documents: the only shape the canvas may save.

Everything here is untrusted learner input. Validation enforces identifiers,
supported component types, edge endpoints, size limits and plain-text labels.
A valid diagram is not evidence that an architecture is correct.
"""

import json
import re
import unicodedata
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

MAX_NODES = 80
MAX_EDGES = 160
MAX_PROPERTIES = 12
MAX_GRAPH_BYTES = 200_000

COMPONENT_TYPES: dict[str, dict[str, str]] = {
    "client": {"label": "Client application", "category": "Clients"},
    "web_frontend": {"label": "Web frontend", "category": "Clients"},
    "api_gateway": {"label": "API gateway", "category": "Edge"},
    "load_balancer": {"label": "Load balancer", "category": "Edge"},
    "cdn": {"label": "CDN", "category": "Edge"},
    "service": {"label": "Backend service", "category": "Compute"},
    "auth_service": {"label": "Authentication service", "category": "Compute"},
    "worker": {"label": "Background worker", "category": "Compute"},
    "postgres": {"label": "PostgreSQL database", "category": "Data"},
    "nosql": {"label": "NoSQL database", "category": "Data"},
    "redis": {"label": "Redis cache", "category": "Data"},
    "object_storage": {"label": "Object storage", "category": "Data"},
    "search": {"label": "Search service", "category": "Data"},
    "queue": {"label": "Message queue", "category": "Messaging"},
    "notification": {"label": "Notification service", "category": "Messaging"},
    "external_api": {"label": "External API", "category": "External"},
    "payment_provider": {"label": "Payment provider", "category": "External"},
    "monitoring": {"label": "Monitoring", "category": "Operations"},
}
PROTOCOLS = ("http", "websocket", "rpc", "event", "db_query", "cache", "replication")

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩]")


def clean_text(value: str) -> str:
    """Plain text only: NFC-normalised, no control or bidi-override characters."""
    return _CONTROL.sub("", unicodedata.normalize("NFC", value)).strip()


Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Short = Annotated[str, AfterValidator(clean_text), Field(max_length=80)]
Long = Annotated[str, AfterValidator(clean_text), Field(max_length=600)]
PropValue = str | int | float | bool


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Position(_Strict):
    x: float = Field(ge=-100_000, le=100_000)
    y: float = Field(ge=-100_000, le=100_000)


class GraphNode(_Strict):
    id: Id
    type: str
    name: Short = Field(min_length=1)
    description: Long = ""
    properties: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")], PropValue] = Field(default_factory=dict)
    capacity: Long | None = None  # learner's stated capacity assumption
    reliability: Long | None = None  # learner's stated reliability assumption
    position: Position

    @model_validator(mode="after")
    def _known_type(self) -> Self:
        if self.type not in COMPONENT_TYPES:
            raise ValueError(f"Unsupported component type '{self.type}'")
        if len(self.properties) > MAX_PROPERTIES:
            raise ValueError(f"At most {MAX_PROPERTIES} properties per component")
        for v in self.properties.values():
            if isinstance(v, str) and len(v) > 200:
                raise ValueError("Property values must be 200 characters or fewer")
        self.properties = {k: clean_text(v) if isinstance(v, str) else v for k, v in self.properties.items()}
        return self


class GraphEdge(_Strict):
    id: Id
    source: Id
    target: Id
    protocol: Literal["http", "websocket", "rpc", "event", "db_query", "cache", "replication"]
    label: Short = ""


class GraphDocument(_Strict):
    version: Literal[1] = 1
    nodes: list[GraphNode] = Field(default_factory=list, max_length=MAX_NODES)
    edges: list[GraphEdge] = Field(default_factory=list, max_length=MAX_EDGES)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("Node ids must be unique")
        edge_ids = [e.id for e in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("Edge ids must be unique")
        known = set(ids)
        for e in self.edges:
            if e.source not in known or e.target not in known:
                raise ValueError(f"Edge '{e.id}' references a missing node")
            if e.source == e.target:
                raise ValueError(f"Edge '{e.id}' connects a node to itself")
        if len(json.dumps(self.model_dump())) > MAX_GRAPH_BYTES:
            raise ValueError("Diagram is too large")
        return self


def diff(a: GraphDocument, b: GraphDocument) -> dict:
    """Structural difference from version a to version b."""
    an, bn = {n.id: n for n in a.nodes}, {n.id: n for n in b.nodes}
    ae, be = {e.id: e for e in a.edges}, {e.id: e for e in b.edges}

    def node_changes(x: GraphNode, y: GraphNode) -> list[str]:
        fields = ["type", "name", "description", "properties", "capacity", "reliability"]
        return [f for f in fields if getattr(x, f) != getattr(y, f)]

    return {
        "nodes_added": [{"id": i, "name": bn[i].name, "type": bn[i].type} for i in bn.keys() - an.keys()],
        "nodes_removed": [{"id": i, "name": an[i].name, "type": an[i].type} for i in an.keys() - bn.keys()],
        "nodes_changed": [
            {"id": i, "name": bn[i].name, "fields": ch}
            for i in an.keys() & bn.keys() if (ch := node_changes(an[i], bn[i]))
        ],
        "edges_added": [_edge(be[i], bn) for i in be.keys() - ae.keys()],
        "edges_removed": [_edge(ae[i], an) for i in ae.keys() - be.keys()],
        "edges_changed": [
            _edge(be[i], bn) for i in ae.keys() & be.keys()
            if (ae[i].protocol, ae[i].label, ae[i].source, ae[i].target) != (be[i].protocol, be[i].label, be[i].source, be[i].target)
        ],
    }


def _edge(e: GraphEdge, nodes: dict[str, GraphNode]) -> dict:
    name = lambda i: nodes[i].name if i in nodes else i  # noqa: E731
    return {"id": e.id, "from": name(e.source), "to": name(e.target), "protocol": e.protocol, "label": e.label}


def describe_for_model(g: GraphDocument) -> str:
    """Compact, delimited rendering for prompts. Labels stay data, not instructions."""
    lines = ["Components:"]
    for n in g.nodes:
        extra = []
        if n.properties:
            extra.append("props=" + json.dumps(n.properties, ensure_ascii=False))
        if n.capacity:
            extra.append(f"capacity_assumption={json.dumps(n.capacity)}")
        if n.reliability:
            extra.append(f"reliability_assumption={json.dumps(n.reliability)}")
        if n.description:
            extra.append(f"description={json.dumps(n.description)}")
        lines.append(f"- node:{n.id} [{n.type}] name={json.dumps(n.name)} " + " ".join(extra))
    lines.append("Connections:")
    for e in g.edges:
        lines.append(f"- edge:{e.id} node:{e.source} -> node:{e.target} via {e.protocol}"
                     + (f" label={json.dumps(e.label)}" if e.label else ""))
    if not g.nodes:
        lines.append("(empty diagram)")
    return "\n".join(lines)
