from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import MoodEntry, Profile, StudyPlan, StudySession, Subject, TimetableEntry

User = get_user_model()


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "mt-2 w-full rounded-2xl border border-sand-300 bg-white/90 px-4 py-3 text-sm text-stone-700 shadow-sm outline-none transition focus:border-moss-500 focus:ring-2 focus:ring-moss-200",
            )


class SignUpForm(StyledFormMixin, UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True, max_length=150)
    education_stage = forms.ChoiceField(choices=Profile._meta.get_field("education_stage").choices)
    preferred_study_duration = forms.IntegerField(min_value=15, max_value=180, initial=45)

    class Meta:
        model = User
        fields = ("first_name", "email", "education_stage", "preferred_study_duration", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        if commit:
            user.save()
            profile = user.profile
            profile.education_stage = self.cleaned_data["education_stage"]
            profile.preferred_study_duration = self.cleaned_data["preferred_study_duration"]
            profile.save()
        return user


class SignInForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(label="Email")


class SubjectForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Subject
        fields = ("name", "accent_color")
        widgets = {
            "accent_color": forms.TextInput(attrs={"type": "color", "class": "mt-2 h-12 w-full rounded-2xl border border-sand-300 bg-white/90 p-2"}),
        }


class StudyPlanForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = StudyPlan
        fields = ("subject", "title", "description", "target_date", "estimated_effort_hours", "priority")
        widgets = {
            "target_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class StudySessionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = StudySession
        fields = (
            "plan",
            "subject",
            "title",
            "scheduled_start",
            "scheduled_end",
            "timer_mode",
            "focus_minutes",
            "break_minutes",
        )
        widgets = {
            "scheduled_start": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "scheduled_end": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class TimetableEntryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TimetableEntry
        fields = ("subject", "title", "day_of_week", "entry_type", "start_time", "end_time")
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }


class AITimetableRequestForm(StyledFormMixin, forms.Form):
    study_goals = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    class_hours = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    preferred_windows = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    break_preferences = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    pressure_notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
    additional_constraints = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)


class MoodEntryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = MoodEntry
        fields = ("level", "note", "logged_for")
        widgets = {
            "logged_for": forms.DateInput(attrs={"type": "date"}),
        }


class ProfileForm(StyledFormMixin, forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    email = forms.EmailField()

    class Meta:
        model = Profile
        fields = ("education_stage", "preferred_study_duration", "timezone", "notifications_enabled")

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = user.first_name
        self.fields["email"].initial = user.email

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.user.first_name = self.cleaned_data["first_name"]
        profile.user.email = self.cleaned_data["email"]
        profile.user.username = self.cleaned_data["email"]
        if commit:
            profile.user.save()
            profile.save()
        return profile
