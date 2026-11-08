"""Advisory second-model review of the P5 lessons; never marks content verified.

Run from api/: venv/bin/python tools/review_p5.py --output /private/tmp/p5-review.json
Uses the existing configured server-side model provider. No learner data is sent.
"""

from __future__ import annotations

import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.seed.lessons import LESSON_DIR, parse_lesson


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--slugs", nargs="*")
    args = parser.parse_args()
    settings = Settings()
    assert settings.llm_api_key and settings.llm_base_url
    lessons = [(path, parse_lesson(path)) for path in sorted(LESSON_DIR.glob("*.md")) if int(path.name[:2]) >= 16]
    if args.slugs:
        lessons = [(p, x) for p, x in lessons if x.slug in args.slugs]

    def review(item):
        path, lesson = item
        prompt = (
            "Independently review this engineering lesson. You did not author it. Do not assume its statements or outputs are correct. "
            "Check technical accuracy and runtime/compiler outputs, version scope, misleading security claims, beginner-to-advanced progression, "
            "exercise usefulness, reasoning feedback and prerequisites. Distinguish genuine errors from optional elaboration. "
            "Give concrete evidence and a suggested correction for each issue. Do not claim you ran tools or visited URLs. "
            "Return JSON: {\"ready\":true|false,\"findings\":[{\"severity\":\"error|important|suggestion\",\"claim\":\"...\",\"reason\":\"...\",\"fix\":\"...\"}],"
            "\"pedagogy\":\"...\",\"reasoning_answers_checked\":true|false}.\n\n" + path.read_text()
        )
        body = {"model": settings.llm_model, "messages": [
            {"role": "system", "content": "Return one strict JSON object only. No Markdown, comments, or trailing commas."},
            {"role": "user", "content": prompt}],
                "temperature": 0, "max_tokens": 6000, "response_format": {"type": "json_object"}}
        request = urllib.request.Request(settings.llm_base_url.rstrip("/") + "/chat/completions",
                                         data=json.dumps(body).encode(), headers={
                                             "Authorization": "Bearer " + settings.llm_api_key.get_secret_value(),
                                             "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = json.load(response)
        content = raw["choices"][0]["message"]["content"]
        result = {"slug": lesson.slug, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "usage": raw.get("usage")}
        try:
            candidate = re.search(r"\{.*\}", content, re.S)
            result["review"] = json.loads(candidate.group(0) if candidate else content)
        except json.JSONDecodeError as exc:
            result.update(error=str(exc), raw=content)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(review, lessons))
    report = {"model": settings.llm_model, "reviewed_at": datetime.now(timezone.utc).isoformat(), "results": results,
              "human_verified": False}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"model": settings.llm_model, "lessons": len(results),
                      "findings": sum(len(x.get("review", {}).get("findings", [])) for x in results),
                      "errors": sum("error" in x for x in results)}))
    if any("error" in x for x in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
