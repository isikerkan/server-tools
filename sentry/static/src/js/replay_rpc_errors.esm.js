/** @odoo-module **/
/* global window */

import {rpcBus} from "@web/core/network/rpc";

/**
 * Server-side errors reach the browser as an RPC error and end up in
 * Odoo's error dialog: the Sentry browser SDK never sees an exception,
 * so a replay recorded in buffer mode (error sampling) is never
 * uploaded and the backend event has no replay to link to.
 *
 * When the `sentry.replay_flush_on_rpc_error` system parameter is set
 * (flag exposed by the loader snippet), flush the buffered replay when
 * such an error comes back. The backend event and the replay share the
 * trace the SDK propagated on the request, so Sentry links them without
 * a duplicate browser-side error event.
 */
rpcBus.addEventListener("RPC:RESPONSE", (ev) => {
    const {error, settings} = ev.detail || {};
    if (!error || !window.sentryReplayFlushOnRpcError) {
        return;
    }
    // Connection/offline errors have no server event to link to
    if (!error.data) {
        return;
    }
    const Sentry = window.Sentry;
    const replay =
        Sentry && typeof Sentry.getReplay === "function" && Sentry.getReplay();
    if (!replay || typeof replay.flush !== "function") {
        return;
    }
    const name = error.data.name || error.name || "RPC error";
    const message = String(error.data.message || error.message || "").slice(0, 200);
    Sentry.addBreadcrumb({
        category: "odoo.rpc",
        level: "error",
        message: `${name}: ${message}`,
        data: {model: error.model, url: settings && settings.url},
    });
    Promise.resolve(replay.flush()).catch(() => undefined);
});
