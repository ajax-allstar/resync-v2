import json

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from django.views.decorators.http import require_http_methods
from django.views.generic import FormView, TemplateView

from .ai_services import TimetableAIError, generate_timetable_draft, persist_timetable_draft
from .forms import (
    AITimetableRequestForm,
    MoodEntryForm,
    ProfileForm,
    SignInForm,
    SignUpForm,
    StudyPlanForm,
    StudySessionForm,
    SubjectForm,
    TimetableEntryForm,
)
from .models import MoodEntry, StudyPlan, StudySession, StudyStatus, Subject, TimetableEntry
from .services import get_dashboard_summary, get_motivation_message, get_streak_days


class LandingView(TemplateView):
    template_name = "core/landing.html"


class SignUpView(FormView):
    template_name = "registration/signup.html"
    form_class = SignUpForm
    success_url = reverse_lazy("dashboard")

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, "Welcome to ReSync. Your focus space is ready.")
        return super().form_valid(form)


class ResyncLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = SignInForm
    redirect_authenticated_user = True


class AppPageMixin(LoginRequiredMixin):
    def get_subject_queryset(self):
        return self.request.user.subjects.all()

    def build_common_context(self):
        summary = get_dashboard_summary(self.request.user)
        return {
            "summary": summary,
            "motivation_message": summary["motivation"],
            "subject_count": self.request.user.subjects.count(),
        }


class DashboardView(AppPageMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_common_context())
        context.update(
            {
                "section_label": "Dashboard",
                "section_title": f"Welcome back, {self.request.user.first_name or 'Student'}",
                "section_copy": "See today’s plan, protect your attention, and return to one clear next step whenever the day feels noisy.",
            }
        )
        context["upcoming_sessions"] = self.request.user.study_sessions.select_related("subject", "plan")[:5]
        context["study_plans"] = self.request.user.study_plans.select_related("subject")[:4]
        context["mood_form"] = MoodEntryForm(initial={"logged_for": timezone.localdate()})
        return context

    def post(self, request, *args, **kwargs):
        form = MoodEntryForm(request.POST)
        if form.is_valid():
            mood, created = MoodEntry.objects.update_or_create(
                user=request.user,
                logged_for=form.cleaned_data["logged_for"],
                defaults={
                    "level": form.cleaned_data["level"],
                    "note": form.cleaned_data["note"],
                },
            )
            messages.success(
                request,
                "Mood saved." if created else "Mood updated. Your dashboard has been refreshed.",
            )
        else:
            messages.error(request, "Please fix the mood form and try again.")
        return redirect("dashboard")


class PlannerView(AppPageMixin, TemplateView):
    template_name = "core/planner.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_common_context())
        context.update(
            {
                "section_label": "Planner",
                "section_title": "Turn stress into structure",
                "section_copy": "Add subjects, break goals into study plans, and schedule sessions that are realistic enough to finish.",
            }
        )
        context["study_plan_form"] = StudyPlanForm()
        context["session_form"] = StudySessionForm()
        context["subject_form"] = SubjectForm()
        context["plans"] = self.request.user.study_plans.select_related("subject").annotate(session_total=Count("sessions"))
        context["sessions"] = self.request.user.study_sessions.select_related("subject", "plan")[:10]

        for form_name in ("study_plan_form", "session_form"):
            context[form_name].fields["subject"].queryset = self.get_subject_queryset()
        context["session_form"].fields["plan"].queryset = self.request.user.study_plans.all()
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        if action == "subject":
            form = SubjectForm(request.POST)
            if form.is_valid():
                subject = form.save(commit=False)
                subject.user = request.user
                subject.save()
                messages.success(request, "Subject added to your study space.")
            else:
                messages.error(request, "Could not save subject.")
        elif action == "plan":
            form = StudyPlanForm(request.POST)
            form.fields["subject"].queryset = self.get_subject_queryset()
            if form.is_valid():
                plan = form.save(commit=False)
                plan.user = request.user
                plan.save()
                messages.success(request, "Study plan created.")
            else:
                messages.error(request, "Please review the study plan form.")
        elif action == "session":
            form = StudySessionForm(request.POST)
            form.fields["subject"].queryset = self.get_subject_queryset()
            form.fields["plan"].queryset = request.user.study_plans.all()
            if form.is_valid():
                session = form.save(commit=False)
                session.user = request.user
                session.save()
                messages.success(request, "Study session scheduled.")
            else:
                messages.error(request, "Session could not be saved.")
        return redirect("planner")


