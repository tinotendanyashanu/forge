import {
  Activity,
  AppWindow,
  Archive,
  Bell,
  Cog,
  CreditCard,
  Database,
  Globe,
  KeyRound,
  Layers,
  ListOrdered,
  MemoryStick,
  Plug,
  Search,
  Server,
  Smartphone,
  Split,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

import type { GraphDocument, Protocol } from "@/lib/types";

/** Mirrors api/app/design/graph.py COMPONENT_TYPES (the API validates). */
export const COMPONENTS: Record<string, { label: string; category: string; icon: LucideIcon }> = {
  client: { label: "Client application", category: "Clients", icon: Smartphone },
  web_frontend: { label: "Web frontend", category: "Clients", icon: AppWindow },
  api_gateway: { label: "API gateway", category: "Edge", icon: Waypoints },
  load_balancer: { label: "Load balancer", category: "Edge", icon: Split },
  cdn: { label: "CDN", category: "Edge", icon: Globe },
  service: { label: "Backend service", category: "Compute", icon: Server },
  auth_service: { label: "Authentication service", category: "Compute", icon: KeyRound },
  worker: { label: "Background worker", category: "Compute", icon: Cog },
  postgres: { label: "PostgreSQL database", category: "Data", icon: Database },
  nosql: { label: "NoSQL database", category: "Data", icon: Layers },
  redis: { label: "Redis cache", category: "Data", icon: MemoryStick },
  object_storage: { label: "Object storage", category: "Data", icon: Archive },
  search: { label: "Search service", category: "Data", icon: Search },
  queue: { label: "Message queue", category: "Messaging", icon: ListOrdered },
  notification: { label: "Notification service", category: "Messaging", icon: Bell },
  external_api: { label: "External API", category: "External", icon: Plug },
  payment_provider: { label: "Payment provider", category: "External", icon: CreditCard },
  monitoring: { label: "Monitoring", category: "Operations", icon: Activity },
};

export const CATEGORIES = ["Clients", "Edge", "Compute", "Data", "Messaging", "External", "Operations"];

export const PROTOCOL_LABEL: Record<Protocol, string> = {
  http: "HTTP",
  websocket: "WebSocket",
  rpc: "RPC",
  event: "Events",
  db_query: "DB queries",
  cache: "Cache",
  replication: "Replication",
};
export const PROTOCOLS = Object.keys(PROTOCOL_LABEL) as Protocol[];

export const LIMITS = { nodes: 80, edges: 160, name: 80, description: 600, properties: 12 };

export const DRAG_MIME = "application/x-forge-component";

export function newId(prefix: string) {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${prefix.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 40)}-${rand}`;
}

export const EMPTY_GRAPH: GraphDocument = { version: 1, nodes: [], edges: [] };

export const LEVEL_LABEL = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
  senior: "Senior",
} as const;

export const MODE_INFO = {
  guided: { label: "Guided design", description: "Step-by-step questions with scaffolding. Good for a first attempt." },
  interview: { label: "Interview simulation", description: "A demanding interviewer probes until your reasoning is explicit." },
  senior_review: { label: "Senior architecture review", description: "Challenges trade-offs, cost, operability and long-term evolution." },
  failure_review: { label: "Production failure review", description: "Focuses on failure modes, blast radius, detection and recovery." },
} as const;

export const CRITERION_LABEL: Record<string, string> = {
  requirement_coverage: "Requirement coverage",
  correctness: "Correctness",
  scalability: "Scalability",
  reliability: "Reliability",
  data_consistency: "Data consistency",
  security: "Security",
  performance: "Performance",
  maintainability: "Maintainability",
  operational_complexity: "Operational complexity",
  cost_awareness: "Cost awareness",
  reasoning_quality: "Reasoning quality",
  tradeoffs: "Trade-offs",
};

export const COMPETENCY_LABEL: Record<string, string> = {
  api_architecture: "API architecture",
  data_modeling: "Data modelling",
  scalability: "Scalability",
  distributed_systems: "Distributed systems",
  consistency: "Consistency",
  security: "Security",
  failure_recovery: "Failure recovery",
  observability: "Observability",
  cost_optimization: "Cost optimisation",
  technical_communication: "Technical communication",
};
