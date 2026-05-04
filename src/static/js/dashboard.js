document.addEventListener('DOMContentLoaded', function() {
    const kennzeichenInput = document.getElementById('kennzeichen-input');
    const btnHinzufuegen = document.getElementById('btn-hinzufuegen');
    const aktiveParkvorgaenge = document.getElementById('aktive-parkvorgaenge');
    const parkhausCounter = document.getElementById('parkhaus-counter');
    const ampelParkhaus = document.getElementById('ampel-parkhaus');
    const ampelEinfahrt = document.getElementById('ampel-einfahrt');
    const ampelAusfahrt = document.getElementById('ampel-ausfahrt');
    const statusEinfahrt = document.getElementById('status-einfahrt');
    const statusAusfahrt = document.getElementById('status-ausfahrt');

    let parkhausBelegt = 0;
    const MAX_PARKPLAETZE = 15;

    function updateParkhausStatus() {
        parkhausCounter.textContent = `${String(parkhausBelegt).padStart(2, '0')} / ${MAX_PARKPLAETZE}`;

        const parkhausGruen = ampelParkhaus.querySelector('.gruen');
        const parkhausRot = ampelParkhaus.querySelector('.rot');

        if (parkhausBelegt >= MAX_PARKPLAETZE) {
            parkhausGruen.classList.remove('aktiv');
            parkhausRot.classList.add('aktiv');
        } else {
            parkhausGruen.classList.add('aktiv');
            parkhausRot.classList.remove('aktiv');
        }
    }

    function updateSchrankenAnzeige() {
        if (ampelEinfahrt.querySelector('.gruen').classList.contains('aktiv')) {
            statusEinfahrt.textContent = 'Schranke offen';
            statusEinfahrt.style.background = '#d4edda';
            statusEinfahrt.style.color = '#155724';
        } else {
            statusEinfahrt.textContent = 'Schranke geschlossen';
            statusEinfahrt.style.background = '#f8f9fa';
            statusEinfahrt.style.color = '#333';
        }

        if (ampelAusfahrt.querySelector('.gruen').classList.contains('aktiv')) {
            statusAusfahrt.textContent = 'Schranke offen';
            statusAusfahrt.style.background = '#d4edda';
            statusAusfahrt.style.color = '#155724';
        } else {
            statusAusfahrt.textContent = 'Schranke geschlossen';
            statusAusfahrt.style.background = '#f8f9fa';
            statusAusfahrt.style.color = '#333';
        }
    }

    function setAmpelState(ampel, isOpen) {
        const gruen = ampel.querySelector('.gruen');
        const rot = ampel.querySelector('.rot');

        if (isOpen) {
            gruen.classList.add('aktiv');
            rot.classList.remove('aktiv');
        } else {
            gruen.classList.remove('aktiv');
            rot.classList.add('aktiv');
        }
    }

    async function loadData() {
        await loadAktiveParkvorgaenge();
        updateParkhausStatus();
        updateSchrankenAnzeige();
    }

    async function loadAktiveParkvorgaenge() {
        try {
            const response = await fetch('/api/parkvorgaenge/aktiv');
            const vorgaenge = await response.json();
            parkhausBelegt = vorgaenge.length;

            if (vorgaenge.length === 0) {
                aktiveParkvorgaenge.innerHTML = '<div class="no-data">Keine Fahrzeuge im Parkhaus</div>';
                return;
            }

            aktiveParkvorgaenge.innerHTML = vorgaenge.map(v => `
                <div class="parkvorgang-card">
                    <h4>${v.kennzeichen}</h4>
                    <div class="parkvorgang-info">
                        <div><span>Einfahrt:</span> <span>${new Date(v.einfahrt_zeit).toLocaleTimeString('de-DE')}</span></div>
                        <div><span>Dauer:</span> <span>${v.dauer_minuten} Min</span></div>
                        <div><span>Kosten:</span> <span class="kosten-display">€${v.kosten.toFixed(2)}</span></div>
                    </div>
                    <button class="btn btn-primary btn-ausfahrt" data-kennzeichen="${v.kennzeichen}">🚪 Ausfahrt</button>
                </div>
            `).join('');

            document.querySelectorAll('.btn-ausfahrt').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const kennzeichen = e.target.dataset.kennzeichen;
                    await handleAusfahrt(kennzeichen);
                });
            });
        } catch (error) {
            console.error('Fehler beim Laden der Parkvorgänge:', error);
        }
    }

    function validateKennzeichen(kennzeichen) {
        const pattern = /^[A-Z]{1,2}-[0-9]{4}$/;
        return pattern.test(kennzeichen.toUpperCase());
    }

    function oeffneSchranke(schrankeAmpel, statusElement) {
        setAmpelState(schrankeAmpel, true);
        updateSchrankenAnzeige();

        setTimeout(() => {
            setAmpelState(schrankeAmpel, false);
            updateSchrankenAnzeige();
        }, 5000);
    }

    btnHinzufuegen.addEventListener('click', async () => {
        const kennzeichen = kennzeichenInput.value.trim().toUpperCase();
        if (!kennzeichen) {
            alert('Bitte geben Sie ein Kennzeichen ein.');
            return;
        }
        if (!validateKennzeichen(kennzeichen)) {
            alert('Ungültiges Format! Verwenden Sie z.B. "AB-1234"');
            return;
        }
        if (parkhausBelegt >= MAX_PARKPLAETZE) {
            alert('Parkhaus ist voll! Keine Einfahrt möglich.');
            return;
        }

        try {
            const response = await fetch(`/api/parkvorgang/start/${kennzeichen}`, { method: 'POST' });
            const result = await response.json();

            if (response.ok) {
                kennzeichenInput.value = '';
                oeffneSchranke(ampelEinfahrt, statusEinfahrt);
                await loadData();
            } else {
                alert('❌ Fehler: ' + result.error);
            }
        } catch (error) {
            console.error('Fehler bei Hinzufügung:', error);
            alert('❌ Netzwerkfehler');
        }
    });

    kennzeichenInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            btnHinzufuegen.click();
        }
    });

    async function handleAusfahrt(kennzeichen) {
        try {
            const response = await fetch(`/api/parkvorgang/end/${kennzeichen}`, { method: 'POST' });
            const result = await response.json();

            if (response.ok) {
                oeffneSchranke(ampelAusfahrt, statusAusfahrt);
                await loadData();
            } else {
                alert('❌ Fehler: ' + result.error);
            }
        } catch (error) {
            console.error('Fehler bei Ausfahrt:', error);
            alert('❌ Netzwerkfehler');
        }
    }

    const demoBtn = document.createElement('button');
    demoBtn.textContent = '🎯 Demo: Zufälliges Kennzeichen einfügen';
    demoBtn.className = 'btn btn-secondary';
    demoBtn.style.marginTop = '10px';
    demoBtn.addEventListener('click', () => {
        const kennzeichen = ['AB-1234', 'CD-5678', 'EF-9012', 'GH-3456'][Math.floor(Math.random() * 4)];
        kennzeichenInput.value = kennzeichen;
    });
    document.querySelector('.kennzeichen-input-section').appendChild(demoBtn);

    loadData();
    setInterval(loadData, 5000);
});


    // Registrierte Fahrzeuge laden
    async function loadRegistrierteFahrzeuge() {
        try {
            const response = await fetch('/api/fahrzeuge');
            const fahrzeuge = await response.json();

            if (fahrzeuge.length === 0) {
                registrierteFahrzeuge.innerHTML = '<div class="no-data">Keine Fahrzeuge registriert</div>';
                return;
            }

            registrierteFahrzeuge.innerHTML = fahrzeuge.map(f => `
                <div class="fahrzeug-card">
                    <div>
                        <span class="kennzeichen">${f.kennzeichen}</span>
                        ${f.name ? `<span class="name"> - ${f.name}</span>` : ''}
                    </div>
                    <span class="status">${f.status}</span>
                </div>
            `).join('');
        } catch (error) {
            console.error('Fehler beim Laden der Fahrzeuge:', error);
        }
    }

    // Kennzeichen simulieren (für Demo)
    function simulateKennzeichen() {
        const kennzeichen = ['AB-CD 123', 'XY-ZW 456', 'MN-OP 789'][Math.floor(Math.random() * 3)];
        showKennzeichen(kennzeichen);
    }

    // Kennzeichen anzeigen
    function showKennzeichen(kennzeichen) {
        aktuellesKennzeichen = kennzeichen;
        kennzeichenDisplay.innerHTML = `
            <div class="kennzeichen-erkannt">
                ${kennzeichen}
            </div>
        `;

        // Buttons aktivieren
        btnEinfahrt.disabled = false;
        btnAusfahrt.disabled = false;

        // Timer starten (für Demo)
        startTimer();
    }

    // Timer für Kostenberechnung
    function startTimer() {
        if (timerInterval) clearInterval(timerInterval);

        const startTime = Date.now();
        timerInterval = setInterval(() => {
            const elapsed = Date.now() - startTime;
            const seconds = Math.floor(elapsed / 1000);
            const kosten = 2.0 + Math.floor(seconds / 20) * 1.0;

            // Live-Kosten-Update in der Anzeige
            const kennzeichenElement = kennzeichenDisplay.querySelector('.kennzeichen-erkannt');
            if (kennzeichenElement) {
                kennzeichenElement.innerHTML = `
                    ${aktuellesKennzeichen}<br>
                    <small>Dauer: ${Math.floor(seconds / 60)}:${(seconds % 60).toString().padStart(2, '0')} | Kosten: €${kosten.toFixed(2)}</small>
                `;
            }
        }, 1000);
    }

    // Einfahrt erlauben
    btnEinfahrt.addEventListener('click', async () => {
        if (!aktuellesKennzeichen) return;

        try {
            const response = await fetch(`/api/parkvorgang/start/${aktuellesKennzeichen}`, {
                method: 'POST'
            });
            const result = await response.json();

            if (response.ok) {
                alert('✅ Einfahrt erlaubt! Schranke öffnet sich.');
                resetKennzeichen();
                loadData();
            } else {
                alert('❌ Fehler: ' + result.error);
            }
        } catch (error) {
            console.error('Fehler bei Einfahrt:', error);
            alert('❌ Netzwerkfehler');
        }
    });

    // Ausfahrt bestätigen
    btnAusfahrt.addEventListener('click', async () => {
        if (!aktuellesKennzeichen) return;

        try {
            const response = await fetch(`/api/parkvorgang/end/${aktuellesKennzeichen}`, {
                method: 'POST'
            });
            const result = await response.json();

            if (response.ok) {
                showKostenModal(result.kosten, result.dauer_minuten);
            } else {
                alert('❌ Fehler: ' + result.error);
            }
        } catch (error) {
            console.error('Fehler bei Ausfahrt:', error);
            alert('❌ Netzwerkfehler');
        }
    });

    // Kosten-Modal anzeigen
    function showKostenModal(kosten, dauerMinuten) {
        kostenDetails.innerHTML = `
            <div class="kosten-breakdown">
                <div>Grundgebühr: €2.00</div>
                <div>Dauer: ${dauerMinuten} Minuten</div>
                <div>Zusatzkosten: €${(kosten - 2.0).toFixed(2)} (1€ pro 20 Sek)</div>
                <div class="kosten-gesamt">Gesamt: €${kosten.toFixed(2)}</div>
            </div>
        `;
        kostenModal.style.display = 'block';
    }

    // Bezahlung bestätigen
    btnBezahlen.addEventListener('click', () => {
        alert('✅ Bezahlung bestätigt! Schranke öffnet sich.');
        kostenModal.style.display = 'none';
        resetKennzeichen();
        loadData();
    });

    // Modal schließen
    btnModalClose.addEventListener('click', () => {
        kostenModal.style.display = 'none';
    });

    // Fahrzeug registrieren
    fahrzeugForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const kennzeichen = document.getElementById('kennzeichen-input').value.toUpperCase();
        const name = document.getElementById('name-input').value;

        try {
            const response = await fetch('/api/fahrzeuge', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ kennzeichen, name })
            });
            const result = await response.json();

            if (response.ok) {
                alert('✅ Fahrzeug erfolgreich registriert!');
                fahrzeugForm.reset();
                loadData();
            } else {
                alert('❌ Fehler: ' + result.error);
            }
        } catch (error) {
            console.error('Fehler bei Registrierung:', error);
            alert('❌ Netzwerkfehler');
        }
    });

    // Kennzeichen zurücksetzen
    function resetKennzeichen() {
        aktuellesKennzeichen = null;
        kennzeichenDisplay.innerHTML = `
            <div class="kennzeichen-placeholder">
                <span>Warten auf Kennzeichen...</span>
            </div>
        `;
        btnEinfahrt.disabled = true;
        btnAusfahrt.disabled = true;

        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
        }
    }

    // Demo-Button für Kennzeichen-Simulation (entfernen im Produktivcode)
    const demoBtn = document.createElement('button');
    demoBtn.textContent = '🎯 Demo: Zufälliges Kennzeichen simulieren';
    demoBtn.className = 'btn btn-secondary';
    demoBtn.style.marginTop = '10px';
    demoBtn.addEventListener('click', simulateKennzeichen);
    kennzeichenDisplay.parentNode.appendChild(demoBtn);

    // Initiale Daten laden
    loadData();

    // Live-Updates alle 5 Sekunden
    setInterval(loadData, 5000);
});