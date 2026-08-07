/**
 * Builds the protocol WorldState snapshot from a live mineflayer bot.
 */
import type { Bot } from "mineflayer";
import type { Entity } from "prismarine-entity";
import type { EntityKind, Mode, NearbyEntity, NearbyPlayer, Vec3, WorldState } from "./protocol";

const NEARBY_RADIUS = 32;
const NEARBY_MAX_ENTRIES = 32;

function toVec3(p: { x: number; y: number; z: number }): Vec3 {
  return { x: p.x, y: p.y, z: p.z };
}

function distance(a: Vec3, b: Vec3): number {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2);
}

/** Protocol rule: distances in blocks, 1 decimal. */
function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

function entityKind(entity: Entity): EntityKind {
  if (entity.name === "item") return "item";
  if (entity.type === "player") return "player";
  // prismarine-entity `kind` is a minecraft-data category like "Hostile mobs".
  const kind = (entity.kind ?? "").toLowerCase();
  if (kind.includes("hostile")) return "hostile";
  if (kind.includes("passive")) return "passive";
  return "other";
}

/** mineflayer reports e.g. "overworld"; the protocol uses namespaced ids. */
function dimensionId(raw: string): string {
  return raw.includes(":") ? raw : `minecraft:${raw}`;
}

export function buildWorldState(bot: Bot, mode: Mode, username: string | null): WorldState {
  const me = bot.entity;
  const position: Vec3 = me?.position ? toVec3(me.position) : { x: 0, y: 0, z: 0 };

  const nearbyEntities: NearbyEntity[] = Object.values(bot.entities)
    .filter((e): e is Entity => e !== undefined && e !== me && e.position !== undefined)
    .filter((e) => e.type !== "player") // players live in nearby_players
    .map((e) => ({ e, d: round1(distance(position, toVec3(e.position))) }))
    .filter(({ d }) => d <= NEARBY_RADIUS)
    .sort((a, b) => a.d - b.d)
    .slice(0, NEARBY_MAX_ENTRIES)
    .map(({ e, d }) => ({
      id: e.id,
      name: e.name ?? "unknown",
      display_name: e.displayName ?? e.name ?? "Unknown",
      kind: entityKind(e),
      position: toVec3(e.position),
      distance: d,
    }));

  const nearbyPlayers: NearbyPlayer[] = Object.values(bot.players)
    .filter((p) => p.username !== bot.username && p.entity?.position !== undefined)
    .map((p) => ({ p, d: round1(distance(position, toVec3(p.entity.position))) }))
    .filter(({ d }) => d <= NEARBY_RADIUS)
    .sort((a, b) => a.d - b.d)
    .map(({ p, d }) => ({
      username: p.username,
      position: toVec3(p.entity.position),
      distance: d,
    }));

  const held = bot.heldItem;

  return {
    timestamp: new Date().toISOString(),
    mode,
    username,
    health: bot.health,
    food: bot.food,
    saturation: bot.foodSaturation,
    oxygen: bot.oxygenLevel ?? 20,
    position,
    yaw: me?.yaw ?? 0,
    pitch: me?.pitch ?? 0,
    dimension: dimensionId(String(bot.game?.dimension ?? "overworld")),
    time_of_day: Number(bot.time?.timeOfDay ?? 0),
    is_raining: bot.isRaining,
    experience_level: bot.experience?.level ?? 0,
    inventory: bot.inventory.items().map((item) => ({
      slot: item.slot,
      name: item.name,
      display_name: item.displayName,
      count: item.count,
    })),
    equipped: {
      hand: held ? { name: held.name, display_name: held.displayName } : null,
    },
    nearby_entities: nearbyEntities,
    nearby_players: nearbyPlayers,
  };
}
