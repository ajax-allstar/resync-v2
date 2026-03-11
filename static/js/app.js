const storageKey = "resync-active-timer";
let deferredInstallPrompt = null;

function pad(value) {
    return String(value).padStart(2, "0");
}

function formatSeconds(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${pad(minutes)}:${pad(seconds)}`;
}

function loadTimerState() {
    try {
        return JSON.parse(window.localStorage.getItem(storageKey) || "null");
    } catch {
        return null;
    }
}

function saveTimerState(state) {
    window.localStorage.setItem(storageKey, JSON.stringify(state));
}

function mountDashboard() {
    if (!window.resyncPage?.summaryUrl) return;
    window.fetch(window.resyncPage.summaryUrl, { credentials: "same-origin" })
        .then((response) => response.json())
        .then((data) => {
            const motivation = document.querySelector("#dashboard-motivation");
            if (motivation && data.motivation) motivation.textContent = data.motivation;
        })
        .catch(() => null);
}

function mountTimer() {
    const display = document.querySelector("#timer-display");
    if (!display) return;

    const label = document.querySelector("#timer-label");
    const phase = document.querySelector("#timer-phase");
    const feedback = document.querySelector("#timer-feedback");
    const focusInput = document.querySelector("#timer-focus-minutes");
    const breakInput = document.querySelector("#timer-break-minutes");
    const sessionSelect = document.querySelector("#timer-session-id");
    const startButton = document.querySelector("#timer-start");
    const pauseButton = document.querySelector("#timer-pause");
    const resetButton = document.querySelector("#timer-reset");
    const completeButton = document.querySelector("#timer-complete");

    let state = loadTimerState() || {
        mode: "pomodoro",
        focusMinutes: 25,
        breakMinutes: 5,
        phase: "focus",
        running: false,
        remainingSeconds: 1500,
        baseSeconds: 1500,
        startedAt: null,
    };

    function syncView() {
        focusInput.value = state.focusMinutes;
        breakInput.value = state.breakMinutes;
        label.textContent = state.mode.charAt(0).toUpperCase() + state.mode.slice(1);
        phase.textContent = state.phase === "focus" ? "Focus phase" : state.phase === "break" ? "Break phase" : "Open session";
        display.textContent = formatSeconds(Math.max(state.remainingSeconds, 0));
        saveTimerState(state);
    }

    function recomputeRemaining() {
        if (!state.running || !state.startedAt) return;
        const elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
        if (state.mode === "stopwatch") {
            state.remainingSeconds = state.baseSeconds + elapsed;
            return;
        }
        state.remainingSeconds = state.baseSeconds - elapsed;
        if (state.remainingSeconds <= 0) {
            if (state.phase === "focus" && state.breakMinutes > 0) {
                state.phase = "break";
                state.baseSeconds = state.breakMinutes * 60;
                state.remainingSeconds = state.baseSeconds;
                state.startedAt = Date.now();
                feedback.textContent = "Focus complete. Break phase started.";
            } else {
                state.running = false;
                state.remainingSeconds = 0;
                feedback.textContent = "Timer finished. You can complete the session now.";
            }
        }
    }

    function applyMode(mode, focusMinutes, breakMinutes) {
        state = {
            mode,
            focusMinutes: Number(focusMinutes),
            breakMinutes: Number(breakMinutes),
            phase: mode === "stopwatch" ? "open" : "focus",
            running: false,
            remainingSeconds: mode === "stopwatch" ? 0 : Number(focusMinutes) * 60,
            baseSeconds: mode === "stopwatch" ? 0 : Number(focusMinutes) * 60,
            startedAt: null,
        };
        feedback.textContent = "Timer updated.";
        syncView();
    }

    document.querySelectorAll(".timer-mode").forEach((button) => {
        button.addEventListener("click", () => applyMode(button.dataset.mode, button.dataset.focus, button.dataset.break));
    });

    startButton.addEventListener("click", () => {
        state.focusMinutes = Number(focusInput.value || 25);
        state.breakMinutes = Number(breakInput.value || 5);
        if (!state.running) {
            if (state.mode !== "stopwatch" && state.remainingSeconds === 0) {
                state.phase = "focus";
                state.remainingSeconds = state.focusMinutes * 60;
            }
            state.baseSeconds = state.remainingSeconds;
            state.startedAt = Date.now();
            state.running = true;
        }
        feedback.textContent = "Timer running.";
        syncView();
    });

    pauseButton.addEventListener("click", () => {
        recomputeRemaining();
        state.running = false;
        state.startedAt = null;
        state.baseSeconds = state.remainingSeconds;
        feedback.textContent = "Timer paused.";
        syncView();
    });

    resetButton.addEventListener("click", () => {
        applyMode(state.mode, focusInput.value || state.focusMinutes, breakInput.value || state.breakMinutes);
        feedback.textContent = "Timer reset.";
    });

    completeButton.addEventListener("click", async () => {
        const sessionId = sessionSelect.value;
        const duration = state.mode === "stopwatch"
            ? Math.max(1, Math.round(state.remainingSeconds / 60))
            : Math.max(1, Math.round(((state.focusMinutes * 60) - Math.max(state.remainingSeconds, 0)) / 60));
        if (!sessionId) {
            feedback.textContent = `Focus block complete. Estimated duration: ${duration} minutes.`;
            return;
        }
        const csrftoken = document.cookie.split("; ").find((row) => row.startsWith("csrftoken="))?.split("=")[1];
        const response = await window.fetch(window.resyncPage.completeUrlTemplate.replace("/0/", `/${sessionId}/`), {
            method: "POST",
            credentials: "same-origin",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrftoken},
            body: JSON.stringify({actual_duration_minutes: duration}),
        });
        if (response.ok) {
            const data = await response.json();
            feedback.textContent = `${data.motivation} Streak: ${data.streak_days} day(s).`;
            applyMode(state.mode, focusInput.value || state.focusMinutes, breakInput.value || state.breakMinutes);
        } else {
            feedback.textContent = "Session completion could not be saved.";
        }
    });

    if (state.running && !state.startedAt) {
        state.startedAt = Date.now();
    }
    syncView();
    window.setInterval(() => {
        recomputeRemaining();
        syncView();
    }, 1000);
}

function mountTimetable() {
    const form = document.querySelector("#ai-timetable-form");
    if (!form) return;

    const feedback = document.querySelector("#ai-timetable-feedback");
    const preview = document.querySelector("#ai-timetable-preview");
    const assumptions = document.querySelector("#ai-assumptions");
    const entries = document.querySelector("#ai-draft-entries");
    const model = document.querySelector("#ai-timetable-model");
    const acceptButton = document.querySelector("#accept-ai-draft");
    let currentDraft = null;

    function getCsrfToken() {
        return document.cookie.split("; ").find((row) => row.startsWith("csrftoken="))?.split("=")[1];
    }

    function renderDraft(draft) {
        assumptions.innerHTML = "";
        entries.innerHTML = "";
        draft.assumptions.forEach((item) => {
            const li = document.createElement("li");
            li.textContent = item;
            assumptions.appendChild(li);
        });
        draft.entries.forEach((entry) => {
            const card = document.createElement("div");
            card.className = "rounded-3xl border border-sand-200 bg-sand-100 p-4";
            card.innerHTML = `
                <p class="font-semibold">${entry.title}</p>
                <p class="mt-1 text-sm text-stone-500">Day ${entry.day_of_week + 1} • ${entry.start_time} - ${entry.end_time}</p>
                <p class="mt-1 text-sm text-stone-600">${entry.subject_name || "General"} • ${entry.entry_type}</p>
            `;
            entries.appendChild(card);
        });
        model.textContent = `Generated with ${draft.model}`;
        preview.classList.remove("hidden");
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        feedback.textContent = "Generating timetable draft...";
        const payload = Object.fromEntries(new FormData(form).entries());
        const response = await window.fetch(window.resyncPage.draftUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {"Content-Type": "application/json", "X-CSRFToken": getCsrfToken()},
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
            feedback.textContent = data.detail || "The AI draft could not be generated.";
            return;
        }
        currentDraft = data;
        renderDraft(data);
        feedback.textContent = "Draft ready. Review it before saving.";
    });

    acceptButton?.addEventListener("click", async () => {
        if (!currentDraft) return;
        feedback.textContent = "Saving accepted AI timetable...";
        const response = await window.fetch(window.resyncPage.acceptUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {"Content-Type": "application/json", "X-CSRFToken": getCsrfToken()},
            body: JSON.stringify({entries: currentDraft.entries}),
        });
        const data = await response.json();
        if (!response.ok) {
            feedback.textContent = data.detail || "The AI draft could not be saved.";
            return;
        }
        feedback.textContent = `${data.created} timetable block(s) created. Refreshing...`;
        window.setTimeout(() => window.location.reload(), 700);
    });
}

window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstallPrompt = event;
    document.querySelector("#install-app")?.classList.remove("hidden");
});

window.addEventListener("DOMContentLoaded", () => {
    if (window.resyncPage?.name === "dashboard") mountDashboard();
    if (window.resyncPage?.name === "timer") mountTimer();
    if (window.resyncPage?.name === "timetable") mountTimetable();

    document.querySelector("#install-app")?.addEventListener("click", async () => {
        if (!deferredInstallPrompt) return;
        deferredInstallPrompt.prompt();
        await deferredInstallPrompt.userChoice;
        deferredInstallPrompt = null;
        document.querySelector("#install-app")?.classList.add("hidden");
    });

    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/static/service-worker.js").catch(() => null);
    }
});
