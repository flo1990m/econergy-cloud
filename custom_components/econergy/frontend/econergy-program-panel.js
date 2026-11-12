/* Radiator-specific weekly programming and 15-day consumption overview. */
const CARD_MODULE = "/econergy/econergy-weekly-program-card.js?v=2.1.3";

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

class EconergyProgramPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._card = null;
    this._entity = null;
    this._loading = false;
    this._renderShell();
    this.shadowRoot.addEventListener("click", (event) => {
      const button = event.target?.closest?.("#activate-program");
      if (button) this._activateProgram();
    });
  }

  set hass(value) {
    this._hass = value;
    this._updateCard();
  }

  get hass() {
    return this._hass;
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:16px; box-sizing:border-box; }
        .wrap { max-width:1000px; margin:0 auto; }
        .heading { display:flex; align-items:center; gap:12px; margin:4px 0 16px; }
        .heading ha-icon { color:var(--primary-color); --mdc-icon-size:28px; }
        h1 { margin:0; font-size:22px; font-weight:500; }
        h2 { margin:0 0 12px; font-size:19px; font-weight:500; }
        .subtitle { color:var(--secondary-text-color); margin-top:3px; font-size:14px; }
        .message { padding:16px; border-radius:12px; background:var(--card-background-color); color:var(--primary-text-color); }
        .error { color:var(--error-color); }
        .back { display:inline-flex; align-items:center; gap:7px; margin:0 0 14px; color:var(--primary-color); text-decoration:none; }
        .intro { margin-bottom:12px; line-height:1.45; }
        .section { margin-top:22px; }
        .consumption { padding:16px; border-radius:12px; background:var(--card-background-color); }
        .chart { display:grid; grid-template-columns:repeat(15,minmax(0,1fr)); gap:5px; align-items:end; height:170px; margin-top:14px; }
        .bar-wrap { min-width:0; display:flex; flex-direction:column; align-items:center; justify-content:end; height:100%; gap:5px; }
        .bar-value { font-size:10px; color:var(--secondary-text-color); min-height:13px; white-space:nowrap; }
        .bar { width:100%; max-width:26px; min-height:3px; background:var(--primary-color); border-radius:5px 5px 2px 2px; }
        .bar.missing { background:var(--disabled-text-color); opacity:.35; }
        .bar-date { font-size:10px; color:var(--secondary-text-color); writing-mode:vertical-rl; transform:rotate(180deg); height:37px; }
        .legend { color:var(--secondary-text-color); font-size:12px; margin-top:8px; }
        .activate { padding:16px; border-radius:12px; background:var(--card-background-color); }
        .activate p { margin:0 0 12px; color:var(--secondary-text-color); line-height:1.45; }
        .activate button { border:0; border-radius:8px; padding:11px 16px; background:var(--primary-color); color:var(--text-primary-color, white); font:inherit; font-weight:600; cursor:pointer; }
        .activate button[disabled] { opacity:.55; cursor:default; }
        .activation-status { min-height:18px; margin-top:10px; color:var(--secondary-text-color); font-size:13px; }
        .activation-status.error { color:var(--error-color); }
        .activation-status.success { color:var(--success-color, var(--primary-color)); }
        .table-wrap { overflow-x:auto; margin-top:14px; }
        table { width:100%; border-collapse:collapse; font-size:13px; }
        th,td { padding:8px 6px; text-align:left; border-bottom:1px solid var(--divider-color); }
        th { color:var(--secondary-text-color); font-weight:500; }
        td.num { text-align:right; font-variant-numeric:tabular-nums; }
        @media(max-width:600px) { :host { padding:8px; } h1 {font-size:19px;} .chart {gap:2px;} .bar-value {font-size:8px;} }
      </style>
      <div class="wrap">
        <a class="back" id="back-link" href="/config/devices"><ha-icon icon="mdi:arrow-left"></ha-icon>Retour au radiateur</a>
        <div class="heading">
          <ha-icon icon="mdi:calendar-week"></ha-icon>
          <div><h1>Programmer le radiateur</h1><div class="subtitle" id="device-name">Chargement du radiateur…</div></div>
        </div>
        <div class="message intro">Définis les heures pendant lesquelles le radiateur chauffe en <b>Confort</b>. En dehors de ces plages, il reste en <b>Éco</b>. Tu peux prévoir jusqu'à trois périodes par jour et copier les réglages d'un jour via l'éditeur.</div>
        <div id="content"><div class="message">Chargement de la programmation…</div></div>
        <section class="section">
          <h2>Mettre le programme en service</h2>
          <div class="activate">
            <p>Le planning enregistré ne change pas automatiquement le mode du radiateur. Après avoir enregistré tes horaires, active ici le mode <b>Programmation</b> pour qu'il alterne entre Confort et Éco.</p>
            <button id="activate-program" type="button">Activer la programmation</button>
            <div id="activation-status" class="activation-status" role="status"></div>
          </div>
        </section>
        <section class="section">
          <h2>Consommation estimée sur 15 jours</h2>
          <div id="consumption" class="consumption"><div class="message">Chargement des relevés de consommation…</div></div>
        </section>
      </div>`;
  }

  async _updateCard() {
    if (!this._hass || this._loading) return;
    const params = new URLSearchParams(window.location.search);
    const deviceId = params.get("device_id");
    const returnTo = params.get("return_to");
    const backLink = this.shadowRoot.getElementById("back-link");
    if (backLink && returnTo && returnTo.startsWith("/") && !returnTo.startsWith("//")) {
      backLink.setAttribute("href", returnTo);
    }
    if (!deviceId) {
      this._showMessage("Identifiant du radiateur absent dans l'adresse de la page.", true);
      return;
    }

    const matching = Object.entries(this._hass.states || {}).find(([entityId, state]) =>
      entityId.startsWith("sensor.")
      && String(state?.attributes?.econergy_device_id || "") === deviceId
      && state?.attributes?.days_api,
    );
    if (!matching) {
      this._showMessage("Le programme de ce radiateur n'est pas encore chargé. Actualise la page dans quelques instants.", true);
      this._renderConsumption(deviceId);
      return;
    }

    const [entityId, state] = matching;
    const deviceName = String(state.attributes.friendly_name || entityId)
      .replace(/^Econergy\s*/i, "")
      .replace(/\s*Programme hebdomadaire$/i, "")
      .trim();
    this.shadowRoot.getElementById("device-name").textContent = deviceName;

    try {
      if (!customElements.get("econergy-weekly-program-card")) {
        this._loading = true;
        await import(CARD_MODULE);
        await customElements.whenDefined("econergy-weekly-program-card");
        this._loading = false;
      }
      if (!this._card || this._entity !== entityId) {
        const content = this.shadowRoot.getElementById("content");
        content.innerHTML = "";
        this._card = document.createElement("econergy-weekly-program-card");
        this._card.setConfig({ entity: entityId, name: deviceName });
        content.appendChild(this._card);
        this._entity = entityId;
      }
      this._card.hass = this._hass;
    } catch (error) {
      this._loading = false;
      this._showMessage(error?.message || "Impossible de charger la carte de programmation.", true);
    }
    this._renderConsumption(deviceId);
  }

  async _activateProgram() {
    const target = this.shadowRoot.getElementById("activation-status");
    const button = this.shadowRoot.getElementById("activate-program");
    if (!this._hass || !target || !button) return;

    if (!this._card) {
      target.textContent = "L'éditeur de programmation n'a pas encore fini de charger.";
      target.className = "activation-status error";
      return;
    }
    if (this._card.hasUnsavedChanges?.()) {
      target.textContent = "Enregistre d'abord les horaires et les consignes avant d'activer le programme.";
      target.className = "activation-status error";
      return;
    }

    const deviceId = new URLSearchParams(window.location.search).get("device_id");
    const climateEntity = Object.entries(this._hass.states || {}).find(([entityId, state]) =>
      entityId.startsWith("climate.")
      && String(state?.attributes?.econergy_device_id || "") === deviceId,
    )?.[0];
    if (!climateEntity) {
      target.textContent = "L'entité climate de ce radiateur est introuvable.";
      target.className = "activation-status error";
      return;
    }

    button.disabled = true;
    target.textContent = "Activation du mode Programmation…";
    target.className = "activation-status";
    try {
      await this._hass.callService("climate", "set_preset_mode", {
        entity_id: climateEntity,
        preset_mode: "Programmation",
      });
      target.textContent = "Mode Programmation activé. Le radiateur suit maintenant les plages Confort et Éco.";
      target.className = "activation-status success";
    } catch (error) {
      target.textContent = error?.message || "Impossible d'activer le mode Programmation.";
      target.className = "activation-status error";
    } finally {
      button.disabled = false;
    }
  }

  _renderConsumption(deviceId) {
    const target = this.shadowRoot.getElementById("consumption");
    if (!target || !this._hass) return;
    const match = Object.entries(this._hass.states || {}).find(([entityId, state]) =>
      entityId.startsWith("sensor.")
      && String(state?.attributes?.econergy_device_id || "") === deviceId
      && Array.isArray(state?.attributes?.jours_disponibles),
    );
    if (!match) {
      target.innerHTML = '<div class="message">Les relevés de consommation ne sont pas encore disponibles.</div>';
      return;
    }
    const days = match[1].attributes.jours_disponibles;
    if (!days.length) {
      target.innerHTML = '<div class="message">Aucun relevé quotidien n’a été retourné pour ce radiateur.</div>';
      return;
    }
    const values = days.map((day) => day?.estimatedKWh == null ? null : Number(day.estimatedKWh));
    const valid = values.filter((value) => Number.isFinite(value) && value >= 0);
    const max = Math.max(0.1, ...valid);
    const bars = days.map((day, index) => {
      const value = values[index];
      const known = Number.isFinite(value) && value >= 0;
      const height = known ? Math.max(3, Math.round((value / max) * 112)) : 3;
      const date = String(day?.date || "");
      const label = date ? date.slice(5) : "—";
      const display = known ? `${value.toFixed(1)} kWh` : "Aucun";
      return `<div class="bar-wrap" title="${escapeHtml(date)} · ${escapeHtml(display)}"><div class="bar-value">${known ? value.toFixed(1) : "–"}</div><div class="bar ${known ? "" : "missing"}" style="height:${height}px"></div><div class="bar-date">${escapeHtml(label)}</div></div>`;
    }).join("");
    const rows = days.map((day) => {
      const energy = day?.estimatedKWh == null ? "Aucune remontée" : `${Number(day.estimatedKWh).toFixed(2)} kWh`;
      const seconds = day?.heatingSeconds == null ? "—" : `${(Number(day.heatingSeconds) / 3600).toFixed(1)} h`;
      return `<tr><td>${escapeHtml(day?.date || "—")}</td><td class="num">${escapeHtml(energy)}</td><td class="num">${escapeHtml(seconds)}</td></tr>`;
    }).join("");
    target.innerHTML = `
      <div><b>Énergie estimée par jour</b></div>
      <div class="chart">${bars}</div>
      <div class="legend">Données des 15 derniers jours complets. La journée actuelle n'est pas incluse. Une absence de relevé n'est pas comptée comme zéro.</div>
      <div class="table-wrap"><table><thead><tr><th>Jour</th><th class="num">Énergie estimée</th><th class="num">Chauffe</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="legend">L'énergie est estimée à partir de la durée de chauffe et de la puissance nominale du radiateur. Ce n'est pas un relevé Linky.</div>`;
  }

  _showMessage(message, error = false) {
    const content = this.shadowRoot.getElementById("content");
    if (!content) return;
    content.innerHTML = `<div class="message ${error ? "error" : ""}"></div>`;
    content.querySelector(".message").textContent = message;
  }
}

if (!customElements.get("econergy-program-panel")) {
  customElements.define("econergy-program-panel", EconergyProgramPanel);
}
