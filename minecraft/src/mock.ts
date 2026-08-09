/**
 * MockAdapter: deterministic in-memory simulation of the game world.
 * Enables CI and benchmark development without a Minecraft server.
 *
 * World layout (fixed, canonical fixture):
 * - bot spawns at (0, 64, 0) in minecraft:overworld at time 6000
 * - inventory: 32x stone (slot 0), 1x stone_sword (slot 1)
 * - one zombie (id 1001) at (3, 64, 4)
 * - one fake player "Steve" at (1, 64, 2)
 *
 * The optional "warded_hostiles_v1" fixture (constructor option, from env
 * BOT_MOCK_FIXTURE) adds 1x gold_nugget (slot 2) and a skeleton (id 1002) at
 * (-4, 64, 3), and wards both hostiles behind the hidden gold_nugget
 * precondition (see WARDED_ATTACK_ERROR). The canonical fixture is the
 * default and its behavior is unchanged byte-for-byte.
 */
import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";
import { executeAction, sleep, type ActionContext, type BotAdapter } from "./adapter";
import type { MockFixtureName } from "./config";
import type {
  ActionRequest,
  ActionResult,
  EntityKind,
  InventoryItem,
  RawEventKind,
  RawGameEvent,
  Vec3,
  WorldState,
} from "./protocol";

/**
 * The item the warded_hostiles_v1 hidden environmental rule requires to be
 * equipped before a warded hostile can be harmed (TASK-020).
 */
export const WARDED_REQUIRED_ITEM = "gold_nugget";

/**
 * The stable, nonempty error the warded_hostiles_v1 fixture returns when a
 * warded hostile is attacked without gold_nugget equipped. It is the ONLY
 * required-item information the environment reveals; the entity survives.
 */
export const WARDED_ATTACK_ERROR =
  "the warded hostile resists the attack: gold_nugget must be equipped to harm it";

interface MockEntity {
  id: number;
  name: string;
  kind: EntityKind;
  position: Vec3;
  /** Set only for dropped-item entities (kind === "item"). */
  itemName?: string;
  itemCount?: number;
}

function displayNameOf(name: string): string {
  return name
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function distance(a: Vec3, b: Vec3): number {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2);
}

/** Protocol rule: distances in blocks, 1 decimal. */
function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

const NEARBY_RADIUS = 32;
const NEARBY_MAX_ENTRIES = 32;

export class MockAdapter implements BotAdapter {
  readonly mode = "mock" as const;
  readonly events = new EventEmitter();

  private readonly _username: string;
  private connected = false;

  private position: Vec3 = { x: 0, y: 64, z: 0 };
  private inventory: InventoryItem[] = [
    { slot: 0, name: "stone", display_name: "Stone", count: 32 },
    { slot: 1, name: "stone_sword", display_name: "Stone Sword", count: 1 },
  ];
  private equippedHand: { name: string; display_name: string } | null = null;
  private entities: MockEntity[] = [
    { id: 1001, name: "zombie", kind: "hostile", position: { x: 3, y: 64, z: 4 } },
  ];
  private players = new Map<string, Vec3>([["Steve", { x: 1, y: 64, z: 2 }]]);
  private nextEntityId = 2000;
  /** Warded hostiles (warded_hostiles_v1 fixture only): unharmable unless
   *  gold_nugget is equipped. Empty in the canonical fixture. */
  private readonly wardedEntityIds = new Set<number>();

  constructor(options: { username?: string; fixture?: MockFixtureName } = {}) {
    this._username = options.username ?? "BenchBot";
    if ((options.fixture ?? "canonical") === "warded_hostiles_v1") {
      // Scenario-specific fixture for failure_learning/observed_precondition_v2
      // (TASK-020): a second distinct hostile plus one non-obvious available
      // inventory item; both hostiles are warded (see WARDED_ATTACK_ERROR).
      // The canonical default above is untouched byte-for-byte.
      this.inventory.push({ slot: 2, name: "gold_nugget", display_name: "Gold Nugget", count: 1 });
      this.entities.push({ id: 1002, name: "skeleton", kind: "hostile", position: { x: -4, y: 64, z: 3 } });
      this.wardedEntityIds.add(1001).add(1002);
    }
  }

  get username(): string | null {
    return this._username;
  }

  async connect(): Promise<void> {
    this.connected = true;
  }

  async disconnect(): Promise<void> {
    this.connected = false;
  }

  isConnected(): boolean {
    return this.connected;
  }

  // -------------------------------------------------------------------------
  // WorldState
  // -------------------------------------------------------------------------

  async getState(): Promise<WorldState> {
    const nearbyEntities = this.entities
      .map((e) => ({ e, d: round1(distance(this.position, e.position)) }))
      .filter(({ d }) => d <= NEARBY_RADIUS)
      .sort((a, b) => a.d - b.d)
      .slice(0, NEARBY_MAX_ENTRIES)
      .map(({ e, d }) => ({
        id: e.id,
        name: e.name,
        display_name: displayNameOf(e.name),
        kind: e.kind,
        position: { ...e.position },
        distance: d,
      }));

    const nearbyPlayers = [...this.players.entries()]
      .map(([username, pos]) => ({ username, pos, d: round1(distance(this.position, pos)) }))
      .filter(({ d }) => d <= NEARBY_RADIUS)
      .sort((a, b) => a.d - b.d)
      .map(({ username, pos, d }) => ({ username, position: { ...pos }, distance: d }));

    return {
      timestamp: new Date().toISOString(),
      mode: this.mode,
      username: this._username,
      health: 20,
      food: 20,
      saturation: 5,
      oxygen: 20,
      position: { ...this.position },
      yaw: 0,
      pitch: 0,
      dimension: "minecraft:overworld",
      time_of_day: 6000,
      is_raining: false,
      experience_level: 0,
      inventory: this.inventory.map((item) => ({ ...item })),
      equipped: { hand: this.equippedHand ? { ...this.equippedHand } : null },
      nearby_entities: nearbyEntities,
      nearby_players: nearbyPlayers,
    };
  }

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------

