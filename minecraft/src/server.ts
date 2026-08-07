/**
 * HTTP + WebSocket API server implementing the Bot Bridge Protocol (v1):
 * - GET  /health
 * - GET  /state       → WorldState (503 when the bot is not connected)
 * - POST /action      → ActionResult (400 invalid body, 503 not connected,
 *                       actions run strictly serially via a FIFO queue)
 * - GET  /events (WS) → hello on connect, then every RawGameEvent broadcast
 */
import express, { type Express } from "express";
import { createServer as createHttpServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { WebSocketServer, WebSocket } from "ws";
import type { BotAdapter } from "./adapter";
import { ActionRequestSchema, type HealthResponse } from "./protocol";

export interface ApiServer {
  app: Express;
  server: Server;
  wss: WebSocketServer;
  /** Bind and return the actual port (pass 0 for an ephemeral port). */
  listen(port: number): Promise<number>;
  close(): Promise<void>;
}

export function createApiServer(adapter: BotAdapter, startedAt: number = Date.now()): ApiServer {
  const app = express();
  app.use(express.json());

  app.get("/health", (_req, res) => {
    const body: HealthResponse = {
      status: "ok",
      mode: adapter.mode,
      connected: adapter.isConnected(),
      username: adapter.username,
      uptime_s: Math.round(((Date.now() - startedAt) / 1000) * 10) / 10,
    };
    res.json(body);
  });

  app.get("/state", async (_req, res) => {
    if (!adapter.isConnected()) {
      res.status(503).json({ error: "bot not connected" });
      return;
    }
    try {
      res.json(await adapter.getState());
    } catch (err) {
      res.status(500).json({ error: err instanceof Error ? err.message : String(err) });
    }
  });

  // FIFO serial queue: each action starts only after the previous one
  // (including its state_after snapshot) has fully settled.
  let queue: Promise<unknown> = Promise.resolve();

  app.post("/action", async (req, res) => {
    if (!adapter.isConnected()) {
      res.status(503).json({ error: "bot not connected" });
      return;
    }
    const parsed = ActionRequestSchema.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({
        error: "invalid action request",
        details: parsed.error.issues.map((i) => ({ path: i.path.join("."), message: i.message })),
      });
      return;
    }
    const request = parsed.data;
    const resultPromise = queue.then(() => adapter.execute(request, request.timeout_ms));
    queue = resultPromise.catch(() => undefined); // a failed action must not break the queue
    try {
      // Protocol: HTTP 200 even when the action failed — check `status`.
      res.json(await resultPromise);
    } catch (err) {
      res.status(500).json({ error: err instanceof Error ? err.message : String(err) });
    }
  });

  const server = createHttpServer(app);
  const wss = new WebSocketServer({ server, path: "/events" });
  // Bind errors surface through the listen() promise; keep the wss from
  // re-emitting them as an unhandled 'error' event.
  wss.on("error", () => undefined);

  wss.on("connection", (ws) => {
    ws.send(JSON.stringify({ type: "hello", mode: adapter.mode, username: adapter.username }));
  });

  adapter.events.on("event", (event) => {
    const message = JSON.stringify({ type: "event", event });
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) client.send(message);
    }
  });

  return {
    app,
    server,
    wss,
    listen(port: number): Promise<number> {
      return new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(port, () => {
          server.removeListener("error", reject);
          resolve((server.address() as AddressInfo).port);
        });
      });
    },
    close(): Promise<void> {
      return new Promise((resolve) => {
        for (const client of wss.clients) client.terminate();
        wss.close();
        server.closeAllConnections(); // do not hang on keep-alive sockets
        server.close(() => resolve());
      });
    },
  };
}
