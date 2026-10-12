"""Fleet analytics from file store or SQL aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from call_analysis.database import SyncSessionLocal
from call_analysis.models import CallRecordModel, JobStatus
from call_analysis.repository import get_call_repository, resolve_storage_backend
from call_analysis.schemas import AnalyticsSummary

if TYPE_CHECKING:
    pass


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def analytics_from_records(calls: list) -> AnalyticsSummary:
    from call_analysis.models import CallRecord

    by_status = {"completed": 0, "processing": 0, "failed": 0, "pending": 0}
    qa_scores: list[float] = []
    comp_scores: list[float] = []
    sent_scores: list[float] = []
    pii_total = 0
    languages: dict[str, int] = {}

    for c in calls:
        if not isinstance(c, CallRecord):
            continue
        st = c.status if c.status in by_status else "pending"
        by_status[st] = by_status.get(st, 0) + 1
        pii_total += len(c.pii_findings)
        if c.language:
            languages[c.language] = languages.get(c.language, 0) + 1
        qa = c.agents.get("qa_scorecard")
        if qa and qa.score is not None:
            qa_scores.append(float(qa.score))
        cr = c.agents.get("compliance_risk")
        if cr and cr.score is not None:
            comp_scores.append(float(cr.score))
        se = c.agents.get("sentiment_emotion")
        if se and se.score is not None:
            sent_scores.append(float(se.score))

    return AnalyticsSummary(
        total_calls=len(calls),
        completed=by_status["completed"],
        processing=by_status["processing"],
        failed=by_status["failed"],
        pending=by_status["pending"],
        avg_qa_score=_avg(qa_scores),
        avg_compliance_score=_avg(comp_scores),
        avg_sentiment_score=_avg(sent_scores),
        total_pii_findings=pii_total,
        languages=languages,
    )


def get_analytics(organization_id: UUID | None = None) -> AnalyticsSummary:
    if resolve_storage_backend() != "postgres":
        repo = get_call_repository()
        records, _ = repo.list_calls(organization_id)
        return analytics_from_records(records)

    org = organization_id
    if org is None:
        from call_analysis.repository import get_default_organization_id

        org = get_default_organization_id()

    with SyncSessionLocal() as db:
        base = select(CallRecordModel).where(CallRecordModel.organization_id == org)
        total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
        by_status: dict[str, int] = {}
        for status in JobStatus:
            cnt = db.execute(
                select(func.count()).where(
                    CallRecordModel.organization_id == org,
                    CallRecordModel.status == status,
                )
            ).scalar_one()
            by_status[status.value] = int(cnt)

        rows = db.execute(
            select(CallRecordModel.agents, CallRecordModel.pii_findings, CallRecordModel.language)
            .where(CallRecordModel.organization_id == org)
        ).all()

    qa_scores: list[float] = []
    comp_scores: list[float] = []
    sent_scores: list[float] = []
    pii_total = 0
    languages: dict[str, int] = {}
    for agents, pii, language in rows:
        pii_total += len(pii or [])
        if language:
            languages[str(language)] = languages.get(str(language), 0) + 1
        agents = agents or {}
        for key, target in (
            ("qa_scorecard", qa_scores),
            ("compliance_risk", comp_scores),
            ("sentiment_emotion", sent_scores),
        ):
            entry = agents.get(key) or {}
            score = entry.get("score") if isinstance(entry, dict) else None
            if score is not None:
                target.append(float(score))

    return AnalyticsSummary(
        total_calls=int(total),
        completed=by_status.get("completed", 0),
        processing=by_status.get("processing", 0),
        failed=by_status.get("failed", 0),
        pending=by_status.get("pending", 0),
        avg_qa_score=_avg(qa_scores),
        avg_compliance_score=_avg(comp_scores),
        avg_sentiment_score=_avg(sent_scores),
        total_pii_findings=pii_total,
        languages=languages,
    )
