from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from .models import MoodLevel, MoodEntry, StudySession, StudyStatus, TimetableEntry


def get_streak_days(user):
    completion_days = list(
        user.study_sessions.filter(status=StudyStatus.COMPLETED, completed_at__isnull=False)
        .dates("completed_at", "day", order="DESC")
    )
    if not completion_days:
        return 0

    streak = 0
    cursor = timezone.localdate()
    valid_start_days = {cursor, cursor - timedelta(days=1)}
    if completion_days[0] not in valid_start_days:
        return 0

    completion_set = set(completion_days)
    while cursor in completion_set or (streak == 0 and cursor - timedelta(days=1) in completion_set):
        if cursor in completion_set:
            streak += 1
            cursor -= timedelta(days=1)
        elif cursor - timedelta(days=1) in completion_set:
            cursor -= timedelta(days=1)
    return streak


def get_motivation_message(user):
    streak = get_streak_days(user)
    recent_mood = user.mood_entries.order_by("-logged_for", "-created_at").first()
    completed_today = user.study_sessions.filter(
        status=StudyStatus.COMPLETED,
        completed_at__date=timezone.localdate(),
    ).count()

    if recent_mood and recent_mood.level <= MoodLevel.UNEASY:
        return "You do not need a perfect day. One calm session is enough to restart your rhythm."
    if streak >= 5:
        return f"You are on a {streak}-day streak. Protect your momentum with one focused block today."
    if completed_today >= 2:
        return "Your effort is stacking up today. Finish with a short review and call it a win."
    return "Start small, stay kind to yourself, and let one focused session lead the day."


def get_dashboard_summary(user):
    today = timezone.localdate()
    sessions = user.study_sessions.select_related("subject", "plan")
    todays_sessions = sessions.filter(scheduled_start__date=today)
    next_session = todays_sessions.filter(status=StudyStatus.PLANNED, scheduled_start__gte=timezone.now()).first()
    mood = user.mood_entries.filter(logged_for=today).first() or user.mood_entries.first()
    completed_minutes = sum(
        todays_sessions.filter(status=StudyStatus.COMPLETED).values_list("actual_duration_minutes", flat=True)
    )
    weekly_progress = sessions.filter(
        status=StudyStatus.COMPLETED,
        completed_at__date__gte=today - timedelta(days=6),
    ).count()

    timetable = defaultdict(list)
    for entry in user.timetable_entries.select_related("subject"):
        timetable[entry.day_of_week].append(entry)

    return {
        "today_count": todays_sessions.count(),
        "completed_minutes": completed_minutes,
        "streak_days": get_streak_days(user),
        "weekly_progress": weekly_progress,
        "next_session": next_session,
        "mood": mood,
        "motivation": get_motivation_message(user),
        "timetable": timetable,
        "recent_moods": list(user.mood_entries.all()[:5]),
    }
