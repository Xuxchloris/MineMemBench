/**
 * Wires mineflayer bot events to protocol RawGameEvents.
 * RAW data only — semantic interpretation happens on the Python side,
 * so this layer must not annotate meaning.
 */
import type { Bot } from "mineflayer";
import type { RawEventKind } from "./protocol";

export type RawEventSink = (kind: RawEventKind, data: Record<string, unknown>) => void;

export function wireBotEvents(bot: Bot, emit: RawEventSink): void {
  bot.on("chat", (username, message) => {
    emit("chat", { username, message });
  });

  // System/game messages (non-player chat), forwarded as raw text.
  bot.on("messagestr", (message, position) => {
    emit("message", { message, position });
  });

  bot.on("playerJoined", (player) => {
    emit("player_joined", { username: player?.username ?? null });
  });

  bot.on("playerLeft", (player) => {
    emit("player_left", { username: player?.username ?? null });
  });

  bot.on("entityHurt", (entity) => {
    emit("entity_hurt", { entity_id: entity?.id ?? null, name: entity?.name ?? null });
  });

  bot.on("entityDead", (entity) => {
    emit("entity_dead", { entity_id: entity?.id ?? null, name: entity?.name ?? null });
  });

  bot.on("itemDrop", (entity) => {
    emit("item_dropped", { entity_id: entity?.id ?? null, name: entity?.name ?? null });
  });

  bot.on("health", () => {
    emit("health", { health: bot.health, food: bot.food, saturation: bot.foodSaturation });
  });

  bot.on("death", () => {
    const p = bot.entity?.position;
    emit("death", { position: p ? { x: p.x, y: p.y, z: p.z } : null });
  });
}