class TimetableView(AppPageMixin, TemplateView):
    template_name = "core/timetable.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_common_context())
        context.update(
            {
                "section_label": "Timetable",
                "section_title": "Shape your weekly rhythm",
                "section_copy": "Classes, study blocks, and breaks belong in one visible structure so your time feels less slippery.",
            }
        )
        form = TimetableEntryForm()
        form.fields["subject"].queryset = self.get_subject_queryset()
        context["entry_form"] = form
        context["ai_form"] = AITimetableRequestForm(
            initial={"break_preferences": "Short breaks after 45 to 60 minutes of study."}
        )
        context["entries"] = self.request.user.timetable_entries.select_related("subject")
        return context

    def post(self, request, *args, **kwargs):
        form = TimetableEntryForm(request.POST)
        form.fields["subject"].queryset = self.get_subject_queryset()
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            try:
                entry.full_clean()
                entry.save()
                messages.success(request, "Timetable entry saved.")
            except ValidationError as exc:
                form.add_error(None, exc.message)
                messages.error(request, exc.message)
        else:
            messages.error(request, "Please review the timetable fields.")
        return redirect("timetable")


class TimerView(AppPageMixin, TemplateView):
    template_name = "core/timer.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_common_context())
        context.update(
            {
                "section_label": "Timer",
                "section_title": "Focus without harsh pressure",
                "section_copy": "Use Pomodoro, custom cycles, or an open stopwatch. ReSync keeps the timer state locally if the page refreshes.",
            }
        )
        context["sessions"] = self.request.user.study_sessions.filter(status=StudyStatus.PLANNED)[:8]
        return context


class MoodView(AppPageMixin, TemplateView):
    template_name = "core/mood.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_common_context())
        context.update(
            {
                "section_label": "Mood",
                "section_title": "Check in with how the day feels",
                "section_copy": "Your study plan works better when it respects your energy, anxiety, and momentum instead of ignoring them.",
            }
        )
        context["mood_form"] = MoodEntryForm(initial={"logged_for": timezone.localdate()})
        context["moods"] = self.request.user.mood_entries.all()[:30]
        return context

    def post(self, request, *args, **kwargs):
        form = MoodEntryForm(request.POST)
        if form.is_valid():
            MoodEntry.objects.update_or_create(
                user=request.user,
                logged_for=form.cleaned_data["logged_for"],
                defaults={"level": form.cleaned_data["level"], "note": form.cleaned_data["note"]},
            )
            messages.success(request, "Mood updated.")
        else:
            messages.error(request, "Mood entry could not be saved.")
        return redirect("mood")


