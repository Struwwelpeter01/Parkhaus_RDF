document.addEventListener("DOMContentLoaded", function () {
    const kennzeichenInput = document.getElementById("kennzeichen-input");
    const btnHinzufuegen = document.getElementById("btn-hinzufuegen");
    const aktiveParkvorgaenge = document.getElementById("aktive-parkvorgaenge");
    const fahrzeugPagination = document.getElementById("fahrzeug-pagination");
    const parkingLot = document.getElementById("parking-lot");
    const parkhausCounter = document.getElementById("parkhaus-counter");
    const ampelParkhaus = document.getElementById("ampel-parkhaus");
    const ampelEinfahrt = document.getElementById("ampel-einfahrt");
    const ampelAusfahrt = document.getElementById("ampel-ausfahrt");
    const statusEinfahrt = document.getElementById("status-einfahrt");
    const statusAusfahrt = document.getElementById("status-ausfahrt");
    const kostenModal = document.getElementById("kosten-modal");
    const kostenDetails = document.getElementById("kosten-details");
    const btnBezahlen = document.getElementById("btn-bezahlen");
    const btnModalClose = document.getElementById("btn-modal-close");

    const MAX_PARKPLAETZE = 15;
    const PAGE_SIZE = 5;
    const PARKPLATZ_STORAGE_KEY = "parkhaus_platz_belegung";

    let parkhausBelegt = 0;
    let aktiveVorgaenge = [];
    let currentPage = 1;
    let pendingAusfahrtKennzeichen = null;

    function ladePlatzBelegung() {
        try {
            return JSON.parse(localStorage.getItem(PARKPLATZ_STORAGE_KEY)) || {};
        } catch (error) {
            return {};
        }
    }

    function speicherePlatzBelegung(belegung) {
        localStorage.setItem(PARKPLATZ_STORAGE_KEY, JSON.stringify(belegung));
    }

    function freiePlaetze(belegung) {
        const belegtePlaetze = new Set(Object.values(belegung));
        return Array.from({ length: MAX_PARKPLAETZE }, (_, index) => index + 1)
            .filter(platz => !belegtePlaetze.has(platz));
    }

    function synchronisiereParkplaetze(vorgaenge) {
        const belegung = ladePlatzBelegung();
        const aktiveIds = new Set(vorgaenge.map(v => String(v.id)));

        Object.keys(belegung).forEach(id => {
            if (!aktiveIds.has(id)) {
                delete belegung[id];
            }
        });

        vorgaenge.forEach(vorgang => {
            const id = String(vorgang.id);
            if (!belegung[id]) {
                const frei = freiePlaetze(belegung);
                if (frei.length > 0) {
                    belegung[id] = frei[Math.floor(Math.random() * frei.length)];
                }
            }
        });

        speicherePlatzBelegung(belegung);
        return belegung;
    }

    function updateParkhausStatus() {
        parkhausCounter.textContent = `${parkhausBelegt} / ${MAX_PARKPLAETZE}`;

        const parkhausGruen = ampelParkhaus.querySelector(".gruen");
        const parkhausRot = ampelParkhaus.querySelector(".rot");

        if (parkhausBelegt >= MAX_PARKPLAETZE) {
            parkhausGruen.classList.remove("aktiv");
            parkhausRot.classList.add("aktiv");
        } else {
            parkhausGruen.classList.add("aktiv");
            parkhausRot.classList.remove("aktiv");
        }
    }

    function updateSchrankenAnzeige() {
        aktualisiereSchrankenText(ampelEinfahrt, statusEinfahrt);
        aktualisiereSchrankenText(ampelAusfahrt, statusAusfahrt);
    }

    function aktualisiereSchrankenText(ampel, statusElement) {
        const offen = ampel.querySelector(".gruen").classList.contains("aktiv");

        statusElement.textContent = offen ? "Schranke offen" : "Schranke geschlossen";
        statusElement.style.background = offen ? "#d4edda" : "#ffffff";
        statusElement.style.color = offen ? "#155724" : "#2c3e50";
    }

    function setAmpelState(ampel, isOpen) {
        const gruen = ampel.querySelector(".gruen");
        const rot = ampel.querySelector(".rot");

        gruen.classList.toggle("aktiv", isOpen);
        rot.classList.toggle("aktiv", !isOpen);
    }

    function oeffneSchranke(schrankeAmpel) {
        setAmpelState(schrankeAmpel, true);
        updateSchrankenAnzeige();

        setTimeout(() => {
            setAmpelState(schrankeAmpel, false);
            updateSchrankenAnzeige();
        }, 5000);
    }

    function validateKennzeichen(kennzeichen) {
        return /^[A-Z]{1,2}-[0-9]{4}$/.test(kennzeichen.toUpperCase());
    }

    async function loadData() {
        await loadAktiveParkvorgaenge();
        updateParkhausStatus();
        updateSchrankenAnzeige();
    }

    async function loadAktiveParkvorgaenge() {
        try {
            const response = await fetch("/api/parkvorgaenge/aktiv");
            const vorgaenge = await response.json();
            const belegung = synchronisiereParkplaetze(vorgaenge);

            aktiveVorgaenge = vorgaenge.map(vorgang => ({
                ...vorgang,
                parkplatz: belegung[String(vorgang.id)]
            }));
            parkhausBelegt = aktiveVorgaenge.length;

            const pageCount = Math.max(1, Math.ceil(aktiveVorgaenge.length / PAGE_SIZE));
            currentPage = Math.min(currentPage, pageCount);

            renderAktiveFahrzeuge();
            renderPagination(pageCount);
            renderParkplaetze(belegung);
        } catch (error) {
            console.error("Fehler beim Laden der Parkvorgaenge:", error);
        }
    }

    function renderAktiveFahrzeuge() {
        if (aktiveVorgaenge.length === 0) {
            aktiveParkvorgaenge.innerHTML = '<div class="no-data">Keine Fahrzeuge im Parkhaus</div>';
            return;
        }

        const start = (currentPage - 1) * PAGE_SIZE;
        const pageItems = aktiveVorgaenge.slice(start, start + PAGE_SIZE);

        aktiveParkvorgaenge.innerHTML = pageItems.map(v => `
            <div class="parkvorgang-card">
                <h4>${v.kennzeichen}</h4>
                <div class="parkvorgang-info">
                    <div><strong>Einfahrt</strong>${new Date(v.einfahrt_zeit).toLocaleTimeString("de-DE")}</div>
                    <div><strong>Dauer</strong>${v.dauer_minuten} Min</div>
                    <div><strong>Preis</strong>EUR ${v.kosten.toFixed(2)}</div>
                    <div><strong>Platz</strong>${v.parkplatz || "-"}</div>
                </div>
                <button class="btn btn-primary btn-ausfahrt" data-kennzeichen="${v.kennzeichen}">Ausfahrt</button>
            </div>
        `).join("");
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

    function renderParkplaetze(belegung) {
        const platzNachId = Object.entries(belegung).reduce((result, [id, platz]) => {
            result[platz] = id;
            return result;
        }, {});

        parkingLot.innerHTML = Array.from({ length: MAX_PARKPLAETZE }, (_, index) => {
            const platz = index + 1;
            const occupied = Boolean(platzNachId[platz]);
            return `
                <div class="parking-space${occupied ? " occupied" : ""}">
                    <span class="space-number">${platz}</span>
                    <span class="space-led" title="${occupied ? "Belegt" : "Frei"}"></span>
                </div>
            `;
        }).join("");
    }

    function handleAusfahrt(kennzeichen) {
        const vorgang = aktiveVorgaenge.find(v => v.kennzeichen === kennzeichen);
        if (!vorgang) {
            alert("Dieses Fahrzeug ist nicht mehr in der aktiven Liste.");
            loadData();
            return;
        }

        pendingAusfahrtKennzeichen = kennzeichen;
        showKostenModal(vorgang.kosten, vorgang.dauer_minuten);
    }

    function showKostenModal(kosten, dauerMinuten) {
        kostenDetails.innerHTML = `
            <div class="kosten-breakdown">
                <div>Grundgebuehr: EUR 2.00</div>
                <div>Dauer: ${dauerMinuten} Minuten</div>
                <div>Zusatzkosten: EUR ${(kosten - 2.0).toFixed(2)}</div>
                <div class="kosten-gesamt">Gesamt: EUR ${kosten.toFixed(2)}</div>
            </div>
        `;
        kostenModal.style.display = "block";
    }

    btnHinzufuegen.addEventListener("click", async () => {
        const kennzeichen = kennzeichenInput.value.trim().toUpperCase();

        if (!kennzeichen) {
            alert("Bitte geben Sie ein Kennzeichen ein.");
            return;
        }

        if (!validateKennzeichen(kennzeichen)) {
            alert('Ungueltiges Format! Verwenden Sie z.B. "AB-1234"');
            return;
        }

        if (parkhausBelegt >= MAX_PARKPLAETZE) {
            alert("Parkhaus ist voll! Keine Einfahrt moeglich.");
            return;
        }

        try {
            const response = await fetch(`/api/parkvorgang/start/${kennzeichen}`, { method: "POST" });
            const result = await response.json();

            if (response.ok) {
                kennzeichenInput.value = "";
                oeffneSchranke(ampelEinfahrt);
                await loadData();
            } else {
                alert("Fehler: " + result.error);
            }
        } catch (error) {
            console.error("Fehler bei Hinzufuegung:", error);
            alert("Netzwerkfehler");
        }
    });

    kennzeichenInput.addEventListener("keypress", event => {
        if (event.key === "Enter") {
            btnHinzufuegen.click();
        }
    });

    aktiveParkvorgaenge.addEventListener("click", event => {
        const button = event.target.closest(".btn-ausfahrt");
        if (button) {
            handleAusfahrt(button.dataset.kennzeichen);
        }
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

    btnBezahlen.addEventListener("click", async () => {
        if (!pendingAusfahrtKennzeichen) {
            kostenModal.style.display = "none";
            return;
        }

        try {
            const response = await fetch(`/api/parkvorgang/end/${pendingAusfahrtKennzeichen}`, { method: "POST" });
            const result = await response.json();

            if (response.ok) {
                kostenModal.style.display = "none";
                pendingAusfahrtKennzeichen = null;
                oeffneSchranke(ampelAusfahrt);
                await loadData();
            } else {
                alert("Fehler: " + result.error);
            }
        } catch (error) {
            console.error("Fehler bei Ausfahrt:", error);
            alert("Netzwerkfehler");
        }
    });

    btnModalClose.addEventListener("click", () => {
        kostenModal.style.display = "none";
        pendingAusfahrtKennzeichen = null;
    });

    const demoBtn = document.createElement("button");
    demoBtn.textContent = "Demo: Zufallskennzeichen";
    demoBtn.className = "btn btn-secondary";
    demoBtn.style.marginTop = "10px";
    demoBtn.addEventListener("click", () => {
        const buchstaben = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
        const prefix = buchstaben[Math.floor(Math.random() * buchstaben.length)] +
            buchstaben[Math.floor(Math.random() * buchstaben.length)];
        const nummer = String(Math.floor(Math.random() * 9000) + 1000);
        kennzeichenInput.value = `${prefix}-${nummer}`;
    });
    document.querySelector(".kennzeichen-input-section").appendChild(demoBtn);

    loadData();
    setInterval(loadData, 5000);
});
