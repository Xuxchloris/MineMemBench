/**
 * Zod schemas + inferred TypeScript types for the Bot Bridge Protocol (v1).
 * Mirrors docs/protocol.md exactly — any breaking change must bump the
 * protocol version there and be reflected on the Python side in the same commit.
 */
import { z } from "zod";

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

export const ModeSchema = z.enum(["minecraft", "mock"]);
export type Mode = z.infer<typeof ModeSchema>;

export const Vec3Schema = z.strictObject({
  x: z.number(),
  y: z.number(),
  z: z.number(),
});
export type Vec3 = z.infer<typeof Vec3Schema>;

// ---------------------------------------------------------------------------
// GET /state → WorldState
// ---------------------------------------------------------------------------

export const InventoryItemSchema = z.strictObject({
  slot: z.number().int(),
  name: z.string(),
  display_name: z.string(),
  count: z.number().int(),
});
export type InventoryItem = z.infer<typeof InventoryItemSchema>;

export const EquippedSchema = z.strictObject({
  hand: z
    .strictObject({
      name: z.string(),
      display_name: z.string(),
    })
    .nullable(),
});
export type Equipped = z.infer<typeof EquippedSchema>;

export const EntityKindSchema = z.enum(["hostile", "passive", "player", "item", "other"]);
export type EntityKind = z.infer<typeof EntityKindSchema>;

export const NearbyEntitySchema = z.strictObject({
  id: z.number().int(),
  name: z.string(),
  display_name: z.string(),
  kind: EntityKindSchema,
  position: Vec3Schema,
  distance: z.number(),
});
export type NearbyEntity = z.infer<typeof NearbyEntitySchema>;

export const NearbyPlayerSchema = z.strictObject({
  username: z.string(),
  position: Vec3Schema,
  distance: z.number(),
});
export type NearbyPlayer = z.infer<typeof NearbyPlayerSchema>;

export const WorldStateSchema = z.strictObject({
  timestamp: z.string(), // ISO-8601
  mode: ModeSchema,
  username: z.string().nullable(),
  health: z.number(),
  food: z.number(),
  saturation: z.number(),
  oxygen: z.number(),
  position: Vec3Schema,
  yaw: z.number(),
  pitch: z.number(),
  dimension: z.string(),
  time_of_day: z.number(),
  is_raining: z.boolean(),
  experience_level: z.number().int(),
  inventory: z.array(InventoryItemSchema),
  equipped: EquippedSchema,
  nearby_entities: z.array(NearbyEntitySchema),
  nearby_players: z.array(NearbyPlayerSchema),
});
export type WorldState = z.infer<typeof WorldStateSchema>;

// ---------------------------------------------------------------------------
// POST /action → ActionRequest
// ---------------------------------------------------------------------------

export const TIMEOUT_MS_DEFAULT = 30_000;
export const TIMEOUT_MS_MAX = 120_000;

export const MoveToArgsSchema = z.strictObject({
  x: z.number(),
  y: z.number(),
  z: z.number(),
});
export type MoveToArgs = z.infer<typeof MoveToArgsSchema>;

export const FollowPlayerArgsSchema = z.strictObject({
  username: z.string().min(1),
  distance: z.number().positive().default(2),
});
export type FollowPlayerArgs = z.infer<typeof FollowPlayerArgsSchema>;

export const AttackEntityArgsSchema = z
  .strictObject({
    name: z.string().min(1).optional(),
    entity_id: z.number().int().optional(),
  })
  .refine((a) => a.name !== undefined || a.entity_id !== undefined, {
    message: "attack_entity requires one of: name, entity_id",
  });
export type AttackEntityArgs = z.infer<typeof AttackEntityArgsSchema>;

export const CollectItemArgsSchema = z.strictObject({
  name: z.string().min(1),
  max_distance: z.number().positive().default(16),
});
export type CollectItemArgs = z.infer<typeof CollectItemArgsSchema>;

export const GiveItemArgsSchema = z.strictObject({
  username: z.string().min(1),
  item: z.string().min(1),
  count: z.number().int().positive().default(1),
});
export type GiveItemArgs = z.infer<typeof GiveItemArgsSchema>;

