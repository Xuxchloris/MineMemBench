/**
 * High-level action handlers for the mineflayer-backed adapter.
 * High-level actions only — no keyboard-level control.
 * Every handler throws on failure; the adapter maps that to ActionResult.
 */
import type { Bot } from "mineflayer";
import { goals } from "mineflayer-pathfinder";
import type { Entity } from "prismarine-entity";
import { sleep, type ActionContext } from "./adapter";
import type {
  AttackEntityArgs,
  ChatArgs,
  CollectItemArgs,
  EquipItemArgs,
  FollowPlayerArgs,
  GiveItemArgs,
  MoveToArgs,
  WaitArgs,
} from "./protocol";

const VISIBILITY_RADIUS = 32;
/** Distance at which the bot can melee a target. */
const MELEE_RANGE = 3;

/** move_to: pathfind to within 1 block of target; failed if unreachable. */
export async function moveTo(bot: Bot, args: MoveToArgs): Promise<Record<string, unknown>> {
  // goto() rejects (NoPath / Timeout / PathStopped / GoalChanged) on failure.
  await bot.pathfinder.goto(new goals.GoalNear(args.x, args.y, args.z, 1));
  const p = bot.entity.position;
  return { position: { x: p.x, y: p.y, z: p.z } };
}

/** follow_player: single approach to within `distance` of a visible player. */
export async function followPlayer(bot: Bot, args: FollowPlayerArgs): Promise<Record<string, unknown>> {
  const target = bot.players[args.username]?.entity;
  if (!target?.position) throw new Error(`player not visible: ${args.username}`);
  const p = target.position;
  await bot.pathfinder.goto(new goals.GoalNear(p.x, p.y, p.z, args.distance));
  return {};
}

function findAttackTarget(bot: Bot, args: AttackEntityArgs): Entity | null {
  const me = bot.entity;
  const matches = Object.values(bot.entities)
    .filter((e): e is Entity => e !== undefined && e !== me && e.position !== undefined)
    .filter((e) => e.type !== "player" && e.name !== "item")
    .filter((e) => (args.entity_id !== undefined ? e.id === args.entity_id : e.name === args.name))
    .filter((e) => me.position.distanceTo(e.position) <= VISIBILITY_RADIUS)
    .sort((a, b) => me.position.distanceTo(a.position) - me.position.distanceTo(b.position));
  return matches[0] ?? null;
}

/** attack_entity: attack nearest match until it dies/disappears or timeout. */
export async function attackEntity(
  bot: Bot,
  args: AttackEntityArgs,
  ctx: ActionContext,
): Promise<Record<string, unknown>> {
  const target = findAttackTarget(bot, args);
  if (!target) {
    throw new Error(`no matching entity (name=${args.name ?? "-"}, entity_id=${args.entity_id ?? "-"})`);
  }
  const entityName = target.name ?? String(target.id);

  while (Date.now() < ctx.deadline) {
    const current = bot.entities[target.id];
    if (!current?.isValid) {
      return { entity_name: entityName, killed: true };
    }
    if (bot.entity.position.distanceTo(current.position) > MELEE_RANGE) {
      bot.pathfinder.setGoal(new goals.GoalFollow(current, 2), true);
      await sleep(200);
    } else {
      bot.pathfinder.stop();
      await bot.lookAt(current.position.offset(0, current.height, 0)).catch(() => undefined);
      bot.attack(current);
      await sleep(300);
    }
  }
  throw new Error(`attack on '${entityName}' did not finish in time`);
}

function countInInventory(bot: Bot, name: string): number {
  return bot.inventory
    .items()
    .filter((i) => i.name === name)
    .reduce((sum, i) => sum + i.count, 0);
}

function nearestDroppedItem(bot: Bot, name: string, maxDistance: number): Entity | null {
  const me = bot.entity;
  const matches = Object.values(bot.entities)
    .filter((e): e is Entity => e !== undefined && e.position !== undefined)
    .filter((e) => e.name === "item" && e.getDroppedItem()?.name === name)
    .filter((e) => me.position.distanceTo(e.position) <= maxDistance)
    .sort((a, b) => me.position.distanceTo(a.position) - me.position.distanceTo(b.position));
  return matches[0] ?? null;
}

/** collect_item: walk to the nearest matching dropped item and pick it up. */
export async function collectItem(
  bot: Bot,
  args: CollectItemArgs,
  ctx: ActionContext,
): Promise<Record<string, unknown>> {
  const before = countInInventory(bot, args.name);

  while (Date.now() < ctx.deadline) {
    const target = nearestDroppedItem(bot, args.name, args.max_distance);
    if (!target) {
      if (countInInventory(bot, args.name) > before) {
        return { item_name: args.name, collected: true };
      }
      throw new Error(`no dropped item '${args.name}' within ${args.max_distance} blocks`);
    }
    try {
      const p = target.position;
      await bot.pathfinder.goto(new goals.GoalNear(p.x, p.y, p.z, 1));
    } catch {
      // Pathing hiccup — retry while the deadline allows.
    }
    // Give the server a moment to register the pickup.
    const pickupWindow = Math.min(Date.now() + 1000, ctx.deadline);
    while (Date.now() < pickupWindow) {
      if (countInInventory(bot, args.name) > before) {
        return { item_name: args.name, collected: true };
      }
      if (!bot.entities[target.id]?.isValid) break; // gone but not ours — rescan
      await sleep(100);
    }
  }
  if (countInInventory(bot, args.name) > before) {
    return { item_name: args.name, collected: true };
  }
  throw new Error(`collect_item '${args.name}' did not finish in time`);
}

/** give_item: toss `count` of `item` from own inventory toward the player. */
export async function giveItem(bot: Bot, args: GiveItemArgs): Promise<Record<string, unknown>> {
  const target = bot.players[args.username]?.entity;
  if (!target?.position) throw new Error(`player not visible: ${args.username}`);
  const stack = bot.inventory.items().find((i) => i.name === args.item);
  if (!stack || stack.count < args.count) {
    throw new Error(`item not in inventory: ${args.item} (need ${args.count})`);
  }
  await bot.lookAt(target.position.offset(0, target.height, 0)).catch(() => undefined);
  await bot.toss(stack.type, stack.metadata, args.count);
  return { item: args.item, count: args.count, target: args.username };
}

/** equip_item: equip an inventory item into the hand. */
export async function equipItem(bot: Bot, args: EquipItemArgs): Promise<Record<string, unknown>> {
  const stack = bot.inventory.items().find((i) => i.name === args.item);
  if (!stack) throw new Error(`item not in inventory: ${args.item}`);
  await bot.equip(stack, args.destination);
  return { item: args.item };
}

/** wait: do nothing for the given number of seconds. */
export async function wait(_bot: Bot, args: WaitArgs): Promise<Record<string, unknown>> {
  await sleep(args.seconds * 1000);
  return {};
}

/** chat: send a public chat message. */
export async function chat(bot: Bot, args: ChatArgs): Promise<Record<string, unknown>> {
  bot.chat(args.message);
  return {};
}
