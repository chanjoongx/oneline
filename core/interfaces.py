"""The interfaces core depends on. Dependency inversion: core defines what it
needs, and the other modules implement these against the shared schemas.

- ImplementerClient: implemented in sandbox/
- JudgeClient and Curator: implemented in judges/
- Deployer: implemented in web/

Each method returns or accepts shapes defined in shared/schemas. core never
imports from sandbox/, judges/, or web/; it is handed an object that satisfies
the relevant Protocol.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class ImplementerClient(Protocol):
    def build_candidate(self, strategy: dict, brief: str, lessons: list) -> dict:
        """Build one candidate in its own Managed Agents sandbox.

        strategy is one entry from Plan.candidate_strategies. brief is the build
        brief. lessons is RetrievedLessons.retrieved_lessons. Returns a Candidate
        dict (candidate_id, html, environment_id, and optionally steps, rationale,
        accent). May be called concurrently, one thread per candidate, so build in
        an isolated sandbox per call and keep the implementation concurrency-safe.
        May also be defined as async. Implemented in sandbox/.
        """
        ...


@runtime_checkable
class JudgeClient(Protocol):
    def judge(self, candidate: dict, plan: dict) -> dict:
        """Score one candidate on all three axes.

        Reuses candidate["environment_id"] for the Playwright functionality run.
        Returns a JudgeScores dict (headline scores plus the three detail
        objects). May be called concurrently, one thread per candidate, so keep
        the implementation concurrency-safe. May also be defined as async.
        Implemented in judges/.
        """
        ...


@runtime_checkable
class Curator(Protocol):
    def curate(self, loser: dict, plan: dict) -> Optional[dict]:
        """Turn a losing candidate into a curator_output lesson.

        Returns the curator_output dict, or None when nothing generalizable is
        found. Implemented in judges/.
        """
        ...


@runtime_checkable
class Deployer(Protocol):
    def deploy(self, winner_html: str) -> dict:
        """Push the winning HTML to a pre-warmed Cloud Run service.

        Returns {"url": str, "service": str, "ts": int}. Implemented in web/.
        """
        ...