export const EquipItemArgsSchema = z.strictObject({
  item: z.string().min(1),
  destination: z.literal("hand").default("hand"),
});
export type EquipItemArgs = z.infer<typeof EquipItemArgsSchema>;

export const WaitArgsSchema = z.strictObject({
  seconds: z.number().min(0.1).max(60),
});
export type WaitArgs = z.infer<typeof WaitArgsSchema>;

export const ChatArgsSchema = z.strictObject({
  message: z.string().min(1).max(256),
});
export type ChatArgs = z.infer<typeof ChatArgsSchema>;

const timeoutField = z.number().int().positive().max(TIMEOUT_MS_MAX).default(TIMEOUT_MS_DEFAULT);

/**
 * A plain union (not discriminatedUnion) so the refined attack_entity schema
 * stays a member; every variant still carries a literal `action` tag, so
 * narrowing on `action.action` works after parsing.
 */
export const ActionRequestSchema = z.union([
  z.strictObject({ action: z.literal("move_to"), arguments: MoveToArgsSchema, timeout_ms: timeoutField }),
  z.strictObject({ action: z.literal("follow_player"), arguments: FollowPlayerArgsSchema, timeout_ms: timeoutField }),
  z.strictObject({ action: z.literal("attack_entity"), arguments: AttackEntityArgsSchema, timeout_ms: timeoutField }),
  z.strictObject({ action: z.literal("collect_item"), arguments: CollectItemArgsSchema, timeout_ms: timeoutField }),
  z.strictObject({ action: z.literal("give_item"), arguments: GiveItemArgsSchema, timeout_ms: timeoutField }),
  z.strictObject({ action: z.literal("equip_item"), arguments: EquipItemArgsSchema, timeout_ms: timeoutField }),
  z.strictObject({ action: z.literal("wait"), arguments: WaitArgsSchema, timeout_ms: timeoutField }),
  z.strictObject({ action: z.literal("chat"), arguments: ChatArgsSchema, timeout_ms: timeoutField }),
]);
export type ActionRequest = z.infer<typeof ActionRequestSchema>;
export type ActionName = ActionRequest["action"];

// ---------------------------------------------------------------------------
// POST /action ← ActionResult
// ---------------------------------------------------------------------------

export const ActionStatusSchema = z.enum(["completed", "failed", "timeout"]);
export type ActionStatus = z.infer<typeof ActionStatusSchema>;

export const ActionResultSchema = z.strictObject({
  action_id: z.string(),
  action: z.string(),
  status: ActionStatusSchema,
  started_at: z.string(), // ISO-8601
  finished_at: z.string(), // ISO-8601
  result: z.record(z.string(), z.unknown()).nullable(),
  error: z.string().nullable(),
  state_after: WorldStateSchema,
});
export type ActionResult = z.infer<typeof ActionResultSchema>;

// ---------------------------------------------------------------------------
// GET /health
// ---------------------------------------------------------------------------

export const HealthResponseSchema = z.strictObject({
  status: z.literal("ok"),
  mode: ModeSchema,
  connected: z.boolean(),
  username: z.string().nullable(),
  uptime_s: z.number(),
});
export type HealthResponse = z.infer<typeof HealthResponseSchema>;

// ---------------------------------------------------------------------------
// GET /events (WebSocket)
// ---------------------------------------------------------------------------

export const RawEventKindSchema = z.enum([
  "chat",
  "player_joined",
  "player_left",
  "entity_hurt",
  "entity_dead",
  "health",
  "death",
  "item_dropped",
  "message",
]);
export type RawEventKind = z.infer<typeof RawEventKindSchema>;

export const RawGameEventSchema = z.strictObject({
  event_id: z.string(),
  timestamp: z.string(), // ISO-8601
  kind: RawEventKindSchema,
  data: z.record(z.string(), z.unknown()), // raw, uninterpreted fields
});
export type RawGameEvent = z.infer<typeof RawGameEventSchema>;

export const WsHelloSchema = z.strictObject({
  type: z.literal("hello"),
  mode: ModeSchema,
  username: z.string().nullable(),
});
export type WsHello = z.infer<typeof WsHelloSchema>;

export const WsEventMessageSchema = z.strictObject({
  type: z.literal("event"),
  event: RawGameEventSchema,
});
export type WsEventMessage = z.infer<typeof WsEventMessageSchema>;
