/* Radiator-specific weekly programming panel. */
const CARD_MODULE = "/econergy/econergy-weekly-program-card.js?v=2.1.6";

class EconergyProgramPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._card = null;
    this._entity = null;
    this._loading = false;
    this._renderShell();
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
        .subtitle { color:var(--secondary-text-color); margin-top:3px; font-size:14px; }
        .message { padding:16px; border-radius:12px; background:var(--card-background-color); color:var(--primary-text-color); }
        .error { color:var(--error-color); }
        .back { display:inline-flex; align-items:center; gap:7px; margin:0 0 14px; color:var(--primary-color); text-decoration:none; }
        .intro { margin-bottom:12px; line-height:1.45; }
        @media(max-width:600px) { :host { padding:8px; } h1 {font-size:19px;} }
      </style>
      <div class="wrap">
        <a class="back" id="back-link" href="/config/devices"><ha-icon icon="mdi:arrow-left"></ha-icon>Retour au radiateur</a>
        <div class="heading">
          <ha-icon icon="mdi:calendar-week"></ha-icon>
          <div><h1>Programmes du radiateur</h1><div class="subtitle" id="device-name">Chargement du radiateur…</div></div>
        </div>
        <div class="message intro">Définissez les plages horaires pendant lesquelles le radiateur chauffe en <b>Confort</b>. En dehors de ces plages, il reste en <b>Éco</b>. Vous pouvez prévoir jusqu'à trois périodes par jour et copier les réglages d'un jour à l'autre dans l'éditeur.</div>
        <div id="content"><div class="message">Chargement de la programmation…</div></div>
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
      this._showMessage("Le programme de ce radiateur n'est pas encore chargé. Actualisez la page dans quelques instants.", true);
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
