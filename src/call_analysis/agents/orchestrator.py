"""Orchestrate QA, compliance, sentiment, root-cause, CRM, and RAG copilot agents."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from call_analysis.agents.base import (
    heuristic_sentiment_timeline,
    run_structured_agent,
    transcript_block,
)
from call_analysis.config import NvidiaConfig
from call_analysis.models import AgentResult, TranscriptSegment
from call_analysis.nim_client import chat_completion


def run_all_agents(
    config: NvidiaConfig,
    *,
    transcript: str,
    segments: list[TranscriptSegment],
    filename: str = "",
    max_workers: int = 4,
) -> dict[str, AgentResult]:
    """Run the specialized agent battery in parallel; returns name → AgentResult."""
    body = transcript_block(transcript)
    meta = f"Recording: {filename}\n\n" if filename else ""
    diarized = _format_segments(segments) if segments else body

    jobs: list[tuple[str, Callable[[], AgentResult]]] = [
        (
            "qa_scorecard",
            lambda: run_structured_agent(
                config,
                name="qa_scorecard",
                system=(
                    "You are a contact-center QA Scorecard Agent. Score agent performance "
                    "0-100. Respond ONLY with JSON: "
                    '{"summary": str, "score": number, "criteria": '
                    '{"greeting": number, "empathy": number, "resolution": number, '
                    '"compliance": number, "closing": number}, "coaching_tips": [str]}'
                ),
                prompt=f"{meta}Evaluate this call transcript for QA:\n\n{diarized}",
            ),
        ),
        (
            "compliance_risk",
            lambda: run_structured_agent(
                config,
                name="compliance_risk",
                system=(
                    "You are a Compliance & Risk Agent for contact centers (privacy, "
                    "misrepresentation, mandatory disclosures, harassment). "
                    "Respond ONLY with JSON: "
                    '{"summary": str, "score": number, "risk_level": "low|medium|high", '
                    '"flags": [{"severity": str, "category": str, "evidence": str}], '
                    '"recommendations": [str]}. score=100 means fully compliant.'
                ),
                prompt=f"{meta}Review compliance risks:\n\n{diarized}",
            ),
        ),
        (
            "sentiment_emotion",
            lambda: run_structured_agent(
                config,
                name="sentiment_emotion",
                system=(
                    "You are a Sentiment & Emotional Vector Agent. Analyze customer and "
                    "agent emotion. Respond ONLY with JSON: "
                    '{"summary": str, "score": number, "customer_sentiment": '
                    '"positive|neutral|negative", "agent_sentiment": "positive|neutral|negative", '
                    '"emotion_vector": {"anger": number, "frustration": number, '
                    '"satisfaction": number, "urgency": number}, "turning_points": [str]}. '
                    "score 0-100 where 100 is highly positive customer experience. "
                    "emotion values 0-1."
                ),
                prompt=f"{meta}Analyze sentiment and emotions:\n\n{diarized}",
            ),
        ),
        (
            "root_cause_intent",
            lambda: run_structured_agent(
                config,
                name="root_cause_intent",
                system=(
                    "You are a Root Cause & Intent Mining Agent. Identify why the customer "
                    "called and underlying issues. Respond ONLY with JSON: "
                    '{"summary": str, "score": number, "primary_intent": str, '
                    '"intents": [str], "root_causes": [str], "product_areas": [str], '
                    '"resolved": boolean}. score is confidence 0-100.'
                ),
                prompt=f"{meta}Mine intents and root causes:\n\n{diarized}",
            ),
        ),
        (
            "crm_action_items",
            lambda: run_structured_agent(
                config,
                name="crm_action_items",
                system=(
                    "You are an Action Item & CRM Sync Agent. Extract follow-ups suitable "
                    "for CRM. Respond ONLY with JSON: "
                    '{"summary": str, "score": number, "action_items": '
                    '[{"owner": "agent|customer|ops", "action": str, "due": str}], '
                    '"crm_fields": {"subject": str, "priority": "low|medium|high", '
                    '"tags": [str], "notes": str}}. score is completeness 0-100.'
                ),
                prompt=f"{meta}Extract CRM action items:\n\n{diarized}",
            ),
        ),
        (
            "call_copilot",
            lambda: run_structured_agent(
                config,
                name="call_copilot",
                system=(
                    "You are an Interactive Call Copilot (RAG-style). Build a concise "
                    "knowledge brief from this call for supervisor Q&A. Respond ONLY with JSON: "
                    '{"summary": str, "score": number, "key_facts": [str], '
                    '"policies_mentioned": [str], "suggested_next_steps": [str], '
                    '"faq": [{"q": str, "a": str}]}. score is brief quality 0-100.'
                ),
                prompt=f"{meta}Build copilot knowledge brief:\n\n{diarized}",
            ),
        ),
    ]

    agents: dict[str, AgentResult] = {}
    workers = max(1, min(max_workers, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn): name for name, fn in jobs}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                agents[name] = fut.result()
            except Exception as exc:  # noqa: BLE001
                agents[name] = AgentResult(
                    name=name,
                    summary=f"Agent failed: {exc}",
                    score=None,
                    details={"error": str(exc)},
                )

    # Attach heuristic timeline into sentiment details
    timeline = heuristic_sentiment_timeline(segments)
    se = agents.get("sentiment_emotion")
    if se is not None:
        details = dict(se.details or {})
        details["timeline"] = timeline
        agents["sentiment_emotion"] = AgentResult(
            name=se.name,
            summary=se.summary,
            score=se.score,
            details=details,
            raw_text=se.raw_text,
        )

    # Stable key order for consumers
    ordered = {
        k: agents[k]
        for k in (
            "qa_scorecard",
            "compliance_risk",
            "sentiment_emotion",
            "root_cause_intent",
            "crm_action_items",
            "call_copilot",
        )
        if k in agents
    }
    return ordered


def answer_copilot(
    config: NvidiaConfig,
    *,
    question: str,
    transcript: str,
    agent_context: dict[str, Any] | None = None,
) -> str:
    """Interactive RAG-style Q&A grounded in call transcript + prior analysis."""
    ctx_bits = []
    if agent_context:
        for name, payload in agent_context.items():
            if isinstance(payload, dict):
                ctx_bits.append(f"{name}: {payload.get('summary', '')}")
            else:
                ctx_bits.append(f"{name}: {payload}")
    context = "\n".join(ctx_bits)
    prompt = (
        f"Call analysis context:\n{context}\n\n"
        f"Transcript:\n{transcript_block(transcript, max_chars=8000)}\n\n"
        f"Supervisor question: {question}\n\n"
        "Answer using only the call evidence. If unknown, say you cannot find it."
    )
    result = chat_completion(
        config,
        system=(
            "You are the Interactive Call Copilot for contact-center supervisors. "
            "Be concise, factual, and cite speakers/times when possible."
        ),
        prompt=prompt,
        max_tokens=600,
        temperature=0.2,
    )
    return result.text


def _format_segments(segments: list[TranscriptSegment]) -> str:
    lines = []
    for s in segments:
        lines.append(f"[{s.start:.1f}-{s.end:.1f}] {s.speaker}: {s.text}")
    return "\n".join(lines)