  execute(action: ActionRequest, timeoutMs: number): Promise<ActionResult> {
    return executeAction({
      action,
      timeoutMs,
      run: (ctx) => this.dispatch(action, ctx),
      getState: () => this.getState(),
    });
  }

  private async dispatch(action: ActionRequest, _ctx: ActionContext): Promise<Record<string, unknown> | null> {
    switch (action.action) {
      case "move_to": {
        const { x, y, z } = action.arguments;
        this.position = { x, y, z };
        return { position: { ...this.position } };
      }

      case "follow_player": {
        const { username } = action.arguments;
        const target = this.players.get(username);
        if (!target) throw new Error(`player not visible: ${username}`);
        // Single approach: step onto the player's position (distance 0 <= requested).
        this.position = { ...target };
        return {};
      }

      case "attack_entity": {
        const { name, entity_id } = action.arguments;
        const candidates = this.entities
          .filter((e) => e.kind !== "item")
          .filter((e) => (entity_id !== undefined ? e.id === entity_id : e.name === name))
          .filter((e) => distance(this.position, e.position) <= NEARBY_RADIUS)
          .sort((a, b) => distance(this.position, a.position) - distance(this.position, b.position));
        const target = candidates[0];
        if (!target) {
          throw new Error(`no matching entity (name=${name ?? "-"}, entity_id=${entity_id ?? "-"})`);
        }
        // Hidden environmental rule (warded_hostiles_v1 fixture): a warded
        // hostile cannot be harmed unless gold_nugget is equipped. The attack
        // fails with the stable warded error and the entity remains alive.
        if (this.wardedEntityIds.has(target.id) && this.equippedHand?.name !== WARDED_REQUIRED_ITEM) {
          throw new Error(WARDED_ATTACK_ERROR);
        }
        const entityName = target.name;
        this.emitEvent("entity_hurt", { entity_id: target.id, name: target.name });
        this.entities = this.entities.filter((e) => e.id !== target.id);
        this.emitEvent("entity_dead", { entity_id: target.id, name: entityName });
        return { entity_name: entityName, killed: true };
      }

      case "collect_item": {
        const { name, max_distance } = action.arguments;
        const candidates = this.entities
          .filter((e) => e.kind === "item" && e.itemName === name)
          .filter((e) => distance(this.position, e.position) <= max_distance)
          .sort((a, b) => distance(this.position, a.position) - distance(this.position, b.position));
        const target = candidates[0];
        if (!target) throw new Error(`no dropped item '${name}' within ${max_distance} blocks`);
        // Walk to the drop, pick it up.
        this.position = { ...target.position };
        this.entities = this.entities.filter((e) => e.id !== target.id);
        this.addToInventory(name, target.itemCount ?? 1);
        return { item_name: name, collected: true };
      }

      case "give_item": {
        const { username, item, count } = action.arguments;
        const held = this.inventory.find((i) => i.name === item);
        if (!held || held.count < count) {
          throw new Error(`item not in inventory: ${item} (need ${count})`);
        }
        const target = this.players.get(username);
        if (!target) throw new Error(`player not visible: ${username}`);
        held.count -= count;
        if (held.count === 0) this.rebuildSlots();
        // The toss lands at the target player's feet as a dropped-item entity.
        const drop: MockEntity = {
          id: this.nextEntityId++,
          name: "item",
          kind: "item",
          position: { ...target },
          itemName: item,
          itemCount: count,
        };
        this.entities.push(drop);
        this.emitEvent("item_dropped", { entity_id: drop.id, name: "item", item, count });
        return { item, count, target: username };
      }

      case "equip_item": {
        const { item } = action.arguments;
        const found = this.inventory.find((i) => i.name === item && i.count > 0);
        if (!found) throw new Error(`item not in inventory: ${item}`);
        this.equippedHand = { name: found.name, display_name: found.display_name };
        return { item };
      }

      case "wait": {
        await sleep(action.arguments.seconds * 1000);
        return {};
      }

      case "chat": {
        const { message } = action.arguments;
        this.emitEvent("chat", { username: this._username, message });
        return {};
      }
    }
  }

  // -------------------------------------------------------------------------
  // Internals
  // -------------------------------------------------------------------------

  private addToInventory(name: string, count: number): void {
    const existing = this.inventory.find((i) => i.name === name);
    if (existing) {
      existing.count += count;
    } else {
      this.inventory.push({ slot: -1, name, display_name: displayNameOf(name), count });
    }
    this.rebuildSlots();
  }

  /** Drop emptied stacks and renumber slots compactly. */
  private rebuildSlots(): void {
    this.inventory = this.inventory.filter((i) => i.count > 0);
    this.inventory.forEach((item, index) => {
      item.slot = index;
    });
  }

  private emitEvent(kind: RawEventKind, data: Record<string, unknown>): void {
    const event: RawGameEvent = {
      event_id: randomUUID(),
      timestamp: new Date().toISOString(),
      kind,
      data,
    };
    this.events.emit("event", event);
  }
}
