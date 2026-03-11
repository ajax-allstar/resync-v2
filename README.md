# ReSync

ReSync is a Django-powered study support web app for students dealing with exam pressure, distractions, brain fog, and inconsistent routines. It ships with a warm, eye-comfortable UI, study planning tools, timers, mood tracking, timetable management, and installable PWA support.

## Stack

- Django 5
- SQLite for local development
- Django allauth for Google social login wiring
- Tailwind via CDN plus custom CSS for the visual system

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000`.

## Google sign-in

Google sign-in is implemented through `django-allauth`. To enable it locally, set:

```powershell
$env:GOOGLE_CLIENT_ID="your-client-id"
$env:GOOGLE_CLIENT_SECRET="your-client-secret"
```

## Included modules

- Landing page with product story and team credits
- Email signup/signin and password reset flow
- Dashboard with next session, study metrics, mood snapshot, and motivation
- Planner for subjects, study plans, and scheduled sessions
- Timetable builder with overlap prevention
- Mood tracker
- Focus timer with local persistence
- JSON endpoints for dashboard, plans, sessions, timetable, and mood
- PWA manifest and service worker
"# resync-v2" 
