/**
 * Environment-based configuration for the adapter process.
 */

/**
 * Selectable mock fixtures (env BOT_MOCK_FIXTURE). "canonical" is the default
 * Controlled Mode world; "warded_hostiles_v1" is the scenario-specific
 * failure_learning/observed_precondition_v2 fixture (TASK-020). Any other
 * value is rejected at startup — the fixture is explicit process
 * configuration, never inferred.
 */
export const MOCK_FIXTURES = ["canonical", "warded_hostiles_v1"] as const;
export type MockFixtureName = (typeof MOCK_FIXTURES)[number];

export interface Config {
  /** HTTP + WebSocket API port (env BOT_API_PORT, default 8081). */
  port: number;
  /** Run the deterministic mock adapter instead of a real bot (env BOT_MOCK=1). */
  mock: boolean;
  /** Which world the mock adapter serves (env BOT_MOCK_FIXTURE, default canonical). */
  mockFixture: MockFixtureName;
  /** Minecraft server host (env MC_HOST, default localhost). */
  host: string;
  /** Minecraft server port (env MC_PORT, default 25565). */
  mcPort: number;
  /** Bot username (env MC_USERNAME, default BenchBot). */
  username: string;
  /** Minecraft version (env MC_VERSION, default 1.20.4). */
  version: string;
}

function envInt(env: NodeJS.ProcessEnv, name: string, fallback: number): number {
  const raw = env[name];
  if (raw === undefined || raw === "") return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    throw new Error(`invalid integer for env ${name}: ${JSON.stringify(raw)}`);
  }
  return value;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const rawFixture = env.BOT_MOCK_FIXTURE ?? "canonical";
  if (!(MOCK_FIXTURES as readonly string[]).includes(rawFixture)) {
    throw new Error(
      `invalid BOT_MOCK_FIXTURE: ${JSON.stringify(rawFixture)} (allowed: ${MOCK_FIXTURES.join(", ")})`,
    );
  }
  const mockFixture = rawFixture as MockFixtureName;
  return {
    port: envInt(env, "BOT_API_PORT", 8081),
    mock: env.BOT_MOCK === "1",
    mockFixture,
    host: env.MC_HOST ?? "localhost",
    mcPort: envInt(env, "MC_PORT", 25565),
    username: env.MC_USERNAME ?? "BenchBot",
    version: env.MC_VERSION ?? "1.20.4",
  };
}
