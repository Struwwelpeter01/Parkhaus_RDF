document.addEventListener("DOMContentLoaded", function () {
    const kennzeichenInput = document.getElementById("kennzeichen-input");
    const btnHinzufuegen = document.getElementById("btn-hinzufuegen");
    const btnDauerparker = document.getElementById("btn-dauerparker");
    const btnNotfallAusfahrt = document.getElementById("btn-notfall-ausfahrt");
    const aktiveParkvorgaenge = document.getElementById("aktive-parkvorgaenge");
    const fahrzeugPagination = document.getElementById("fahrzeug-pagination");
    const dauerparkerList = document.getElementById("dauerparker-list");
    const parkhausCounter = document.getElementById("parkhaus-counter");
    const kameraStatus = document.getElementById("kamera-status");
    const kameraKennzeichen = document.getElementById("kamera-kennzeichen");
    const kameraStatusAusfahrt = document.getElementById("kamera-status-ausfahrt");
    const kameraKennzeichenAusfahrt = document.getElementById("kamera-kennzeichen-ausfahrt");
    const currentDate = document.getElementById("current-date");
    const currentTime = document.getElementById("current-time");
    const gateEntryStatus = document.getElementById("gate-entry-status");
    const gateExitStatus = document.getElementById("gate-exit-status");
    const toast = document.getElementById("toast");

    const MAX_PARKPLAETZE = 15;
    const PAGE_SIZE = 6;
    const PAYMENT_WINDOW_MINUTES = 10;
    const AUTO_ENTRY_MIN_HITS = 3;
    const AUTO_EXIT_MIN_HITS = 3;

    let parkhausBelegt = 0;
    let aktiveVorgaenge = [];
    let currentPage = 1;
    let lastCameraPlate = "";
    let ignoredCameraPlate = "";
    let cameraFilledInput = false;
    let lastExitAttemptPlate = "";
    let lastExitAttemptAt = 0;
    let entryCandidate = { plate: "", hits: 0 };
    let exitCandidate = { plate: "", hits: 0 };
    let lastAutoEntryPlate = "";
    let lastAutoEntryAt = 0;
    let dauerparker = [];
    const gates = {
        entry: { open: false, timer: null, blockedPlate: "" },
        exit: { open: false, timer: null, blockedPlate: "" },
    };

    function normalizeKennzeichen(value) {
        return value.trim().toUpperCase().replace(/-/g, " ").replace(/\s+/g, " ");
    }

    function validateKennzeichen(kennzeichen) {
        return /^[A-Z] [0-9]{4}$/.test(normalizeKennzeichen(kennzeichen));
    }

    function routePlate(kennzeichen) {
        return encodeURIComponent(normalizeKennzeichen(kennzeichen));
    }

    function showToast(message, type = "info") {
        toast.textContent = message;
        toast.className = `toast show ${type}`;
        window.clearTimeout(showToast.timer);
        showToast.timer = window.setTimeout(() => {
            toast.className = "toast";
        }, 4200);
    }

    function updateClock() {
        const now = new Date();
        currentDate.textContent = now.toLocaleDateString("de-DE", {
            weekday: "short",
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
        currentTime.textContent = now.toLocaleTimeString("de-DE");
    }

    function updateParkhausStatus() {
        parkhausCounter.textContent = `${parkhausBelegt} / ${MAX_PARKPLAETZE}`;
        parkhausCounter.classList.toggle("full", parkhausBelegt >= MAX_PARKPLAETZE);
    }

    function setGate(gateName, open, reason = "") {
        const gate = gates[gateName];
        const statusElement = gateName === "entry" ? gateEntryStatus : gateExitStatus;
        const changed = gate.open !== open;
        gate.open = open;
        statusElement.textContent = open ? "Schranke offen" : "Schranke zu";
        statusElement.classList.toggle("open", open);
        statusElement.title = reason;

        if (gate.timer) {
            window.clearTimeout(gate.timer);
            gate.timer = null;
        }

        if (open) {
            gate.timer = window.setTimeout(() => {
                setGate(gateName, false, "15 Sekunden Fallback");
            }, 15000);
        } else {
            gate.blockedPlate = "";
            if (gateName === "entry") {
                entryCandidate = { plate: "", hits: 0 };
            } else {
                exitCandidate = { plate: "", hits: 0 };
            }
        }

        if (changed) {
            triggerGateHardware(gateName, open ? "open" : "close");
        }
    }

    async function triggerGateHardware(gateName, action) {
        try {
            await fetch(`/api/schranke/${gateName}/${action}`, { method: "POST" });
        } catch (error) {
            console.error("Fehler beim Schalten der Schranke:", error);
        }
    }

    function closeGateOnLine(gateName, result) {
        if (result.line_blocked && gates[gateName].open) {
            setGate(gateName, false, "Rote Linie beruehrt");
        }
    }

    function handleGateOpenRecognition(gateName, plate, target, direction) {
        const gate = gates[gateName];
        if (!gate.open || !validateKennzeichen(plate)) {
            return false;
        }

        target.textContent = `${direction} gesperrt bis Schranke zu`;
        target.className = "error";

        if (gate.blockedPlate !== plate) {
            gate.blockedPlate = plate;
            showToast(`${direction} gesperrt: Schranke ist noch offen.`, "error");
        }

        if (gateName === "entry") {
            entryCandidate = { plate: "", hits: 0 };
        } else {
            exitCandidate = { plate: "", hits: 0 };
        }
        return true;
    }

    function displayPlateState(target, plate, result) {
        const normalized = normalizeKennzeichen(plate || "");
        const ocrRaw = (result.ocr_raw || "").trim();

        if (normalized && /^[A-Z] [0-9]{4}$/.test(normalized)) {
            target.textContent = `Erkannt: ${normalized}`;
            target.className = "ok";
        } else if (normalized === "ERKANNT") {
            target.textContent = "Kennzeichen erkannt, OCR liest...";
            target.className = "warn";
        } else if (result.status && result.status.includes("warte auf Stillstand")) {
            target.textContent = "Bitte kurz stillhalten";
            target.className = "warn";
        } else if (ocrRaw) {
            target.textContent = `OCR: ${ocrRaw}`;
            target.className = "warn";
        } else if (result.status && result.status.includes("nicht erkannt")) {
            target.textContent = "Nicht erkannt";
            target.className = "error";
        } else {
            target.textContent = "Erkannt: -";
            target.className = "";
        }
    }

    async function loadKameraKennzeichen() {
        try {
            const response = await fetch("/api/kamera/kennzeichen");
            const result = await response.json();
            const plate = normalizeKennzeichen(result.plate || "");

            kameraStatus.textContent = result.status || "Kamera aktiv";
            displayPlateState(kameraKennzeichen, plate, result);
            closeGateOnLine("entry", result);

            if (handleGateOpenRecognition("entry", plate, kameraKennzeichen, "Einfahrt")) {
                return;
            }

            if (!plate || plate === ignoredCameraPlate || plate === "ERKANNT") {
                return;
            }

            if (!validateKennzeichen(plate)) {
                return;
            }

            lastCameraPlate = plate;
            kennzeichenInput.value = plate;
            cameraFilledInput = true;
            await maybeAutoEntry(plate);
        } catch (error) {
            console.error("Fehler beim Laden des Einfahrt-Kennzeichens:", error);
        }
    }

    async function maybeAutoEntry(plate) {
        if (entryCandidate.plate === plate) {
            entryCandidate.hits += 1;
        } else {
            entryCandidate = { plate, hits: 1 };
        }

        const now = Date.now();
        if (entryCandidate.hits < AUTO_ENTRY_MIN_HITS) {
            return;
        }
        if (plate === lastAutoEntryPlate && now - lastAutoEntryAt < 15000) {
            return;
        }

        lastAutoEntryPlate = plate;
        lastAutoEntryAt = now;
        await starteParkvorgang("normal", plate, true);
    }

    async function loadAusfahrtKameraKennzeichen() {
        try {
            const response = await fetch("/api/kamera/kennzeichen/ausfahrt");
            const result = await response.json();
            const plate = normalizeKennzeichen(result.plate || "");

            kameraStatusAusfahrt.textContent = result.status || "Kamera aktiv";
            displayPlateState(kameraKennzeichenAusfahrt, plate, result);
            closeGateOnLine("exit", result);

            if (handleGateOpenRecognition("exit", plate, kameraKennzeichenAusfahrt, "Ausfahrt")) {
                return;
            }

            if (!validateKennzeichen(plate)) {
                return;
            }

            if (exitCandidate.plate === plate) {
                exitCandidate.hits += 1;
            } else {
                exitCandidate = { plate, hits: 1 };
            }

            const now = Date.now();
            if (exitCandidate.hits < AUTO_EXIT_MIN_HITS || (plate === lastExitAttemptPlate && now - lastExitAttemptAt < 8000)) {
                return;
            }

            lastExitAttemptPlate = plate;
            lastExitAttemptAt = now;
            await pruefeAusfahrt(plate);
        } catch (error) {
            console.error("Fehler beim Laden des Ausfahrt-Kennzeichens:", error);
        }
    }

    async function loadData() {
        await loadAktiveParkvorgaenge();
        await loadDauerparker();
        updateParkhausStatus();
    }

    async function loadAktiveParkvorgaenge() {
        try {
            const response = await fetch("/api/parkvorgaenge/aktiv");
            const vorgaenge = await response.json();

            aktiveVorgaenge = vorgaenge;
            parkhausBelegt = aktiveVorgaenge.length;

            const pageCount = Math.max(1, Math.ceil(aktiveVorgaenge.length / PAGE_SIZE));
            currentPage = Math.min(currentPage, pageCount);

            renderAktiveFahrzeuge();
            renderPagination(pageCount);
        } catch (error) {
            console.error("Fehler beim Laden der Parkvorgaenge:", error);
        }
    }

    async function loadDauerparker() {
        try {
            const response = await fetch("/api/dauerparker");
            dauerparker = await response.json();
            renderDauerparker();
        } catch (error) {
            console.error("Fehler beim Laden der Dauerparker:", error);
        }
    }

    function renderDauerparker() {
        if (!dauerparker.length) {
            dauerparkerList.innerHTML = '<div class="no-data">Keine Dauerparker gebucht</div>';
            return;
        }

        dauerparkerList.innerHTML = dauerparker.map(item => `
            <div class="dauerparker-row">
                <strong>${escapeHtml(item.kennzeichen)}</strong>
                <span>gebucht</span>
                <button class="btn btn-danger btn-small dauerparker-delete" type="button" data-plate="${escapeHtml(item.kennzeichen)}">Entfernen</button>
            </div>
        `).join("");
    }

    function renderAktiveFahrzeuge() {
        if (aktiveVorgaenge.length === 0) {
            aktiveParkvorgaenge.innerHTML = '<div class="no-data">Keine Fahrzeuge im Parkhaus</div>';
            return;
        }

        const start = (currentPage - 1) * PAGE_SIZE;
        const pageItems = aktiveVorgaenge.slice(start, start + PAGE_SIZE);

        aktiveParkvorgaenge.innerHTML = pageItems.map(v => {
            const isPermanent = v.fahrzeug_typ === "dauerparker";
            const statusText = isPermanent ? "Dauerparker" : "Normal";
            const paidUntil = v.bezahlt_bis ? new Date(v.bezahlt_bis) : null;
            const secondsLeft = paidUntil ? Math.max(0, Math.floor((paidUntil - new Date()) / 1000)) : 0;
            const paidText = isPermanent
                ? "Festpreis EUR 365"
                : v.bezahlt
                    ? `bezahlt (${Math.ceil(secondsLeft / 60)} Min)`
                    : "offen";

            return `
                <div class="parkvorgang-card ${v.ausfahrt_blockiert ? "blocked" : ""}">
                    <h3>${escapeHtml(v.kennzeichen)}</h3>
                    <div class="parkvorgang-info">
                        <div><strong>Status</strong>${statusText}</div>
                        <div><strong>Einfahrt</strong>${formatTime(v.einfahrt_zeit)}</div>
                        <div><strong>Dauer</strong>${v.dauer_minuten} Min</div>
                        <div><strong>Preis</strong>EUR ${Number(v.kosten).toFixed(2)}</div>
                    </div>
                    <label class="paid-check">
                        <input type="checkbox" class="bezahlt-checkbox" data-id="${v.id}" ${v.bezahlt ? "checked" : ""} ${isPermanent ? "disabled" : ""}>
                        <span>${paidText}</span>
                    </label>
                </div>
            `;
        }).join("");
    }

    function renderPagination(pageCount) {
        if (pageCount <= 1) {
            fahrzeugPagination.innerHTML = "";
            return;
        }

        fahrzeugPagination.innerHTML = Array.from({ length: pageCount }, (_, index) => {
            const page = index + 1;
            const activeClass = page === currentPage ? " active" : "";
            return `<button class="page-btn${activeClass}" type="button" data-page="${page}">${page}</button>`;
        }).join("");
    }

    async function starteParkvorgang(fahrzeugTyp, erkanntesKennzeichen = "", automatisch = false) {
        const kennzeichen = normalizeKennzeichen(erkanntesKennzeichen || kennzeichenInput.value);

        if (gates.entry.open) {
            showToast("Einfahrt gesperrt: Schranke ist noch offen.", "error");
            return;
        }

        if (!kennzeichen) {
            showToast("Bitte Kennzeichen eingeben.", "error");
            return;
        }

        if (!validateKennzeichen(kennzeichen)) {
            showToast('Ungueltiges Format. Beispiel: "A 1234"', "error");
            return;
        }

        try {
            const response = await fetch(`/api/parkvorgang/start/${routePlate(kennzeichen)}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ fahrzeug_typ: fahrzeugTyp }),
            });
            const result = await response.json();

            if (response.ok) {
                ignoredCameraPlate = kennzeichen;
                lastCameraPlate = kennzeichen;
                cameraFilledInput = false;
                if (!automatisch) {
                    kennzeichenInput.value = "";
                }
                setGate("entry", true, "Einfahrt erlaubt");
                showToast(automatisch ? `${kennzeichen}: automatisch eingefahren.` : "Notfall-Einfahrt eingetragen.", "success");
                await loadData();
            } else {
                showToast(result.error || "Einfahrt abgelehnt.", "error");
            }
        } catch (error) {
            console.error("Fehler bei Einfahrt:", error);
            showToast("Netzwerkfehler bei der Einfahrt.", "error");
        }
    }

    async function bucheDauerparker() {
        const kennzeichen = normalizeKennzeichen(kennzeichenInput.value);

        if (!kennzeichen) {
            showToast("Bitte Kennzeichen fuer Dauerparker eingeben.", "error");
            return;
        }

        if (!validateKennzeichen(kennzeichen)) {
            showToast('Ungueltiges Format. Beispiel: "A 1234"', "error");
            return;
        }

        try {
            const response = await fetch("/api/dauerparker", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ kennzeichen }),
            });
            const result = await response.json();

            if (response.ok) {
                kennzeichenInput.value = "";
                showToast(`${result.kennzeichen}: Dauerparker gebucht.`, "success");
                await loadData();
            } else {
                showToast(result.error || "Dauerparker konnte nicht gebucht werden.", "error");
            }
        } catch (error) {
            console.error("Fehler beim Buchen des Dauerparkers:", error);
            showToast("Netzwerkfehler beim Dauerparker.", "error");
        }
    }

    async function entferneDauerparker(kennzeichen) {
        try {
            const response = await fetch(`/api/dauerparker/${routePlate(kennzeichen)}`, { method: "DELETE" });
            const result = await response.json();

            if (response.ok) {
                showToast(`${result.kennzeichen}: Dauerparker entfernt.`, "success");
                await loadData();
            } else {
                showToast(result.error || "Dauerparker konnte nicht entfernt werden.", "error");
            }
        } catch (error) {
            console.error("Fehler beim Entfernen des Dauerparkers:", error);
            showToast("Netzwerkfehler beim Entfernen des Dauerparkers.", "error");
        }
    }

    async function pruefeAusfahrt(kennzeichen) {
        if (gates.exit.open) {
            showToast("Ausfahrt gesperrt: Schranke ist noch offen.", "error");
            return;
        }

        try {
            const response = await fetch(`/api/parkvorgang/end/${routePlate(kennzeichen)}`, { method: "POST" });
            const result = await response.json();

            if (response.ok) {
                setGate("exit", true, "Ausfahrt erlaubt");
                showToast(`${kennzeichen}: Ausfahrt erlaubt.`, "success");
                await loadData();
                return;
            }

            showToast(result.error || "Ausfahrt abgelehnt.", "error");
            await loadData();
        } catch (error) {
            console.error("Fehler bei Ausfahrt:", error);
            showToast("Netzwerkfehler bei der Ausfahrt.", "error");
        }
    }

    async function notfallAusfahrt() {
        const kennzeichen = normalizeKennzeichen(kennzeichenInput.value);

        if (!kennzeichen) {
            showToast("Bitte Kennzeichen fuer die Notfall-Ausfahrt eingeben.", "error");
            return;
        }

        if (!validateKennzeichen(kennzeichen)) {
            showToast('Ungueltiges Format. Beispiel: "A 1234"', "error");
            return;
        }

        try {
            const response = await fetch(`/api/parkvorgang/notfall-ausfahrt/${routePlate(kennzeichen)}`, { method: "POST" });
            const result = await response.json();

            if (response.ok) {
                kennzeichenInput.value = "";
                setGate("exit", true, "Notfall-Ausfahrt");
                showToast(`${kennzeichen}: Notfall-Ausfahrt ausgeloest.`, "success");
                await loadData();
            } else {
                showToast(result.error || "Notfall-Ausfahrt abgelehnt.", "error");
            }
        } catch (error) {
            console.error("Fehler bei Notfall-Ausfahrt:", error);
            showToast("Netzwerkfehler bei der Notfall-Ausfahrt.", "error");
        }
    }

    async function setBezahlt(id, bezahlt) {
        try {
            const response = await fetch(`/api/parkvorgang/${id}/bezahlt`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ bezahlt }),
            });
            const result = await response.json();
            if (!response.ok) {
                showToast(result.error || "Bezahlstatus konnte nicht gesetzt werden.", "error");
            } else if (bezahlt) {
                showToast(`Bezahlt markiert. Ausfahrt innerhalb von ${PAYMENT_WINDOW_MINUTES} Minuten.`, "success");
            }
            await loadData();
        } catch (error) {
            console.error("Fehler beim Setzen des Bezahlstatus:", error);
            showToast("Netzwerkfehler beim Bezahlstatus.", "error");
        }
    }

    function formatTime(value) {
        return new Date(value).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    }

    function formatDateTime(value) {
        return new Date(value).toLocaleString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    btnHinzufuegen.addEventListener("click", () => starteParkvorgang("normal"));
    btnDauerparker.addEventListener("click", bucheDauerparker);
    btnNotfallAusfahrt.addEventListener("click", notfallAusfahrt);

    dauerparkerList.addEventListener("click", event => {
        const button = event.target.closest(".dauerparker-delete");
        if (!button) {
            return;
        }
        entferneDauerparker(button.dataset.plate);
    });

    kennzeichenInput.addEventListener("keypress", event => {
        if (event.key === "Enter") {
            btnHinzufuegen.click();
        }
    });

    kennzeichenInput.addEventListener("input", () => {
        const value = normalizeKennzeichen(kennzeichenInput.value);
        if (cameraFilledInput && !value && lastCameraPlate) {
            ignoredCameraPlate = lastCameraPlate;
            cameraFilledInput = false;
        }
        if (value && value !== lastCameraPlate) {
            ignoredCameraPlate = "";
            cameraFilledInput = false;
        }
    });

    aktiveParkvorgaenge.addEventListener("change", event => {
        const checkbox = event.target.closest(".bezahlt-checkbox");
        if (!checkbox) {
            return;
        }
        setBezahlt(Number(checkbox.dataset.id), checkbox.checked);
    });

    fahrzeugPagination.addEventListener("click", event => {
        const button = event.target.closest(".page-btn");
        if (!button) {
            return;
        }

        currentPage = Number(button.dataset.page);
        renderAktiveFahrzeuge();
        renderPagination(Math.max(1, Math.ceil(aktiveVorgaenge.length / PAGE_SIZE)));
    });

    updateClock();
    loadData();
    loadKameraKennzeichen();
    loadAusfahrtKameraKennzeichen();
    setInterval(updateClock, 1000);
    setInterval(loadData, 5000);
    setInterval(renderAktiveFahrzeuge, 1000);
    setInterval(loadKameraKennzeichen, 300);
    setInterval(loadAusfahrtKameraKennzeichen, 450);
});
