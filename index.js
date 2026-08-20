/**
 * Native OpenClaw entry. MCP servers and skills are declared in
 * openclaw.plugin.json — this file exists because the host wants a package
 * entry. No session capture.
 */
export default {
  id: "memvara",
  name: "Memvara",
  register() {
    // Manifest-owned MCP + skills. Nothing to register at runtime.
  },
};
