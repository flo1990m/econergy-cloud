/* Econergy Cloud - single-card weekly schedule and setpoint editor */
const CARD_TYPE = "econergy-weekly-program-card";
const CARD_NAME = "Econergy – Programmation hebdomadaire";
const DOMAIN = "econergy";
const DAYS = [
  ["monday", "Lundi"],
  ["tuesday", "Mardi"],
  ["wednesday", "Mercredi"],
  ["thursday", "Jeudi"],
  ["friday", "Vendredi"],
  ["saturday", "Samedi"],
  ["sunday", "Dimanche"],
];
const COUNT_OPTIONS = ["Aucun", "1 créneau", "2 créneaux", "3 créneaux"];

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

const normalizeTime = (value) => {
  const match = String(value ?? "").match(/^(\d{2}:\d{2})/);
  return match ? match[1] : "";
};

const emptySlot = () => ({ start: "", end: "" });
const snapshot = (draft) => JSON.stringify({
  count: Number(draft.count),
  slots: draft.slots.slice(0, Number(draft.count)).map((slot) => ({
    start: slot.start,
    end: slot.end,
  })),
});
const targetSnapshot = (targets) => JSON.stringify({
  eco: Number(targets.eco),
  comfort: Number(targets.comfort),
});

class EconergyWeeklyProgramCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._drafts = {};
    this._messages = {};
    this._saving = false;
    this._selectedDay = this._todayKey();
    this._targetsDraft = null;
    this._targetsExpanded = false;
    this._awaitingSchedule = {};
    this._awaitingTargets = null;
    this._hasFocusedEditor = false;
    this._pendingRender = false;
    this._rendering = false;
    this._focusReleaseTimer = null;

    // Do not replace the editor while any native form control is active.
    // In particular, native <select> popups can briefly report focusout with
    // a null relatedTarget while the popup is still open.
    this.shadowRoot.addEventListener("focusin", (event) => {
      if (event.target?.matches?.("input, select, textarea")) {
        if (this._focusReleaseTimer !== null) {
          clearTimeout(this._focusReleaseTimer);
          this._focusReleaseTimer = null;
        }
        this._hasFocusedEditor = true;
      }
    });
    this.shadowRoot.addEventListener("focusout", (event) => {
      if (this._rendering) return;
      if (event.relatedTarget && this.shadowRoot.contains(event.relatedTarget)) return;
      if (this._focusReleaseTimer !== null) clearTimeout(this._focusReleaseTimer);
      this._focusReleaseTimer = window.setTimeout(() => {
        this._focusReleaseTimer = null;
        const active = this.shadowRoot.activeElement;
        if (active?.matches?.("input, select, textarea")) return;
        this._hasFocusedEditor = false;
        if (this._pendingRender && !this._saving) {
          this._pendingRender = false;
          this._render();
        }
      }, 300);
    });
  }

  _todayKey() {
    return ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"][new Date().getDay()];
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Choisis le capteur Econergy « Programme hebdomadaire ».");
    }
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._hasFocusedEditor) {
      this._pendingRender = true;
      return;
    }
    this._render();
  }

  static getStubConfig(hass) {
    const match = Object.entries(hass?.states || {}).find(([entityId, state]) =>
      entityId.startsWith("sensor.")
      && state?.attributes?.econergy_device_id
      && state?.attributes?.days_api,
    );
    return { entity: match?.[0] || "" };
  }

  getCardSize() {
    return 7;
  }

  hasUnsavedChanges() {
    const dirtyDay = Object.values(this._drafts).some((draft) => this._isDayDirty(draft));
    const dirtyTargets = this._targetsDraft && this._isTargetsDirty(this._targetsDraft);
    return Boolean(dirtyDay || dirtyTargets || this._saving);
  }

  _sensor() {
    return this._hass?.states?.[this._config?.entity] || null;
  }

  _deviceId() {
    return this._sensor()?.attributes?.econergy_device_id || null;
  }

  _readDay(dayKey, attrs) {
    const apiDays = attrs?.days_api || {};
    const periods = Array.isArray(apiDays[dayKey]) ? apiDays[dayKey].slice(0, 3) : [];
    const slots = periods.map((period) => ({
      start: normalizeTime(period?.start),
      end: normalizeTime(period?.end),
    }));
    while (slots.length < 3) slots.push(emptySlot());
    const value = { count: periods.length, slots };
    return { ...value, original: snapshot(value) };
  }

  _getDraft(dayKey, attrs) {
    const latest = this._readDay(dayKey, attrs);
    const pending = this._awaitingSchedule[dayKey];
    if (pending) {
      if (latest.original === pending) {
        this._drafts[dayKey] = latest;
        delete this._awaitingSchedule[dayKey];
      }
      return this._drafts[dayKey] || latest;
    }
    if (!this._drafts[dayKey]) {
      this._drafts[dayKey] = latest;
    } else if (snapshot(this._drafts[dayKey]) === this._drafts[dayKey].original
      && latest.original !== this._drafts[dayKey].original) {
      // Refresh an untouched draft if the schedule was changed from the Econergy app.
      this._drafts[dayKey] = latest;
    }
    return this._drafts[dayKey];
  }

  _readTargets(attrs) {
    return {
      eco: Number(attrs?.eco_c),
      comfort: Number(attrs?.comfort_c),
    };
  }

  _getTargets(attrs) {
    const latest = this._readTargets(attrs);
    const latestSnapshot = targetSnapshot(latest);
    if (!this._targetsDraft) {
      this._targetsDraft = { ...latest, original: latestSnapshot };
      return this._targetsDraft;
    }
    if (this._awaitingTargets) {
      if (latestSnapshot === this._awaitingTargets) {
        this._targetsDraft = { ...latest, original: latestSnapshot };
        this._awaitingTargets = null;
      }
      return this._targetsDraft;
    }
    if (targetSnapshot(this._targetsDraft) === this._targetsDraft.original
      && latestSnapshot !== this._targetsDraft.original) {
      this._targetsDraft = { ...latest, original: latestSnapshot };
    }
    return this._targetsDraft;
  }

  _isDayDirty(draft) {
    return snapshot(draft) !== draft.original;
  }

  _isTargetsDirty(targets) {
    return targetSnapshot(targets) !== targets.original;
  }

  _daySummary(dayKey, attrs) {
    const periods = Array.isArray(attrs?.days_api?.[dayKey]) ? attrs.days_api[dayKey] : [];
    if (!periods.length) return "Éco toute la journée";
    return periods.slice(0, 3).map((period) => `${normalizeTime(period.start)}–${normalizeTime(period.end)}`).join(" · ");
  }

  _validate(dayKey, draft) {
    let previousEnd = -1;
    for (let index = 0; index < draft.count; index += 1) {
      const slot = draft.slots[index];
      const toMinutes = (value) => {
        const match = /^(\d{2}):(\d{2})$/.exec(value || "");
        if (!match) return null;
        const hour = Number(match[1]);
        const minute = Number(match[2]);
        if (hour > 23 || minute > 59 || minute % 10 !== 0) return null;
        return hour * 60 + minute;
      };
      const start = toMinutes(slot.start);
      const end = toMinutes(slot.end);
      if (start === null || end === null) {
        return `Créneau ${index + 1} : renseigne une heure de début et de fin, par pas de 10 minutes.`;
      }
      if (end <= start) {
        return `Créneau ${index + 1} : l'heure de fin doit être après l'heure de début.`;
      }
      if (start < previousEnd) {
        return "Les créneaux doivent être dans l'ordre et ne pas se chevaucher.";
      }
      previousEnd = end;
    }
    return null;
  }

  _validateTargets(targets, attrs = {}) {
    const eco = Number(targets.eco);
    const comfort = Number(targets.comfort);
    const rawMaximum = Number(attrs.max_setpoint_c ?? 30);
    const maximum = Number.isFinite(rawMaximum) ? Math.min(30, Math.max(13.5, rawMaximum)) : 30;
    if (!Number.isFinite(eco) || eco < 13 || eco > 19 || Math.abs(eco * 2 - Math.round(eco * 2)) > 0.0001) {
      return "La consigne Éco doit être comprise entre 13 et 19 °C, par pas de 0,5 °C.";
    }
    if (!Number.isFinite(comfort) || comfort < 13.5 || comfort > maximum || Math.abs(comfort * 2 - Math.round(comfort * 2)) > 0.0001) {
      return `La consigne Confort doit être comprise entre 13,5 et ${maximum.toLocaleString("fr-FR")} °C, selon la butée maximale du radiateur.`;
    }
    if (comfort < eco + 0.5) {
      return "La consigne Confort doit être au moins 0,5 °C au-dessus de la consigne Éco.";
    }
    return null;
  }

  _slotsMarkup(draft) {
    if (draft.count === 0) {
      return `<div class="eco-note"><ha-icon icon="mdi:leaf"></ha-icon><span>Éco toute la journée, aucun créneau Confort.</span></div>`;
    }
    return draft.slots.slice(0, draft.count).map((slot, index) => `
      <div class="slot-row">
        <div class="slot-number">${index + 1}</div>
        <label><span>Début</span><input type="time" step="600" data-slot="${index + 1}" data-field="start" value="${escapeHtml(slot.start)}"></label>
        <label><span>Fin</span><input type="time" step="600" data-slot="${index + 1}" data-field="end" value="${escapeHtml(slot.end)}"></label>
      </div>
    `).join("");
  }

  _bindTimeInputs(dayKey, draft, targets) {
    this.shadowRoot.querySelectorAll('.slots input[type="time"]').forEach((input) => {
      const update = (event) => {
        const { slot, field } = event.currentTarget.dataset;
        draft.slots[Number(slot) - 1][field] = event.currentTarget.value;
        this._clearEditMessage(dayKey);
        this._updateSaveButton(draft, targets);
      };
      input.addEventListener("input", update);
      input.addEventListener("change", update);
    });
  }

  _clearEditMessage(dayKey) {
    this._messages[dayKey] = null;
    this.shadowRoot.querySelector(".message")?.remove();
  }

  _updateSaveButton(dayDraft, targets) {
    const button = this.shadowRoot.querySelector("button[data-save]");
    if (!button) return;
    const dirty = this._isDayDirty(dayDraft) || this._isTargetsDirty(targets);
    button.disabled = !dirty || this._saving;
    const help = this.shadowRoot.querySelector(".help");
    if (help) {
      help.textContent = dirty
        ? "Modifications en attente d'enregistrement."
        : "Les changements ne sont envoyés qu'à l'enregistrement.";
    }
  }

  async _saveChanges(dayKey, draft, targets, deviceId) {
    const dayDirty = this._isDayDirty(draft);
    const targetsDirty = this._isTargetsDirty(targets);
    if (!dayDirty && !targetsDirty) return;

    if (dayDirty) {
      const validationError = this._validate(dayKey, draft);
      if (validationError) {
        this._messages[dayKey] = { type: "error", text: validationError };
        this._render();
        return;
      }
    }
    if (targetsDirty) {
      const validationError = this._validateTargets(targets, this._sensor()?.attributes || {});
      if (validationError) {
        this._messages[dayKey] = { type: "error", text: validationError };
        this._render();
        return;
      }
    }

    this._saving = true;
    this._messages[dayKey] = { type: "info", text: "Envoi et vérification auprès d'Econergy…" };
    this._render();

    try {
      if (typeof this._hass?.callService !== "function") {
        throw new Error("L'interface Home Assistant ne permet pas d'envoyer les commandes.");
      }

      const payload = { device_id: deviceId };
      if (dayDirty) {
        payload.day = dayKey;
        payload.periods = draft.slots.slice(0, draft.count).map((slot) => ({
          start: slot.start,
          end: slot.end,
        }));
      }
      if (targetsDirty) {
        const originalTargets = JSON.parse(targets.original);
        if (Number(targets.eco) !== Number(originalTargets.eco)) {
          payload.eco_c = Number(targets.eco);
        }
        if (Number(targets.comfort) !== Number(originalTargets.comfort)) {
          payload.comfort_c = Number(targets.comfort);
        }
      }

      // Ask Home Assistant for a blocking service response. The card must not
      // report success merely because a fire-and-forget service call was sent.
      const serviceResult = await this._hass.callService(
        DOMAIN,
        "set_program_day",
        payload,
        undefined,
        false,
        true,
      );
      const serviceResponse = serviceResult?.response;
      if (serviceResponse?.success !== true) {
        throw new Error("Home Assistant n'a pas retourné de confirmation d'enregistrement.");
      }

      if (dayDirty) {
        draft.original = snapshot(draft);
        this._awaitingSchedule[dayKey] = draft.original;
      }
      if (targetsDirty) {
        targets.original = targetSnapshot(targets);
        this._awaitingTargets = targets.original;
      }

      const confirmedFields = Array.isArray(serviceResponse.updates)
        ? serviceResponse.updates.map((item) => item.field).join(", ")
        : "modifications demandées";
      this._messages[dayKey] = {
        type: "success",
        text: `Econergy a confirmé : ${confirmedFields}.`,
      };
    } catch (error) {
      this._messages[dayKey] = {
        type: "error",
        text: error?.message || "Econergy n'a pas confirmé la mise à jour.",
      };
    } finally {
      this._saving = false;
      this._hasFocusedEditor = false;
      this._pendingRender = false;
      this._render();
    }
  }

  _render() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    this._rendering = true;
    this._hasFocusedEditor = false;
    this._pendingRender = false;

    const sensor = this._sensor();
    const deviceId = this._deviceId();
    const attrs = sensor?.attributes || {};
    const friendlyName = String(attrs.friendly_name || this._config.entity || "Radiateur Econergy");
    const deviceName = this._config.name || friendlyName
      .replace(/^Econergy\s*/i, "")
      .replace(/\s*Programme hebdomadaire$/i, "")
      .trim();

    if (!sensor || !deviceId || !attrs.days_api) {
      this.shadowRoot.innerHTML = `
        <ha-card><div class="content error">Ce capteur n'est pas un capteur de programme Econergy. Sélectionne l'entité « Programme hebdomadaire » du radiateur.</div></ha-card>
        ${this._styles()}`;
      this._rendering = false;
      return;
    }

    if (!DAYS.some(([key]) => key === this._selectedDay)) this._selectedDay = "monday";
    const dayKey = this._selectedDay;
    const draft = this._getDraft(dayKey, attrs);
    const targets = this._getTargets(attrs);
    const dayDirty = this._isDayDirty(draft);
    const targetsDirty = this._isTargetsDirty(targets);
    const dirty = dayDirty || targetsDirty;
    const eco = Number.isFinite(targets.eco) ? `${targets.eco} °C` : "—";
    const comfort = Number.isFinite(targets.comfort) ? `${targets.comfort} °C` : "—";
    const slotsHtml = this._slotsMarkup(draft);

    const maxComfort = Math.min(30, Math.max(13.5, Number(attrs.max_setpoint_c ?? 30)));
    const targetsEditor = this._targetsExpanded ? `
      <div class="targets-editor">
        <label><span>Consigne Éco (°C)</span><input type="number" inputmode="decimal" min="13" max="19" step="0.5" data-target="eco" value="${escapeHtml(targets.eco)}"></label>
        <label><span>Consigne Confort (°C)</span><input type="number" inputmode="decimal" min="13.5" max="${maxComfort}" step="0.5" data-target="comfort" value="${escapeHtml(targets.comfort)}"></label>
      </div>
      <div class="target-hint">Éco : 13 à 19 °C · Confort : 13,5 à ${maxComfort.toLocaleString("fr-FR")} °C · Pas de 0,5 °C. La butée maximale du radiateur est respectée.</div>
    ` : "";

    const message = this._messages[dayKey]
      ? `<div class="message ${this._messages[dayKey].type}">${escapeHtml(this._messages[dayKey].text)}</div>`
      : "";

    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="header">
          <div class="heading">
            <ha-icon icon="mdi:calendar-week"></ha-icon>
            <div><div class="title">Programmation hebdomadaire</div><div class="subtitle">${escapeHtml(deviceName)}</div></div>
          </div>
          <div class="targets">
            <span><small>Éco</small><strong>${escapeHtml(eco)}</strong></span>
            <span><small>Confort</small><strong>${escapeHtml(comfort)}</strong></span>
            <button class="edit-targets" type="button" data-edit-targets aria-expanded="${this._targetsExpanded}">
              <ha-icon icon="mdi:pencil-outline"></ha-icon>${this._targetsExpanded ? "Fermer" : "Modifier"}
            </button>
          </div>
        </div>
        <div class="content">
          ${targetsEditor}
          <label class="day-picker">
            <span>Jour à modifier</span>
            <select data-role="day">
              ${DAYS.map(([key, label]) => `<option value="${key}" ${key === dayKey ? "selected" : ""}>${label}</option>`).join("")}
            </select>
          </label>
          <div class="count-row">
            <label for="econergy-slot-count">Nombre de créneaux Confort</label>
            <select id="econergy-slot-count" data-role="count">
              ${COUNT_OPTIONS.map((option, index) => `<option value="${index}" ${draft.count === index ? "selected" : ""}>${option}</option>`).join("")}
            </select>
          </div>
          <div class="slots">${slotsHtml}</div>
          <div class="actions">
            <span class="help">${dirty ? "Modifications en attente d'enregistrement." : "Les changements ne sont envoyés qu'à l'enregistrement."}</span>
            <button class="save" data-save ${!dirty || this._saving ? "disabled" : ""}>
              <ha-icon icon="mdi:content-save-check"></ha-icon>
              ${this._saving ? "Vérification…" : "Enregistrer"}
            </button>
          </div>
          ${message}
          <div class="footnote"><ha-icon icon="mdi:information-outline"></ha-icon><span>3 créneaux maximum · pas de 10 minutes · pas de chevauchement. La relecture confirme l'enregistrement dans l'API ; le radiateur doit être en mode Programmation (PROG) pour suivre les horaires.</span></div>
        </div>
      </ha-card>
      ${this._styles()}
    `;

    this.shadowRoot.querySelector('select[data-role="day"]')?.addEventListener("change", (event) => {
      this._selectedDay = event.currentTarget.value;
      this._render();
    });

    this.shadowRoot.querySelector('select[data-role="count"]')?.addEventListener("change", (event) => {
      draft.count = Number(event.currentTarget.value);
      this._clearEditMessage(dayKey);
      const slots = this.shadowRoot.querySelector(".slots");
      if (slots) slots.innerHTML = this._slotsMarkup(draft);
      this._bindTimeInputs(dayKey, draft, targets);
      this._updateSaveButton(draft, targets);
    });

    this._bindTimeInputs(dayKey, draft, targets);

    this.shadowRoot.querySelectorAll('input[data-target]').forEach((input) => {
      const update = (event) => {
        const key = event.currentTarget.dataset.target;
        targets[key] = event.currentTarget.value === "" ? "" : Number(event.currentTarget.value);
        this._clearEditMessage(dayKey);
        this._updateSaveButton(draft, targets);
      };
      input.addEventListener("input", update);
      input.addEventListener("change", update);
    });

    this.shadowRoot.querySelector("button[data-edit-targets]")?.addEventListener("click", () => {
      this._targetsExpanded = !this._targetsExpanded;
      this._render();
    });

    this.shadowRoot.querySelector("button[data-save]")?.addEventListener("click", () => {
      this._saveChanges(dayKey, draft, targets, deviceId);
    });

    this._rendering = false;
  }

  _styles() {
    return `<style>
      :host { display:block; }
      ha-card { overflow:hidden; }
      .header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:18px 20px; border-bottom:1px solid var(--divider-color); }
      .heading { display:flex; align-items:center; gap:12px; min-width:0; }
      .heading ha-icon { color:var(--primary-color); --mdc-icon-size:27px; }
      .title { font-size:17px; font-weight:600; line-height:1.3; }
      .subtitle { color:var(--secondary-text-color); font-size:13px; margin-top:3px; }
      .targets { display:flex; align-items:center; gap:14px; flex-shrink:0; }
      .targets span { display:flex; flex-direction:column; align-items:flex-end; gap:2px; }
      .targets small { color:var(--secondary-text-color); font-size:11px; }
      .targets strong { font-size:14px; font-weight:600; }
      button.edit-targets { display:flex; align-items:center; gap:4px; color:var(--primary-color); border:1px solid var(--divider-color); border-radius:8px; background:transparent; padding:7px 9px; font:inherit; font-size:12px; cursor:pointer; white-space:nowrap; }
      button.edit-targets ha-icon { --mdc-icon-size:16px; }
      .content { padding:16px 18px 17px; }
      .day-picker, .count-row { display:flex; align-items:center; justify-content:space-between; gap:12px; font-size:13px; }
      .day-picker { margin-bottom:12px; }
      select, input { color:var(--primary-text-color); background:var(--secondary-background-color); border:1px solid var(--divider-color); border-radius:9px; font:inherit; min-height:42px; padding:8px 11px; }
      .day-picker select { min-width:180px; font-weight:600; }
      .count-row { margin-bottom:12px; }
      .count-row select { min-width:180px; }
      .slots { display:flex; flex-direction:column; gap:9px; }
      .slot-row { display:grid; grid-template-columns:38px 1fr 1fr; gap:12px; align-items:end; padding:11px 0; border-top:1px solid var(--divider-color); }
      .slot-number { width:30px; height:30px; display:flex; align-items:center; justify-content:center; border-radius:50%; color:var(--primary-color); background:var(--secondary-background-color); font-weight:700; font-size:13px; align-self:center; }
      .slot-row label, .targets-editor label { display:flex; flex-direction:column; gap:5px; color:var(--secondary-text-color); font-size:12px; }
      .slot-row input, .targets-editor input { width:100%; box-sizing:border-box; }
      .targets-editor { display:grid; grid-template-columns:1fr 1fr; gap:12px; padding:12px; border:1px solid var(--divider-color); border-radius:10px; margin-bottom:14px; }
      .target-hint { margin:-7px 0 14px; color:var(--secondary-text-color); font-size:11px; }
      .eco-note { display:flex; align-items:center; gap:9px; color:var(--secondary-text-color); background:var(--secondary-background-color); border-radius:10px; padding:13px; font-size:13px; }
      .eco-note ha-icon { color:var(--success-color, var(--primary-color)); }
      .actions { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-top:16px; }
      .help { color:var(--secondary-text-color); font-size:11px; line-height:1.4; }
      button.save { border:0; border-radius:9px; background:var(--primary-color); color:var(--text-primary-color, white); font-weight:600; padding:11px 15px; cursor:pointer; display:flex; align-items:center; gap:7px; white-space:nowrap; min-height:42px; }
      button.save ha-icon { --mdc-icon-size:18px; }
      button:disabled { opacity:.45; cursor:default; }
      .message { margin-top:12px; border-radius:9px; padding:10px 12px; font-size:12px; line-height:1.4; }
      .message.error { color:var(--error-color); background:var(--error-background-color, var(--secondary-background-color)); }
      .message.success { color:var(--success-color, var(--primary-color)); background:var(--secondary-background-color); }
      .message.info { color:var(--secondary-text-color); background:var(--secondary-background-color); }
      .footnote { display:flex; align-items:flex-start; gap:7px; color:var(--secondary-text-color); font-size:11px; line-height:1.45; margin-top:15px; }
      .footnote ha-icon { --mdc-icon-size:16px; flex-shrink:0; }
      .error { padding:18px; color:var(--error-color); }
      @media (max-width:520px) {
        .header { align-items:flex-start; flex-direction:column; }
        .targets { width:100%; justify-content:flex-start; flex-wrap:wrap; }
        .targets span { align-items:flex-start; }
        .day-picker, .count-row { align-items:flex-start; flex-direction:column; }
        .day-picker select, .count-row select { width:100%; }
        .slot-row { grid-template-columns:28px 1fr 1fr; gap:8px; }
        .actions { align-items:stretch; flex-direction:column; }
        button.save { justify-content:center; }
      }
    </style>`;
  }
}

if (!customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, EconergyWeeklyProgramCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: CARD_NAME,
    description: "Un éditeur unique pour les jours, les créneaux Confort et les consignes Éco/Confort.",
    preview: true,
    getEntitySuggestion: (hass, entityId) => {
      const state = hass?.states?.[entityId];
      const attributes = state?.attributes || {};
      if (
        !entityId.startsWith("sensor.")
        || !attributes.econergy_device_id
        || !attributes.days_api
        || attributes.eco_c === undefined
        || attributes.comfort_c === undefined
      ) {
        return null;
      }
      return {
        config: { type: `custom:${CARD_TYPE}`, entity: entityId },
      };
    },
  });
}
