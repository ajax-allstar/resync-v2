import json
from dataclasses import dataclass
from datetime import time

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_time

from .models import EntryType, TimetableEntry


class TimetableAIError(Exception):
    pass


@dataclass
class DraftResult:
    assumptions: list[str]
    entries: list[dict]
    model: str


def _build_prompt(payload):
    return {
        "education_stage": payload.get("education_stage"),
        "study_goals": payload.get("study_goals"),
        "class_hours": payload.get("class_hours"),
        "preferred_windows": payload.get("preferred_windows"),
        "break_preferences": payload.get("break_preferences"),
        "pressure_notes": payload.get("pressure_notes"),
        "additional_constraints": payload.get("additional_constraints"),
        "available_subjects": payload.get("available_subjects", []),
    }


def _messages(payload):
    schema = {
        "assumptions": ["short bullet"],
        "entries": [
            {
                "title": "string",
                "day_of_week": 0,
                "entry_type": "study",
                "start_time": "09:00",
                "end_time": "10:00",
                "subject_name": "optional string",
            }
        ],
    }
    return [
        {
            "role": "system",
            "content": (
                "You generate a weekly student timetable. Return JSON only with no markdown. "
                "The response must strictly match this schema: "
                f"{json.dumps(schema)}. "
                "Use day_of_week 0-6 for Monday-Sunday. "
                f"Allowed entry_type values: {', '.join(value for value, _ in EntryType.choices)}. "
                "Do not include overlapping entries on the same day. Keep assumptions concise."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(_build_prompt(payload)),
        },
    ]


def _extract_json(content):
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(content)


def _normalize_entry(entry):
    normalized = {
        "title": str(entry["title"]).strip(),
        "day_of_week": int(entry["day_of_week"]),
        "entry_type": str(entry["entry_type"]).strip().lower(),
        "start_time": str(entry["start_time"]).strip(),
        "end_time": str(entry["end_time"]).strip(),
        "subject_name": str(entry.get("subject_name", "")).strip() or None,
    }
    return normalized


def validate_timetable_draft(user, draft):
    assumptions = draft.get("assumptions")
    entries = draft.get("entries")
    if not isinstance(assumptions, list) or not isinstance(entries, list) or not entries:
        raise TimetableAIError("The AI response did not include a valid timetable draft.")

    normalized_entries = [_normalize_entry(entry) for entry in entries]
    day_buckets = {}
    existing = {}
    for item in user.timetable_entries.all():
        existing.setdefault(item.day_of_week, []).append((item.start_time, item.end_time))

    for entry in normalized_entries:
        if not entry["title"]:
            raise TimetableAIError("Each AI timetable block must include a title.")
        if entry["entry_type"] not in {value for value, _ in EntryType.choices}:
            raise TimetableAIError("The AI used an unsupported timetable entry type.")
        if entry["day_of_week"] not in range(7):
            raise TimetableAIError("The AI returned an invalid day_of_week value.")
        start = parse_time(entry["start_time"])
        end = parse_time(entry["end_time"])
        if not isinstance(start, time) or not isinstance(end, time) or end <= start:
            raise TimetableAIError("The AI returned an invalid time range.")

        for existing_start, existing_end in existing.get(entry["day_of_week"], []):
            if existing_start < end and existing_end > start:
                raise TimetableAIError("The AI draft overlaps with an existing timetable block.")

        for queued_start, queued_end in day_buckets.get(entry["day_of_week"], []):
            if queued_start < end and queued_end > start:
                raise TimetableAIError("The AI draft contains overlapping blocks.")

        day_buckets.setdefault(entry["day_of_week"], []).append((start, end))

    return {
        "assumptions": [str(item).strip() for item in assumptions if str(item).strip()],
        "entries": normalized_entries,
    }


def generate_timetable_draft(payload):
    if not settings.OPENROUTER_API_KEY:
        raise TimetableAIError("AI timetable generation is unavailable until OPENROUTER_API_KEY is configured.")

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    last_error = None

    for model in settings.OPENROUTER_TIMETABLE_MODELS:
        try:
            response = requests.post(
                settings.OPENROUTER_API_URL,
                headers=headers,
                json={
                    "model": model,
                    "messages": _messages(payload),
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                },
                timeout=45,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            draft = _extract_json(content)
            validated = validate_timetable_draft(payload["user"], draft)
            return DraftResult(
                assumptions=validated["assumptions"],
                entries=validated["entries"],
                model=model,
            )
        except (requests.RequestException, KeyError, IndexError, ValueError, TimetableAIError) as exc:
            last_error = exc

    raise TimetableAIError(
        "We could not generate a usable AI timetable draft right now."
        if last_error is None
        else str(last_error)
    )


def persist_timetable_draft(user, draft_entries):
    validated = validate_timetable_draft(user, {"assumptions": ["accepted"], "entries": draft_entries})
    subjects = {subject.name.lower(): subject for subject in user.subjects.all()}
    created = []
    for entry in validated["entries"]:
        created.append(
            TimetableEntry.objects.create(
                user=user,
                subject=subjects.get(entry["subject_name"].lower()) if entry["subject_name"] else None,
                title=entry["title"],
                day_of_week=entry["day_of_week"],
                entry_type=entry["entry_type"],
                start_time=parse_time(entry["start_time"]),
                end_time=parse_time(entry["end_time"]),
            )
        )
    return created
