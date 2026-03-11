from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.LandingView.as_view(), name="landing"),
    path("signup/", views.SignUpView.as_view(), name="signup"),
    path("login/", views.ResyncLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(template_name="registration/password_reset_form.html"),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("app/dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("app/planner/", views.PlannerView.as_view(), name="planner"),
    path("app/timetable/", views.TimetableView.as_view(), name="timetable"),
    path("app/timer/", views.TimerView.as_view(), name="timer"),
    path("app/mood/", views.MoodView.as_view(), name="mood"),
    path("app/profile/", views.ProfileView.as_view(), name="profile"),
    path("api/dashboard-summary/", views.dashboard_summary_api, name="api-dashboard-summary"),
    path("api/study-plans/", views.study_plans_api, name="api-study-plans"),
    path("api/study-plans/<int:plan_id>/", views.study_plan_detail_api, name="api-study-plan-detail"),
    path("api/sessions/", views.sessions_api, name="api-sessions"),
    path("api/sessions/<int:session_id>/complete/", views.complete_session_api, name="api-session-complete"),
    path("api/timetable/", views.timetable_api, name="api-timetable"),
    path("api/timetable/<int:entry_id>/", views.timetable_detail_api, name="api-timetable-detail"),
    path("api/timetable/ai-draft/", views.ai_timetable_draft_api, name="api-ai-timetable-draft"),
    path("api/timetable/ai-accept/", views.accept_ai_timetable_draft_api, name="api-ai-timetable-accept"),
    path("api/moods/", views.moods_api, name="api-moods"),
]
