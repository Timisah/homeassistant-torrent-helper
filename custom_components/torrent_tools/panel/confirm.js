/* Torrent Tools: administrator approval of torrent file deletion.
 * Text is inserted with textContent only; nothing from the backend is parsed as HTML. */
class TorrentToolsConfirmPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._started = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._started) {
      this._started = true;
      this.refresh();
    }
  }

  el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  async refresh() {
    const root = this.shadowRoot;
    root.replaceChildren();
    const style = this.el("style");
    style.textContent =
      ":host{display:block;padding:24px;color:var(--primary-text-color)}" +
      "main{max-width:880px;margin:auto}article{padding:16px;border:1px solid var(--divider-color);" +
      "border-radius:12px;margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}" +
      "button{padding:10px 16px;border:0;border-radius:8px;cursor:pointer;margin-right:12px}" +
      ".danger{background:var(--error-color,#b71c1c);color:#fff}.status{white-space:pre-wrap}";
    root.append(style);
    const main = this.el("main");
    root.append(main);
    main.append(this.el("h2", "Torrent file deletion"));
    main.append(
      this.el(
        "p",
        "Review the exact torrent. Approving permanently deletes it and its downloaded files. " +
          "Requests expire after 10 minutes and can be used once."
      )
    );
    const refresh = this.el("button", "Refresh");
    refresh.onclick = () => this.refresh();
    main.append(refresh);
    const status = this.el("p", "", "status");
    main.append(status);
    try {
      const requests = await this._hass.callWS({ type: "torrent_tools/pending_deletions" });
      if (!requests.length) status.textContent = "No pending requests.";
      for (const request of requests) {
        const t = request.torrent;
        const article = this.el("article");
        article.append(this.el("h3", String(t.name)));
        article.append(
          this.el(
            "pre",
            `Hash: ${t.hash}\nSize: ${t.total_size ?? t.size ?? "unknown"} bytes\n` +
              `Save path: ${t.save_path}\nContent path: ${t.content_path}\n` +
              `Expires: ${new Date(request.expires_at * 1000).toLocaleTimeString()}`
          )
        );
        const button = this.el("button", "Delete torrent and files", "danger");
        button.onclick = async () => {
          if (!window.confirm(`Permanently delete "${t.name}" and its files at ${t.content_path}?`)) return;
          button.disabled = true;
          try {
            await this._hass.callWS({
              type: "torrent_tools/approve_deletion",
              request_id: request.request_id,
              nonce: request.nonce,
            });
            article.remove();
            status.textContent = `Deleted: ${t.name}`;
          } catch (error) {
            status.textContent = error.message || "Deletion was not confirmed. Check qBittorrent.";
          }
        };
        article.append(button);
        main.append(article);
      }
    } catch (error) {
      status.textContent = error.message || "Could not load requests.";
    }
  }
}
if (!customElements.get("torrent-tools-confirm-panel")) {
  customElements.define("torrent-tools-confirm-panel", TorrentToolsConfirmPanel);
}
