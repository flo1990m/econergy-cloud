/* Radiator-specific weekly programming panel. */
const CARD_MODULE = "/econergy/econergy-weekly-program-card.js?v=2.1.5";

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
        .activate { padding:16px; border-radius:12px; background:var(--card-background-color); }
        .activate p { margin:0 0 12px; color:var(--secondary-text-color); line-height:1.45; }
        .activate button { border:0; border-radius:8px; padding:11px 16px; background:var(--primary-color); color:var(--text-primary-color, white); font:inherit; font-weight:600; cursor:pointer; }
        .activate button[disabled] { opacity:.55; cursor:default; }
        .activation-status { min-height:18px; margin-top:10px; color:var(--secondary-text-color); font-size:13px; }
        .activation-status.error { color:var(--error-color); }
        .activation-status.success { color:var(--success-color, var(--primary-color)); }
        @media(max-width:600px) { :host { padding:8px; } h1 {font-size:19px;} }
      </style>
      <div class="wrap">
        <a class="back" id="back-link" href="/config/devices"><ha-icon icon="mdi:arrow-left"></ha-icon>Retour au radiateur</a>
        <div class="heading">
          <ha-icon icon="mdi:calendar-week"></ha-icon>
          <div><h1>Programmes du radiateur</h1><div class="subtitle" id="device-name">Chargement du radiateur…</div></div>
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
