import { describe, expect, it } from "vitest";
import {
  ActionRequestSchema,
  ActionResultSchema,
  RawGameEventSchema,
  WorldStateSchema,
  type WorldState,
} from "../src/protocol";

const sampleState: WorldState = {
  timestamp: "2026-08-07T12:00:00.000Z",
  mode: "mock",
  username: "BenchBot",
  health: 20,
  food: 20,
  saturation: 5,
  oxygen: 20,
  position: { x: 0, y: 64, z: 0 },
  yaw: 0,
  pitch: 0,
  dimension: "minecraft:overworld",
  time_of_day: 6000,
  is_raining: false,
  experience_level: 0,
  inventory: [{ slot: 0, name: "stone", display_name: "Stone", count: 32 }],
  equipped: { hand: { name: "stone_sword", display_name: "Stone Sword" } },
  nearby_entities: [
    {
      id: 1001,
      name: "zombie",
      display_name: "Zombie",
      kind: "hostile",
      position: { x: 3, y: 64, z: 4 },
      distance: 5,
    },
  ],
  nearby_players: [{ username: "Steve", position: { x: 1, y: 64, z: 2 }, distance: 2.2 }],
};

describe("WorldStateSchema", () => {
  it("round-trips a full WorldState", () => {
    const parsed = WorldStateSchema.parse(sampleState);
    expect(parsed).toEqual(sampleState);
  });

  it("accepts equipped.hand = null and empty nearby lists", () => {
    const state = { ...sampleState, equipped: { hand: null }, nearby_entities: [], nearby_players: [] };
    expect(WorldStateSchema.safeParse(state).success).toBe(true);
  });

  it("rejects an invalid entity kind and a bad mode", () => {
    const badKind = structuredClone(sampleState);
    (badKind.nearby_entities[0] as { kind: string }).kind = "scary";
    expect(WorldStateSchema.safeParse(badKind).success).toBe(false);
    expect(WorldStateSchema.safeParse({ ...sampleState, mode: "creative" }).success).toBe(false);
  });
});

describe("ActionRequestSchema", () => {
  it("accepts all 8 actions and applies documented defaults", () => {
    const cases: [string, Record<string, unknown>][] = [
      ["move_to", { x: 10, y: 64, z: 10 }],
      ["follow_player", { username: "Steve" }],
      ["attack_entity", { name: "zombie" }],
      ["attack_entity", { entity_id: 1001 }],
      ["collect_item", { name: "stone" }],
      ["give_item", { username: "Steve", item: "stone" }],
      ["equip_item", { item: "stone_sword" }],
      ["wait", { seconds: 1 }],
      ["chat", { message: "hello" }],
    ];
    for (const [action, args] of cases) {
      const parsed = ActionRequestSchema.safeParse({ action, arguments: args });
      expect(parsed.success, `${action} should parse`).toBe(true);
      if (parsed.success) expect(parsed.data.timeout_ms).toBe(30000);
    }
    const follow = ActionRequestSchema.parse({ action: "follow_player", arguments: { username: "Steve" } });
    expect(follow.arguments.distance).toBe(2);
    const give = ActionRequestSchema.parse({ action: "give_item", arguments: { username: "Steve", item: "stone" } });
    expect(give.arguments.count).toBe(1);
    const equip = ActionRequestSchema.parse({ action: "equip_item", arguments: { item: "stone_sword" } });
    expect(equip.arguments.destination).toBe("hand");
    const collect = ActionRequestSchema.parse({ action: "collect_item", arguments: { name: "stone" } });
    expect(collect.arguments.max_distance).toBe(16);
  });

  it("respects the timeout_ms bound (max 120000)", () => {
    const ok = ActionRequestSchema.safeParse({ action: "wait", arguments: { seconds: 1 }, timeout_ms: 120000 });
    expect(ok.success).toBe(true);
    const tooBig = ActionRequestSchema.safeParse({ action: "wait", arguments: { seconds: 1 }, timeout_ms: 120001 });
    expect(tooBig.success).toBe(false);
  });

  it("rejects invalid action bodies", () => {
    const bad: unknown[] = [
      { action: "fly", arguments: {} }, // unknown action
      { action: "move_to", arguments: { x: 1, y: 64 } }, // missing z
      { action: "wait", arguments: { seconds: 0.05 } }, // below 0.1 min
      { action: "wait", arguments: { seconds: 61 } }, // above 60 max
      { action: "chat", arguments: { message: "" } }, // empty message
      { action: "chat", arguments: { message: "x".repeat(257) } }, // over 256 chars
      { action: "give_item", arguments: { username: "Steve", item: "stone", count: 0 } },
      { action: "attack_entity", arguments: {} }, // needs name or entity_id
      { action: "equip_item", arguments: { item: "stone_sword", destination: "offhand" } },
      { action: "chat", arguments: { message: "hi" }, bogus: true }, // unknown key
      { arguments: {} }, // missing action
      "not-an-object",
    ];
    for (const body of bad) {
      expect(ActionRequestSchema.safeParse(body).success, JSON.stringify(body)).toBe(false);
    }
  });
});

describe("RawGameEventSchema", () => {
  it("round-trips a chat event with raw data", () => {
    const event = {
      event_id: "3b8f1c2e-0000-4000-8000-000000000000",
      timestamp: "2026-08-07T12:00:00.000Z",
      kind: "chat",
      data: { username: "BenchBot", message: "hello" },
    };
    expect(RawGameEventSchema.parse(event)).toEqual(event);
  });

  it("rejects an unknown event kind", () => {
    const event = {
      event_id: "x",
      timestamp: "2026-08-07T12:00:00.000Z",
      kind: "explosion",
      data: {},
    };
    expect(RawGameEventSchema.safeParse(event).success).toBe(false);
  });
});

describe("ActionResultSchema", () => {
  it("validates a completed result and a failed result", () => {
    const base = {
      action_id: "3b8f1c2e-0000-4000-8000-000000000000",
      action: "move_to",
      started_at: "2026-08-07T12:00:00.000Z",
      finished_at: "2026-08-07T12:00:01.000Z",
      state_after: sampleState,
    };
    expect(ActionResultSchema.safeParse({ ...base, status: "completed", result: { position: { x: 1, y: 64, z: 1 } }, error: null }).success).toBe(true);
    expect(ActionResultSchema.safeParse({ ...base, status: "failed", result: null, error: "target unreachable" }).success).toBe(true);
    expect(ActionResultSchema.safeParse({ ...base, status: "done", result: null, error: null }).success).toBe(false);
  });
});
