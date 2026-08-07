/**
 * Integration test: real express server + WebSocket, MockAdapter behind it,
 * listening on an ephemeral port.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import WebSocket from "ws";
import { MockAdapter } from "../src/mock";
import { createApiServer, type ApiServer } from "../src/server";
import {
  ActionResultSchema,
  HealthResponseSchema,
  WorldStateSchema,
  WsEventMessageSchema,
  WsHelloSchema,
} from "../src/protocol";

/** Collects WS messages; next() returns messages in arrival order. */
class WsClient {
  private buffer: unknown[] = [];
  private waiters: ((msg: unknown) => void)[] = [];

  constructor(private readonly ws: WebSocket) {
    ws.on("message", (data) => {
      const msg = JSON.parse(data.toString()) as unknown;
      const waiter = this.waiters.shift();
      if (waiter) waiter(msg);
      else this.buffer.push(msg);
    });
  }

  async open(): Promise<void> {
    if (this.ws.readyState === WebSocket.OPEN) return;
    await new Promise<void>((resolve, reject) => {
      this.ws.once("open", resolve);
      this.ws.once("error", reject);
    });
  }

  next(timeoutMs = 5000): Promise<unknown> {
    const buffered = this.buffer.shift();
    if (buffered !== undefined) return Promise.resolve(buffered);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("timed out waiting for WS message")), timeoutMs);
      this.waiters.push((msg) => {
        clearTimeout(timer);
        resolve(msg);
      });
    });
  }

  close(): void {
    this.ws.close();
  }
}

describe("API server (HTTP + WS) with MockAdapter", () => {
  let adapter: MockAdapter;
  let api: ApiServer;
  let base: string;

  beforeAll(async () => {
    adapter = new MockAdapter();
    await adapter.connect();
    api = createApiServer(adapter);
    const port = await api.listen(0); // ephemeral
    base = `http://127.0.0.1:${port}`;
  });

  afterAll(async () => {
    await adapter.disconnect();
    await api.close();
  });

  it("GET /health reports ok/mock/connected", async () => {
    const res = await fetch(`${base}/health`);
    expect(res.status).toBe(200);
    const body = HealthResponseSchema.parse(await res.json());
    expect(body.status).toBe("ok");
    expect(body.mode).toBe("mock");
    expect(body.connected).toBe(true);
    expect(body.username).toBe("BenchBot");
    expect(body.uptime_s).toBeGreaterThanOrEqual(0);
  });

  it("GET /state returns a protocol-valid WorldState", async () => {
    const res = await fetch(`${base}/state`);
    expect(res.status).toBe(200);
    const state = WorldStateSchema.parse(await res.json());
    expect(state.mode).toBe("mock");
    expect(state.position).toEqual({ x: 0, y: 64, z: 0 });
  });

  it("POST /action happy path returns a completed ActionResult", async () => {
    const res = await fetch(`${base}/action`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "move_to", arguments: { x: 5, y: 64, z: 5 } }),
    });
    expect(res.status).toBe(200);
    const result = ActionResultSchema.parse(await res.json());
    expect(result.status).toBe("completed");
    expect(result.result).toEqual({ position: { x: 5, y: 64, z: 5 } });
    expect(result.state_after.position).toEqual({ x: 5, y: 64, z: 5 });
  });

  it("POST /action returns HTTP 200 with status failed for a failing action", async () => {
    const res = await fetch(`${base}/action`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "equip_item", arguments: { item: "bow" } }),
    });
    expect(res.status).toBe(200);
    const result = ActionResultSchema.parse(await res.json());
    expect(result.status).toBe("failed");
    expect(result.error).toMatch(/not in inventory/);
  });

  it("POST /action rejects invalid bodies with 400", async () => {
    for (const body of [
      { action: "fly", arguments: {} }, // unknown action
      { action: "move_to", arguments: { x: 1, y: 64 } }, // missing z
      { action: "wait", arguments: { seconds: 600 } }, // out of range
      { not: "an action" },
    ]) {
      const res = await fetch(`${base}/action`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      expect(res.status, JSON.stringify(body)).toBe(400);
      const parsed = (await res.json()) as { error?: string };
      expect(parsed.error).toBeTruthy();
    }
  });

  it("POST /action executes strictly serially (FIFO)", async () => {
    // Two moves issued back-to-back must land in request order: the second
    // action's state_after must reflect the first action's position.
    const post = (x: number) =>
      fetch(`${base}/action`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "move_to", arguments: { x, y: 64, z: 0 } }),
      }).then((r) => r.json() as Promise<{ status: string; state_after: { position: { x: number } } }>);
    const [first, second] = await Promise.all([post(11), post(22)]);
    expect(first.status).toBe("completed");
    expect(second.status).toBe("completed");
    expect(second.state_after.position.x).toBe(22);
  });

  it("WS /events sends hello, then broadcasts a raw chat event", async () => {
    const address = api.server.address();
    if (address === null || typeof address === "string") throw new Error("server not listening");
    const client = new WsClient(new WebSocket(`ws://127.0.0.1:${address.port}/events`));
    try {
      await client.open();
      const hello = WsHelloSchema.parse(await client.next());
      expect(hello).toEqual({ type: "hello", mode: "mock", username: "BenchBot" });

      const res = await fetch(`${base}/action`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "chat", arguments: { message: "ws hello" } }),
      });
      expect(res.status).toBe(200);

      const message = WsEventMessageSchema.parse(await client.next());
      expect(message.event.kind).toBe("chat");
      expect(message.event.data).toEqual({ username: "BenchBot", message: "ws hello" });
      expect(message.event.timestamp).toBeTruthy();
      expect(message.event.event_id).toBeTruthy();
    } finally {
      client.close();
    }
  });
});

describe("API server with a disconnected adapter", () => {
  let adapter: MockAdapter;
  let api: ApiServer;
  let base: string;

  beforeAll(async () => {
    adapter = new MockAdapter(); // never connect()
    api = createApiServer(adapter);
    const port = await api.listen(0);
    base = `http://127.0.0.1:${port}`;
  });

  afterAll(async () => {
    await api.close();
  });

  it("GET /state and POST /action return 503", async () => {
    expect((await fetch(`${base}/state`)).status).toBe(503);
    const res = await fetch(`${base}/action`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "chat", arguments: { message: "hi" } }),
    });
    expect(res.status).toBe(503);
    // /health stays up and reports connected=false.
    const health = HealthResponseSchema.parse(await (await fetch(`${base}/health`)).json());
    expect(health.connected).toBe(false);
  });
});
