from django.contrib import admin

from .models import MoodEntry, Profile, StudyPlan, StudySession, Subject, TimetableEntry


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "education_stage", "preferred_study_duration", "notifications_enabled")
    search_fields = ("user__email", "user__username")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "accent_color")
    search_fields = ("name", "user__email")


@admin.register(StudyPlan)
class StudyPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "subject", "priority", "status", "target_date")
    list_filter = ("priority", "status")
    search_fields = ("title", "user__email", "subject__name")


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "status", "timer_mode", "scheduled_start", "actual_duration_minutes")
    list_filter = ("status", "timer_mode")
    search_fields = ("title", "user__email", "subject__name")


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "day_of_week", "start_time", "end_time", "entry_type")
    list_filter = ("day_of_week", "entry_type")
    search_fields = ("title", "user__email", "subject__name")


@admin.register(MoodEntry)
class MoodEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "logged_for", "level", "note")
    list_filter = ("level",)
    search_fields = ("user__email", "note")
