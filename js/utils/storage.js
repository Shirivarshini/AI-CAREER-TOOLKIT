/**
 * storage.js
 * Thin localStorage wrapper. Per the product requirements, localStorage is
 * used ONLY for non-sensitive UI preferences (theme, last-used tool, guest
 * dismissal state). Auth sessions are handled by the backend via an
 * httpOnly cookie (fetch calls use credentials:'include') — no tokens or
 * resume content are ever written to client-side storage here.
 */
window.Storage_ = (() => {
  const NAMESPACE = "act:"; // AI Career Toolkit

  function get(key, fallback = null) {
    try {
      const raw = window.localStorage.getItem(NAMESPACE + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  }

  function set(key, value) {
    try {
      window.localStorage.setItem(NAMESPACE + key, JSON.stringify(value));
      return true;
    } catch {
      // Storage disabled/full — fail silently, it's only a UI preference.
      return false;
    }
  }

  function remove(key) {
    try {
      window.localStorage.removeItem(NAMESPACE + key);
    } catch {
      /* no-op */
    }
  }

  return { get, set, remove };
})();
