import { ApiError, ApiUnreachableError, getLearnerId } from "@/lib/api";

const API_BASE_URL = (process.env.FORGE_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

/** Markdown export of a postmortem, proxied with the learner cookie (the API key never reaches the browser). */
export async function GET(_req: Request, ctx: RouteContext<"/ops/sessions/[id]/postmortem.md">) {
  const { id } = await ctx.params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return new Response("Not found", { status: 404 });
  const learnerId = await getLearnerId();
  if (!learnerId) return new Response("Not found", { status: 404 });
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/ops/sessions/${id}/postmortem/export`, {
      headers: { "X-Learner-Id": learnerId },
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return new Response("Not found", { status: res.status === 409 ? 409 : 404 });
    return new Response(await res.text(), {
      headers: {
        "Content-Type": "text/markdown; charset=utf-8",
        "Content-Disposition": res.headers.get("Content-Disposition") ?? 'attachment; filename="postmortem.md"',
      },
    });
  } catch (error) {
    if (error instanceof ApiError || error instanceof ApiUnreachableError) return new Response("Unavailable", { status: 502 });
    return new Response("Unavailable", { status: 502 });
  }
}