class ProfileView(AppPageMixin, TemplateView):
    template_name = "core/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.build_common_context())
        context.update(
            {
                "section_label": "Profile",
                "section_title": "Personalize your study comfort",
                "section_copy": "Adjust the settings ReSync uses to shape defaults, reminders, and your overall study environment.",
            }
        )
        context["profile_form"] = ProfileForm(instance=self.request.user.profile, user=self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        form = ProfileForm(request.POST, instance=request.user.profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved.")
        else:
            messages.error(request, "Please review the profile fields.")
        return redirect("profile")


def _parse_body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return None


def _parsed_date(value):
    return parse_date(value) if value else None


def _parsed_datetime(value):
    return parse_datetime(value) if value else None


def _parsed_time(value):
    return parse_time(value) if value else None


def _json_plan(plan):
    return {
        "id": plan.id,
        "title": plan.title,
        "subject": plan.subject.name if plan.subject else None,
        "priority": plan.priority,
        "status": plan.status,
        "target_date": plan.target_date.isoformat() if plan.target_date else None,
        "estimated_effort_hours": plan.estimated_effort_hours,
    }


def _json_session(session):
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "subject": session.subject.name if session.subject else None,
        "plan": session.plan.title if session.plan else None,
        "scheduled_start": session.scheduled_start.isoformat() if session.scheduled_start else None,
        "scheduled_end": session.scheduled_end.isoformat() if session.scheduled_end else None,
        "actual_duration_minutes": session.actual_duration_minutes,
        "timer_mode": session.timer_mode,
        "focus_minutes": session.focus_minutes,
        "break_minutes": session.break_minutes,
    }


@require_http_methods(["GET"])
def dashboard_summary_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    summary = get_dashboard_summary(request.user)
    return JsonResponse(
        {
            "today_count": summary["today_count"],
            "completed_minutes": summary["completed_minutes"],
            "streak_days": summary["streak_days"],
            "weekly_progress": summary["weekly_progress"],
            "motivation": summary["motivation"],
            "next_session": _json_session(summary["next_session"]) if summary["next_session"] else None,
        }
    )


@require_http_methods(["GET", "POST"])
def study_plans_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    if request.method == "GET":
        plans = [_json_plan(plan) for plan in request.user.study_plans.select_related("subject")]
        return JsonResponse({"results": plans})

    data = _parse_body(request)
    if data is None:
        return HttpResponseBadRequest("Invalid JSON")
    subject = get_object_or_404(Subject, pk=data.get("subject_id"), user=request.user) if data.get("subject_id") else None
    plan = StudyPlan.objects.create(
        user=request.user,
        subject=subject,
        title=data["title"],
        description=data.get("description", ""),
        estimated_effort_hours=data.get("estimated_effort_hours", 2),
        priority=data.get("priority", "medium"),
        target_date=_parsed_date(data.get("target_date")),
    )
    return JsonResponse(_json_plan(plan), status=201)


@require_http_methods(["PATCH", "DELETE"])
def study_plan_detail_api(request, plan_id):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    plan = get_object_or_404(StudyPlan, pk=plan_id, user=request.user)
    if request.method == "DELETE":
        plan.delete()
        return JsonResponse({}, status=204)

    data = _parse_body(request)
    if data is None:
        return HttpResponseBadRequest("Invalid JSON")
    for field in ("title", "description", "priority", "status", "target_date", "estimated_effort_hours"):
        if field in data:
            value = data[field] or None
            if field == "target_date":
                value = _parsed_date(value)
            setattr(plan, field, value)
    if "subject_id" in data:
        plan.subject = get_object_or_404(Subject, pk=data["subject_id"], user=request.user) if data["subject_id"] else None
    plan.save()
    return JsonResponse(_json_plan(plan))


@require_http_methods(["GET", "POST"])
def sessions_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    if request.method == "GET":
        sessions = [_json_session(session) for session in request.user.study_sessions.select_related("subject", "plan")]
        return JsonResponse({"results": sessions})

    data = _parse_body(request)
    if data is None:
        return HttpResponseBadRequest("Invalid JSON")
    session = StudySession.objects.create(
        user=request.user,
        title=data["title"],
        plan=get_object_or_404(StudyPlan, pk=data["plan_id"], user=request.user) if data.get("plan_id") else None,
        subject=get_object_or_404(Subject, pk=data["subject_id"], user=request.user) if data.get("subject_id") else None,
        scheduled_start=_parsed_datetime(data.get("scheduled_start")),
        scheduled_end=_parsed_datetime(data.get("scheduled_end")),
        timer_mode=data.get("timer_mode", "pomodoro"),
        focus_minutes=data.get("focus_minutes", 25),
        break_minutes=data.get("break_minutes", 5),
    )
    return JsonResponse(_json_session(session), status=201)


@require_http_methods(["POST"])
def complete_session_api(request, session_id):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    session = get_object_or_404(StudySession, pk=session_id, user=request.user)
    data = _parse_body(request)
    if data is None:
        return HttpResponseBadRequest("Invalid JSON")
    session.mark_completed(duration_minutes=data.get("actual_duration_minutes"))
    return JsonResponse(
        {
            "session": _json_session(session),
            "motivation": get_motivation_message(request.user),
            "streak_days": get_streak_days(request.user),
        }
    )


@require_http_methods(["GET", "POST"])
def timetable_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    if request.method == "GET":
        results = [
            {
                "id": entry.id,
                "title": entry.title,
                "day_of_week": entry.day_of_week,
                "entry_type": entry.entry_type,
                "subject": entry.subject.name if entry.subject else None,
                "start_time": entry.start_time.isoformat(),
                "end_time": entry.end_time.isoformat(),
            }
            for entry in request.user.timetable_entries.select_related("subject")
        ]
        return JsonResponse({"results": results})

    data = _parse_body(request)
    if data is None:
        return HttpResponseBadRequest("Invalid JSON")
    entry = TimetableEntry(
        user=request.user,
        title=data["title"],
        day_of_week=data["day_of_week"],
        entry_type=data.get("entry_type", "study"),
        start_time=_parsed_time(data["start_time"]),
        end_time=_parsed_time(data["end_time"]),
        subject=get_object_or_404(Subject, pk=data["subject_id"], user=request.user) if data.get("subject_id") else None,
    )
    entry.full_clean()
    entry.save()
    return JsonResponse({"id": entry.id}, status=201)


@require_http_methods(["PATCH", "DELETE"])
def timetable_detail_api(request, entry_id):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    entry = get_object_or_404(TimetableEntry, pk=entry_id, user=request.user)
    if request.method == "DELETE":
        entry.delete()
        return JsonResponse({}, status=204)

    data = _parse_body(request)
    if data is None:
        return HttpResponseBadRequest("Invalid JSON")
    for field in ("title", "day_of_week", "entry_type", "start_time", "end_time"):
        if field in data:
            value = data[field]
            if field in {"start_time", "end_time"}:
                value = _parsed_time(value)
            setattr(entry, field, value)
    entry.full_clean()
    entry.save()
    return JsonResponse({"id": entry.id, "title": entry.title})


@require_http_methods(["GET", "POST"])
def moods_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    if request.method == "GET":
        results = [
            {
                "id": mood.id,
                "level": mood.level,
                "label": mood.get_level_display(),
                "note": mood.note,
                "logged_for": mood.logged_for.isoformat(),
            }
            for mood in request.user.mood_entries.all()[:30]
        ]
        return JsonResponse({"results": results})

    data = _parse_body(request)
    if data is None:
        return HttpResponseBadRequest("Invalid JSON")
    mood, _ = MoodEntry.objects.update_or_create(
        user=request.user,
        logged_for=data.get("logged_for", timezone.localdate()),
        defaults={"level": data["level"], "note": data.get("note", "")},
    )
    return JsonResponse({"id": mood.id, "label": mood.get_level_display()}, status=201)


@require_http_methods(["POST"])
def ai_timetable_draft_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    data = _parse_body(request)
    if data is None:
        return HttpResponseBadRequest("Invalid JSON")

    form = AITimetableRequestForm(data)
    if not form.is_valid():
        return JsonResponse({"detail": "Please review the AI timetable form.", "errors": form.errors}, status=400)

    payload = form.cleaned_data
    payload["education_stage"] = request.user.profile.education_stage
    payload["available_subjects"] = list(request.user.subjects.values_list("name", flat=True))
    payload["user"] = request.user

    try:
        draft = generate_timetable_draft(payload)
    except TimetableAIError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse(
        {
            "assumptions": draft.assumptions,
            "entries": draft.entries,
            "model": draft.model,
        }
    )


@require_http_methods(["POST"])
def accept_ai_timetable_draft_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=403)
    data = _parse_body(request)
    if data is None or "entries" not in data:
        return HttpResponseBadRequest("Invalid JSON")

    try:
        created = persist_timetable_draft(request.user, data["entries"])
    except TimetableAIError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    return JsonResponse({"created": len(created)}, status=201)
