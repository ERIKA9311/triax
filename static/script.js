/**
 * SECCION 1: SIMULADOR DE SALA DE ESPERA (Datos Locales)
 */
const basePacientes = [
    { id: 1, nombre: "Juan Pérez", sintomas: "Dolor de pecho fuerte, dificultad respiratoria", triage: "t1", prioridad: 1 },
    { id: 2, nombre: "María Gómez", sintomas: "Fiebre alta (39.5 °C), dolor de cabeza severo", triage: "t2", prioridad: 2 },
    { id: 3, nombre: "Luis Rodríguez", sintomas: "Torcedura de tobillo, dolor moderado", triage: "t4", prioridad: 4 },
    { id: 4, nombre: "Ana Martínez", sintomas: "Corte superficial en la mano, sangrado leve", triage: "t5", prioridad: 5 },
    { id: 5, nombre: "Carlos Sánchez", sintomas: "Dolor abdominal agudo, náuseas", triage: "t3", prioridad: 3 },
    { id: 6, nombre: "Sofía López", sintomas: "Pérdida de conciencia momentánea", triage: "t1", prioridad: 1 }
];

let pacientesEnSala = [];

function scrollAResultado() {
    const panelResultado = document.getElementById("contenedor-ia");
    if (!panelResultado) return;

    panelResultado.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}

