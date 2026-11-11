/* Handle the native device-page action button without an awkward external link. */
(() => {
  const EVENT_TYPE = "econergy_program_requested";
  let subscribedConnection = null;

  const attach = () => {
    const root = document.querySelector("home-assistant");
    const hass = root?.hass;
    const connection = hass?.connection;
    if (!connection || typeof connection.subscribeEvents !== "function") return;
    if (subscribedConnection === connection) return;
    subscribedConnection = connection;

    connection.subscribeEvents((event) => {
      const deviceId = String(event?.data?.device_id || "");
      if (!/^[a-f0-9]{12,32}$/i.test(deviceId)) return;
      const returnTo = `${window.location.pathname}${window.location.search}`;
      const path = `/econergy-program?device_id=${encodeURIComponent(deviceId)}&return_to=${encodeURIComponent(returnTo)}`;
      if (typeof root.hass?.navigate === "function") {
        root.hass.navigate(path);
      } else {
        window.location.assign(path);
      }
    }, EVENT_TYPE).catch((error) => {
      subscribedConnection = null;
      console.warn("Econergy: impossible d'activer le bouton de programmation", error);
    });
  };

  const observer = new MutationObserver(attach);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("location-changed", attach);
  window.addEventListener("hass-authenticated", attach);
  attach();
})();
