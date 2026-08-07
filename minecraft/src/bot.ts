/**
 * MineflayerAdapter: BotAdapter backed by a real mineflayer bot with the
 * pathfinder plugin. Connects to a Java Edition server in offline auth mode
 * (the benchmark runs its own local server with ONLINE_MODE=FALSE).
 */
import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";
import { createBot, type Bot } from "mineflayer";
import { Movements, pathfinder } from "mineflayer-pathfinder";
import { executeAction, type ActionContext, type BotAdapter } from "./adapter";
import { attackEntity, chat, collectItem, equipItem, followPlayer, giveItem, moveTo, wait } from "./actions";
import { wireBotEvents } from "./events";
import { buildWorldState } from "./state";
import type { ActionRequest, ActionResult, RawEventKind, RawGameEvent, WorldState } from "./protocol";

export interface MineflayerAdapterOptions {
  host: string;
  port: number;
  username: string;
  version: string;
}

export class MineflayerAdapter implements BotAdapter {
  readonly mode = "minecraft" as const;
  readonly events = new EventEmitter();

  private bot: Bot | null = null;
  private connected = false;

  constructor(private readonly options: MineflayerAdapterOptions) {}

  get username(): string | null {
    return this.bot?.username ?? this.options.username;
  }

  isConnected(): boolean {
    return this.connected;
  }

  connect(): Promise<void> {
    const bot = createBot({
      host: this.options.host,
      port: this.options.port,
      username: this.options.username,
      version: this.options.version,
      auth: "offline",
    });
    this.bot = bot;
    bot.loadPlugin(pathfinder);
    wireBotEvents(bot, (kind, data) => this.emitEvent(kind, data));

    // Persistent lifecycle listeners. Reconnect is intentionally not
    // implemented — the benchmark treats a disconnect as episode failure.
    bot.on("end", () => {
      this.connected = false;
    });
    bot.on("error", (err) => {
      // Log but do not crash: connection errors surface via isConnected().
      console.error("[mineflayer] bot error:", err.message);
    });

    return new Promise<void>((resolve, reject) => {
      bot.once("spawn", () => {
        bot.pathfinder.setMovements(new Movements(bot));
        this.connected = true;
        resolve();
      });
      bot.once("kicked", (reason) => reject(new Error(`kicked from server: ${reason}`)));
      bot.once("end", () => reject(new Error("connection ended before spawn")));
    });
  }

  async disconnect(): Promise<void> {
    this.connected = false;
    this.bot?.quit();
  }

  async getState(): Promise<WorldState> {
    const bot = this.requireBot();
    return buildWorldState(bot, this.mode, this.username);
  }

  execute(action: ActionRequest, timeoutMs: number): Promise<ActionResult> {
    return executeAction({
      action,
      timeoutMs,
      run: (ctx) => this.dispatch(action, ctx),
      getState: () => this.getState(),
      onTimeout: () => {
        // Best-effort halt so a timed-out movement does not keep running.
        this.bot?.pathfinder.stop();
        this.bot?.clearControlStates();
      },
    });
  }

  private dispatch(action: ActionRequest, ctx: ActionContext): Promise<Record<string, unknown> | null> {
    const bot = this.requireBot();
    switch (action.action) {
      case "move_to":
        return moveTo(bot, action.arguments);
      case "follow_player":
        return followPlayer(bot, action.arguments);
      case "attack_entity":
        return attackEntity(bot, action.arguments, ctx);
      case "collect_item":
        return collectItem(bot, action.arguments, ctx);
      case "give_item":
        return giveItem(bot, action.arguments);
      case "equip_item":
        return equipItem(bot, action.arguments);
      case "wait":
        return wait(bot, action.arguments);
      case "chat":
        return chat(bot, action.arguments);
    }
  }

  private requireBot(): Bot {
    if (!this.bot || !this.connected) throw new Error("bot not connected");
    return this.bot;
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
