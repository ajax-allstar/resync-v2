from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

User = get_user_model()


class EducationStage(models.TextChoices):
    ELEMENTARY = "elementary", "Elementary"
    HIGH_SCHOOL = "high-school", "High School"
    HIGHER_STUDIES = "higher-studies", "Higher Studies"


class Priority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class StudyStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    COMPLETED = "completed", "Completed"
    SKIPPED = "skipped", "Skipped"


class TimerMode(models.TextChoices):
    POMODORO = "pomodoro", "Pomodoro"
    CUSTOM = "custom", "Custom Focus"
    STOPWATCH = "stopwatch", "Stopwatch"


class DayOfWeek(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class EntryType(models.TextChoices):
    CLASS = "class", "Class"
    STUDY = "study", "Study"
    BREAK = "break", "Break"


class MoodLevel(models.IntegerChoices):
    DRAINED = 1, "Drained"
    UNEASY = 2, "Uneasy"
    STEADY = 3, "Steady"
    GOOD = 4, "Good"
    GREAT = 5, "Great"


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Profile(TimestampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    education_stage = models.CharField(
        max_length=32,
        choices=EducationStage.choices,
        default=EducationStage.HIGH_SCHOOL,
    )
    preferred_study_duration = models.PositiveIntegerField(default=45)
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    notifications_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.email or self.user.username} profile"


class Subject(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subjects")
    name = models.CharField(max_length=120)
    accent_color = models.CharField(max_length=7, default="#8FB7A5")

    class Meta:
        ordering = ["name"]
        unique_together = ("user", "name")

    def __str__(self):
        return self.name


class StudyPlan(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="study_plans")
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="study_plans",
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    target_date = models.DateField(null=True, blank=True)
    estimated_effort_hours = models.PositiveIntegerField(default=2)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=16, choices=StudyStatus.choices, default=StudyStatus.PLANNED)

    class Meta:
        ordering = ["target_date", "-created_at"]

    def __str__(self):
        return self.title


class TimetableEntry(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="timetable_entries")
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timetable_entries",
    )
    title = models.CharField(max_length=160)
    day_of_week = models.IntegerField(choices=DayOfWeek.choices)
    entry_type = models.CharField(max_length=16, choices=EntryType.choices, default=EntryType.STUDY)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["day_of_week", "start_time"]

    def __str__(self):
        return f"{self.get_day_of_week_display()} - {self.title}"

    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

        overlapping_entries = TimetableEntry.objects.filter(
            user=self.user,
            day_of_week=self.day_of_week,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time,
        )
        if self.pk:
            overlapping_entries = overlapping_entries.exclude(pk=self.pk)
        if overlapping_entries.exists():
            raise ValidationError("This timetable slot overlaps with an existing entry.")


class StudySession(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="study_sessions")
    plan = models.ForeignKey(
        StudyPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    title = models.CharField(max_length=160)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    actual_duration_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=StudyStatus.choices, default=StudyStatus.PLANNED)
    timer_mode = models.CharField(max_length=16, choices=TimerMode.choices, default=TimerMode.POMODORO)
    focus_minutes = models.PositiveIntegerField(default=25)
    break_minutes = models.PositiveIntegerField(default=5)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_start", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def suggested_duration(self):
        if self.scheduled_start and self.scheduled_end:
            return int((self.scheduled_end - self.scheduled_start).total_seconds() // 60)
        return self.focus_minutes

    def mark_completed(self, duration_minutes=None):
        self.status = StudyStatus.COMPLETED
        self.completed_at = timezone.now()
        self.actual_duration_minutes = duration_minutes or self.actual_duration_minutes or self.suggested_duration
        self.save(update_fields=["status", "completed_at", "actual_duration_minutes", "updated_at"])


class MoodEntry(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mood_entries")
    level = models.IntegerField(choices=MoodLevel.choices)
    note = models.CharField(max_length=240, blank=True)
    logged_for = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-logged_for", "-created_at"]
        unique_together = ("user", "logged_for")

    def __str__(self):
        return f"{self.user} {self.logged_for} mood"
