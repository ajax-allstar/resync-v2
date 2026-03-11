from datetime import timedelta
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import MoodEntry, StudyPlan, StudySession, StudyStatus, Subject, TimetableEntry

User = get_user_model()


class ReSyncTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="student@example.com",
            email="student@example.com",
            password="SafePassword123!",
            first_name="Student",
        )
        self.subject = Subject.objects.create(user=self.user, name="Biology")
        self.plan = StudyPlan.objects.create(user=self.user, subject=self.subject, title="Cell revision")
        self.session = StudySession.objects.create(
            user=self.user,
            subject=self.subject,
            plan=self.plan,
            title="Cell sprint",
            scheduled_start=timezone.now() + timedelta(hours=1),
            timer_mode="pomodoro",
        )

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_signup_creates_profile(self):
        response = self.client.post(
            reverse("signup"),
            {
                "first_name": "Lina",
                "email": "lina@example.com",
                "education_stage": "high-school",
                "preferred_study_duration": 40,
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
            },
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(User.objects.filter(email="lina@example.com").exists())

    def test_timetable_overlap_validation(self):
        TimetableEntry.objects.create(
            user=self.user,
            subject=self.subject,
            title="Morning focus",
            day_of_week=0,
            entry_type="study",
            start_time="09:00",
            end_time="10:00",
        )
        entry = TimetableEntry(
            user=self.user,
            subject=self.subject,
            title="Overlap",
            day_of_week=0,
            entry_type="study",
            start_time="09:30",
            end_time="10:30",
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_complete_session_api_marks_session_complete(self):
        self.client.login(username="student@example.com", password="SafePassword123!")
        response = self.client.post(
            reverse("api-session-complete", args=[self.session.id]),
            content_type="application/json",
            data='{"actual_duration_minutes": 30}',
        )
        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, StudyStatus.COMPLETED)
        self.assertEqual(self.session.actual_duration_minutes, 30)

    def test_mood_api_upserts_entry(self):
        self.client.login(username="student@example.com", password="SafePassword123!")
        response = self.client.post(
            reverse("api-moods"),
            content_type="application/json",
            data='{"level": 4, "note": "Feeling better"}',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(MoodEntry.objects.filter(user=self.user).count(), 1)

    def test_dashboard_summary_api_returns_motivation(self):
        self.client.login(username="student@example.com", password="SafePassword123!")
        response = self.client.get(reverse("api-dashboard-summary"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("motivation", response.json())

    def test_landing_page_shows_expanded_team_profiles(self):
        response = self.client.get(reverse("landing"))
        self.assertContains(response, "Daniel Santhosh")
        self.assertContains(response, "Ajax Shinto")
        self.assertNotContains(response, ">Daniel<", html=False)
        self.assertNotContains(response, "AjaxN")

    @override_settings(OPENROUTER_API_KEY="")
    def test_ai_timetable_missing_key_returns_clean_error(self):
        self.client.login(username="student@example.com", password="SafePassword123!")
        response = self.client.post(
            reverse("api-ai-timetable-draft"),
            content_type="application/json",
            data='{"study_goals":"Math","class_hours":"Mon 9-12","preferred_windows":"Afternoons"}',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("OPENROUTER_API_KEY", response.json()["detail"])

    @override_settings(OPENROUTER_API_KEY="test-key")
    @patch("core.ai_services.requests.post")
    def test_ai_timetable_uses_fallback_model(self, mock_post):
        self.client.login(username="student@example.com", password="SafePassword123!")

        failure = Mock()
        failure.raise_for_status.side_effect = requests.RequestException("boom")

        success = Mock()
        success.raise_for_status.return_value = None
        success.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"assumptions":["Afternoon focus works best"],"entries":[{"title":"Math Focus","day_of_week":0,"entry_type":"study","start_time":"14:00","end_time":"15:00","subject_name":"Biology"}]}'
                    }
                }
            ]
        }
        mock_post.side_effect = [failure, success]

        response = self.client.post(
            reverse("api-ai-timetable-draft"),
            content_type="application/json",
            data='{"study_goals":"Math and Biology","class_hours":"Mon 9-12","preferred_windows":"Afternoons"}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model"], "meta-llama/llama-3.3-70b-instruct:free")

    def test_ai_timetable_accept_creates_entries(self):
        self.client.login(username="student@example.com", password="SafePassword123!")
        response = self.client.post(
            reverse("api-ai-timetable-accept"),
            content_type="application/json",
            data='{"entries":[{"title":"Evening Review","day_of_week":2,"entry_type":"study","start_time":"18:00","end_time":"19:00","subject_name":"Biology"}]}',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(TimetableEntry.objects.filter(user=self.user, title="Evening Review").exists())

    def test_ai_timetable_rejects_overlapping_draft(self):
        self.client.login(username="student@example.com", password="SafePassword123!")
        response = self.client.post(
            reverse("api-ai-timetable-accept"),
            content_type="application/json",
            data='{"entries":[{"title":"First","day_of_week":1,"entry_type":"study","start_time":"10:00","end_time":"11:00"},{"title":"Second","day_of_week":1,"entry_type":"study","start_time":"10:30","end_time":"11:30"}]}',
        )
        self.assertEqual(response.status_code, 400)
