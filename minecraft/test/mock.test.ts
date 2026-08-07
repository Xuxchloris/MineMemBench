import { once } from "node:events";
import { beforeEach, describe, expect, it } from "vitest";
import { MockAdapter } from "../src/mock";
import { ActionRequestSchema, type ActionRequest, type RawGameEvent } from "../src/protocol";

function action(body: unknown): ActionRequest {
  return ActionRequestSchema.parse(body);
}

describe("MockAdapter", () => {
  let adapter: MockAdapter;

  beforeEach(async () => {
    adapter = new MockAdapter();
    await adapter.connect();
  });

  it("reports a deterministic initial state", async () => {
    const state = await adapter.getState();
    expect(state.mode).toBe("mock");
    expect(state.username).toBe("BenchBot");
    expect(state.position).toEqual({ x: 0, y: 64, z: 0 });
    expect(state.dimension).toBe("minecraft:overworld");
    expect(state.inventory).toContainEqual({ slot: 0, name: "stone", display_name: "Stone", count: 32 });
    expect(state.inventory).toContainEqual({ slot: 1, name: "stone_sword", display_name: "Stone Sword", count: 1 });
    expect(state.nearby_entities.map((e) => e.name)).toContain("zombie");
    expect(state.nearby_players.map((p) => p.username)).toContain("Steve");
    // Protocol: nearby_entities excludes players.
    expect(state.nearby_entities.every((e) => e.kind !== "player")).toBe(true);
  });

  it("isConnected reflects connect/disconnect", async () => {
    expect(adapter.isConnected()).toBe(true);
    await adapter.disconnect();
    expect(adapter.isConnected()).toBe(false);
  });

  it("move_to updates position and echoes it in result + state_after", async () => {
    const result = await adapter.execute(action({ action: "move_to", arguments: { x: 10, y: 64, z: 10 } }), 5000);
    expect(result.status).toBe("completed");
    expect(result.error).toBeNull();
    expect(result.result).toEqual({ position: { x: 10, y: 64, z: 10 } });
    expect(result.state_after.position).toEqual({ x: 10, y: 64, z: 10 });
    expect((await adapter.getState()).position).toEqual({ x: 10, y: 64, z: 10 });
  });

  it("chat completes and emits a raw chat event", async () => {
    const [event] = (await Promise.all([
      once(adapter.events, "event").then(([e]) => e as RawGameEvent),
      adapter.execute(action({ action: "chat", arguments: { message: "hello world" } }), 5000),
    ])) as [RawGameEvent, unknown];
    expect(event.kind).toBe("chat");
    expect(event.data).toEqual({ username: "BenchBot", message: "hello world" });
  });

  it("give_item fails when the item is not in inventory", async () => {
    const result = await adapter.execute(
      action({ action: "give_item", arguments: { username: "Steve", item: "diamond", count: 1 } }),
      5000,
    );
    expect(result.status).toBe("failed");
    expect(result.result).toBeNull();
    expect(result.error).toMatch(/not in inventory/);
  });

  it("give_item tosses items, decrements inventory and emits item_dropped", async () => {
    const [event, result] = (await Promise.all([
      once(adapter.events, "event").then(([e]) => e as RawGameEvent),
      adapter.execute(action({ action: "give_item", arguments: { username: "Steve", item: "stone", count: 2 } }), 5000),
    ])) as [RawGameEvent, Awaited<ReturnType<MockAdapter["execute"]>>];
    expect(result.status).toBe("completed");
    expect(result.result).toEqual({ item: "stone", count: 2, target: "Steve" });
    expect(event.kind).toBe("item_dropped");
    const stone = result.state_after.inventory.find((i) => i.name === "stone");
    expect(stone?.count).toBe(30);
  });

  it("collect_item picks a dropped item back up", async () => {
    await adapter.execute(action({ action: "give_item", arguments: { username: "Steve", item: "stone", count: 4 } }), 5000);
    const result = await adapter.execute(action({ action: "collect_item", arguments: { name: "stone" } }), 5000);
    expect(result.status).toBe("completed");
    expect(result.result).toEqual({ item_name: "stone", collected: true });
    const stone = result.state_after.inventory.find((i) => i.name === "stone");
    expect(stone?.count).toBe(32);
  });

  it("collect_item fails when nothing matching is dropped", async () => {
    const result = await adapter.execute(action({ action: "collect_item", arguments: { name: "diamond" } }), 5000);
    expect(result.status).toBe("failed");
    expect(result.error).toMatch(/no dropped item/);
  });

  it("equip_item equips an inventory item and fails for a missing one", async () => {
    const ok = await adapter.execute(action({ action: "equip_item", arguments: { item: "stone_sword" } }), 5000);
    expect(ok.status).toBe("completed");
    expect(ok.state_after.equipped.hand).toEqual({ name: "stone_sword", display_name: "Stone Sword" });

    const missing = await adapter.execute(action({ action: "equip_item", arguments: { item: "bow" } }), 5000);
    expect(missing.status).toBe("failed");
    expect(missing.error).toMatch(/not in inventory/);
  });

  it("attack_entity kills the zombie and emits entity_hurt + entity_dead", async () => {
    const events: RawGameEvent[] = [];
    adapter.events.on("event", (e: RawGameEvent) => events.push(e));
    const result = await adapter.execute(action({ action: "attack_entity", arguments: { name: "zombie" } }), 5000);
    expect(result.status).toBe("completed");
    expect(result.result).toEqual({ entity_name: "zombie", killed: true });
    expect(events.map((e) => e.kind)).toEqual(["entity_hurt", "entity_dead"]);
    expect(result.state_after.nearby_entities.map((e) => e.name)).not.toContain("zombie");

    // Attacking it again fails: nothing left to match.
    const again = await adapter.execute(action({ action: "attack_entity", arguments: { name: "zombie" } }), 5000);
    expect(again.status).toBe("failed");
  });

  it("attack_entity can target by entity_id", async () => {
    const result = await adapter.execute(action({ action: "attack_entity", arguments: { entity_id: 1001 } }), 5000);
    expect(result.status).toBe("completed");
    expect(result.result).toEqual({ entity_name: "zombie", killed: true });
  });

  it("follow_player moves next to a known player and fails for strangers", async () => {
    const ok = await adapter.execute(action({ action: "follow_player", arguments: { username: "Steve" } }), 5000);
    expect(ok.status).toBe("completed");
    const steve = ok.state_after.nearby_players.find((p) => p.username === "Steve");
    expect(steve?.distance).toBeLessThanOrEqual(2);

    const stranger = await adapter.execute(action({ action: "follow_player", arguments: { username: "Herobrine" } }), 5000);
    expect(stranger.status).toBe("failed");
    expect(stranger.error).toMatch(/not visible/);
  });

  it("wait completes after the delay", async () => {
    const started = Date.now();
    const result = await adapter.execute(action({ action: "wait", arguments: { seconds: 0.1 } }), 5000);
    expect(result.status).toBe("completed");
    expect(Date.now() - started).toBeGreaterThanOrEqual(90);
  });

  it("reports status 'timeout' when the action outlives timeoutMs", async () => {
    const result = await adapter.execute(action({ action: "wait", arguments: { seconds: 5 }, timeout_ms: 100 }), 100);
    expect(result.status).toBe("timeout");
    expect(result.result).toBeNull();
    expect(result.error).toMatch(/timed out/);
    // state_after is still captured on timeout, per protocol.
    expect(result.state_after.mode).toBe("mock");
  }, 10000);
});
