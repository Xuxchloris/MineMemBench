/**
 * Entry point: pick the adapter (mock or real mineflayer bot), connect it,
 * then serve the HTTP + WebSocket API on BOT_API_PORT.
 */
import { loadConfig } from "./config";
import type { BotAdapter } from "./adapter";
import { MockAdapter } from "./mock";
import { MineflayerAdapter } from "./bot";
import { createApiServer } from "./server";

async function main(): Promise<void> {
  const config = loadConfig();

  const adapter: BotAdapter = config.mock
    ? new MockAdapter({ username: config.username })
    : new MineflayerAdapter({
        host: config.host,
        port: config.mcPort,
        username: config.username,
        version: config.version,
      });

  await adapter.connect();
  console.log(`[minemembench] adapter connected (mode=${adapter.mode}, username=${adapter.username})`);

  const api = createApiServer(adapter);
  const port = await api.listen(config.port);
  console.log(`[minemembench] API listening on port ${port} (HTTP + WS /events)`);

  const shutdown = async (signal: string) => {
    console.log(`[minemembench] ${signal} received, shutting down`);
    await adapter.disconnect().catch(() => undefined);
    await api.close().catch(() => undefined);
    process.exit(0);
  };
  process.on("SIGINT", () => void shutdown("SIGINT"));
  process.on("SIGTERM", () => void shutdown("SIGTERM"));
}

main().catch((err) => {
  console.error("[minemembench] fatal:", err instanceof Error ? err.message : err);
  process.exit(1);
});