function scrollAFormulario() {
    const formulario = document.getElementById("formulario-triage");
    if (!formulario) return;

    formulario.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

function resetPanelResultado() {
    const contenedorIA = document.getElementById("contenedor-ia");
    if (!contenedorIA) return;

    contenedorIA.innerHTML = `<p class="loading">Esperando ingreso de datos del paciente...</p>`;
}

function obtenerTiempoEspera(nivel) {
    const tiempos = {
        1: "0 minutos - atención inmediata",
        2: "30 minutos",
        3: "120 minutos",
        4: "240 minutos",
        5: "240 minutos"
    };

    return tiempos[Number(nivel)] || "Por definir según valoración clínica";
}

function actualizarSeccionObstetrica() {
    const respuestaEmbarazo = document.querySelector("input[name='embarazada']:checked");
    const seccionObstetrica = document.getElementById("seccionObstetrica");
    if (!respuestaEmbarazo || !seccionObstetrica) return;

    const estaEmbarazada = respuestaEmbarazo.value === "si";
    seccionObstetrica.classList.toggle("hidden", !estaEmbarazada);

    seccionObstetrica.querySelectorAll("input, select").forEach((campo) => {
        campo.disabled = !estaEmbarazada;
        if (!estaEmbarazada) {
            if (campo.type === "checkbox") campo.checked = false;
            else campo.value = "";
        }
    });
}

function simularLlegada() {
    const container = document.getElementById("lista-pacientes");
    if (!container) return;

    container.innerHTML = "";
    pacientesEnSala = [...basePacientes].sort(() => Math.random() - 0.5);

    pacientesEnSala.forEach((paciente, index) => {
        const card = document.createElement("div");
        card.className = "paciente-card";
        card.id = `paciente-${paciente.id}`;

        card.innerHTML = `
            <div class="paciente-info">
                <h4>${paciente.nombre}</h4>
                <p><strong>Síntomas:</strong> ${paciente.sintomas}</p>
            </div>
            <div class="triage-tag unknown" id="tag-${paciente.id}">Esperando</div>
        `;

        container.appendChild(card);
        setTimeout(() => card.classList.add("show"), index * 100);
    });

    const tituloSala = document.querySelector(".sala-espera h3");
    if (tituloSala) tituloSala.innerText = "Sala de espera";
}

function clasificarTriage() {
    if (pacientesEnSala.length === 0) return;

    pacientesEnSala.forEach((paciente) => {
        const tag = document.getElementById(`tag-${paciente.id}`);
        if (!tag) return;

        tag.innerText = `Triage ${paciente.prioridad}`;
        tag.className = `triage-tag ${paciente.triage}`;
    });

    pacientesEnSala.sort((a, b) => a.prioridad - b.prioridad);
    const container = document.getElementById("lista-pacientes");

    pacientesEnSala.forEach((paciente) => {
        const card = document.getElementById(`paciente-${paciente.id}`);
        if (card) container.appendChild(card);
    });

    const tituloSala = document.querySelector(".sala-espera h3");
    if (tituloSala) tituloSala.innerText = "Sala de espera priorizada por TRIAX";
}

/**
 * SECCION 2: INTEGRACION CON TRIAX AI (Formulario Real)
 */
document.addEventListener("DOMContentLoaded", () => {
    const loginMethodTabs = document.querySelectorAll("[data-login-method]");
    const loginMethodPanels = document.querySelectorAll("[data-login-panel]");
    const loginMetodo = document.getElementById("loginMetodo");
    const loginSubmit = document.getElementById("loginSubmit");
    const loginSubmitLabels = {
        otp: "Enviar codigo OTP",
        recovery: "Entrar con codigo",
        trxkey: "Entrar con .trxkey"
    };

    loginMethodTabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            const method = tab.dataset.loginMethod;
            loginMethodTabs.forEach((item) => item.classList.toggle("active", item === tab));
            loginMethodPanels.forEach((panel) => {
                panel.classList.toggle("active", panel.dataset.loginPanel === method);
            });
            if (loginMetodo) loginMetodo.value = method;
            if (loginSubmit) loginSubmit.textContent = loginSubmitLabels[method] || loginSubmitLabels.otp;
        });
    });

    const profileTabs = document.querySelectorAll("[data-profile-tab]");
    const profilePanels = document.querySelectorAll("[data-profile-panel]");

    profileTabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            const target = tab.dataset.profileTab;
            profileTabs.forEach((item) => item.classList.toggle("active", item === tab));
            profilePanels.forEach((panel) => {
                panel.classList.toggle("active", panel.dataset.profilePanel === target);
            });

            const url = new URL(window.location.href);
            url.searchParams.set("tab", target);
            window.history.replaceState({}, "", url);
        });
    });

    simularLlegada();
    actualizarSeccionObstetrica();

    const triageForm = document.getElementById("triageForm");
    const contenedorIA = document.getElementById("contenedor-ia");
    const btnNuevoIngreso = document.getElementById("btnNuevoIngreso");
    const opcionesEmbarazo = document.querySelectorAll("input[name='embarazada']");

    opcionesEmbarazo.forEach((opcion) => {
        opcion.addEventListener("change", actualizarSeccionObstetrica);
    });

    if (btnNuevoIngreso && triageForm) {
        btnNuevoIngreso.addEventListener("click", () => {
            triageForm.reset();
            actualizarSeccionObstetrica();
            resetPanelResultado();
            scrollAFormulario();

            const primerCampo = triageForm.querySelector("input[name='edad']");
            if (primerCampo) {
                setTimeout(() => primerCampo.focus(), 450);
            }
        });
    }

    if (triageForm) {
        triageForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            contenedorIA.innerHTML = `
                <div class="loading-state">
                    <p>Analizando signos vitales con IA...</p>
                    <div class="spinner"></div>
                </div>
            `;
            scrollAResultado();

            const formData = new FormData(triageForm);

            try {
                const response = await fetch("/ejecutar-ia", {
                    method: "POST",
                    body: formData
                });

                const data = await response.json();

                if (data.error) {
                    contenedorIA.innerHTML = `<p class="error">Error: ${data.error}</p>`;
                    scrollAResultado();
                    return;
                }

                let textoLimpio = data.respuesta.replace(/```json|```/g, "").trim();

                try {
                    const resObj = JSON.parse(textoLimpio);

                    const colores = {
                        1: "#ff4d4d",
                        2: "#ff944d",
                        3: "#ffdb4d",
                        4: "#4dff88",
                        5: "#4da6ff"
                    };

                    const colorActual = colores[resObj.nivel] || "#ffffff";
                    const tiempoEspera = obtenerTiempoEspera(resObj.nivel);

                    contenedorIA.innerHTML = `
                        <div class="resultado-card" style="border-left: 10px solid ${colorActual}">
                            <h2 style="color: ${colorActual}">TRIAGE NIVEL ${resObj.nivel}</h2>
                            <p><strong>Estado:</strong> ${resObj.prioridad}</p>
                            <p class="tiempo-espera"><strong>Tiempo máximo de espera:</strong> ${tiempoEspera}</p>
                            <hr>
                            <p><strong>Justificación Clínica:</strong> ${resObj.justificacion}</p>
                            <small>El tiempo puede variar según ocupación del servicio, recursos disponibles y emergencias con múltiples víctimas.</small>
                            <br>
                            <small>Basado en Resolución 5596 de 2015 - Análisis por IA</small>
                        </div>
                    `;
                } catch (parseError) {
                    contenedorIA.innerHTML = `
                        <div class="resultado-texto">
                            <h4>Resultado del Análisis:</h4>
                            <p>${data.respuesta}</p>
                        </div>
                    `;
                }

                scrollAResultado();
            } catch (error) {
                contenedorIA.innerHTML = `<p class="error">No se pudo conectar con el servidor.</p>`;
                scrollAResultado();
                console.error("Fetch Error:", error);
            }
        });
    }
});
