"""Proves the challenge bank against the real sandbox.

For every challenge and language: the reference solution must pass every test,
and the starter code must fail at least one hidden test.

    python -m app.coding.verify_bank      (needs the docker backend verified)
"""

import asyncio
import sys
from dataclasses import dataclass

from app.coding.bank_loader import BankChallenge, load_bank
from app.coding.grading import CaseSpec, grade
from app.coding.sandbox import DockerSandbox, ExecRequest
from app.core.config import Settings
from app.db.enums import TestOutcome, TestVisibility


@dataclass
class BankCheck:
    slug: str
    language: str
    reference_ok: bool
    reference_failures: list[str]
    starter_fails_hidden: bool
    duration_ms: int


def cases_for(c: BankChallenge) -> list[CaseSpec]:
    return [
        CaseSpec(i, i, t.name, t.visibility, t.call or c.entrypoint, t.resolved_args(), t.outcome())
        for i, t in enumerate(c.tests)
    ]


async def check(sandbox: DockerSandbox, c: BankChallenge, language: str) -> BankCheck:
    cases = cases_for(c)
    driver = c.driver.get(language).code if language in c.driver else None

    async def run(code: str):
        res = await sandbox.run(ExecRequest(language, code, driver, cases, c.time_limit_ms, c.memory_limit_mb))
        return res, grade(cases, res.stdout, killed_for_time=res.killed_for_time)

    ref_exec, ref = await run(c.languages[language].reference)
    _, starter = await run(c.languages[language].starter)
    failures = [f"{cases[r.position].name}: {r.outcome.value} {r.message or ''}".strip()
                for r in ref if r.outcome is not TestOutcome.PASSED]
    hidden_fail = any(
        r.outcome is not TestOutcome.PASSED and cases[r.position].visibility is TestVisibility.HIDDEN for r in starter
    )
    return BankCheck(c.slug, language, not failures, failures, hidden_fail, ref_exec.duration_ms)


async def verify_all(settings: Settings) -> list[BankCheck]:
    sandbox = DockerSandbox(settings)
    report = await sandbox.verify()
    if not report.verified:
        raise SystemExit(f"Sandbox not verified: {report.problems}")
    results = []
    for c in load_bank():
        for language in c.languages:
            results.append(await check(sandbox, c, language))
    return results


def main() -> None:
    settings = Settings(sandbox_backend="docker", sandbox_allow_container_isolation=True)
    results = asyncio.run(verify_all(settings))
    bad = 0
    for r in results:
        ok = r.reference_ok and r.starter_fails_hidden
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {r.slug:<26} {r.language:<10} ref={'pass' if r.reference_ok else 'FAIL'} "
              f"starter_fails_hidden={r.starter_fails_hidden} {r.duration_ms}ms")
        for f in r.reference_failures:
            print(f"      ✗ {f}")
    print(f"{len(results) - bad}/{len(results)} verified")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
