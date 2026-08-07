/**
 * BotAdapter: the adapter contract shared by the real mineflayer-backed
 * adapter and the deterministic mock adapter, plus a shared helper that runs
 * one action and packages the outcome as a protocol ActionResult.
 */
import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";
import type { ActionRequest, ActionResult, ActionStatus, Mode, WorldState } from "./protocol";

export interface BotAdapter {
  /** "minecraft" for the real bot, "mock" for the simulated one. */
  readonly mode: Mode;
  /** Bot username once known, otherwise the configured (or null) value. */
  readonly username: string | null;
  /** Emits "event" with a RawGameEvent payload (raw, uninterpreted). */
  readonly events: EventEmitter;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
  isConnected(): boolean;
  getState(): Promise<WorldState>;
  /**
   * Execute one already-validated action. Never rejects for ordinary action
   * failures — failures are reported via ActionResult.status instead.
   */
  execute(action: ActionRequest, timeoutMs: number): Promise<ActionResult>;
}

/** Rejection marker used to distinguish timeouts from ordinary failures. */
export class ActionTimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ActionTimeoutError";
  }
}

export interface ActionContext {
  /** Epoch ms by which the action should give up (for internal loops). */
  deadline: number;
}

export type ActionHandler = (ctx: ActionContext) => Promise<Record<string, unknown> | null>;

export interface ExecuteActionOptions {
  action: ActionRequest;
  timeoutMs: number;
  run: ActionHandler;
  getState: () => Promise<WorldState>;
  /** Best-effort cancellation hook fired when the timeout wins the race. */
  onTimeout?: () => void;
}

/**
 * Runs `run` with a hard timeout wall and builds the protocol ActionResult.
 * `state_after` is captured after the action settles (success, failure or
 * timeout), per the protocol contract.
 */
export async function executeAction(opts: ExecuteActionOptions): Promise<ActionResult> {
  const startedAt = new Date();
  const deadline = startedAt.getTime() + opts.timeoutMs;

  let status: ActionStatus;
  let result: Record<string, unknown> | null = null;
  let error: string | null = null;

  let timer: NodeJS.Timeout | undefined;
  try {
    const timeout = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        try {
          opts.onTimeout?.();
        } catch {
          // Cancellation is best-effort; never mask the timeout itself.
        }
        reject(new ActionTimeoutError(`action '${opts.action.action}' timed out after ${opts.timeoutMs} ms`));
      }, opts.timeoutMs);
    });
    result = await Promise.race([opts.run({ deadline }), timeout]);
    status = "completed";
  } catch (err) {
    if (err instanceof ActionTimeoutError) {
      status = "timeout";
      error = err.message;
    } else {
      status = "failed";
      error = err instanceof Error ? err.message : String(err);
    }
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }

  return {
    action_id: randomUUID(),
    action: opts.action.action,
    status,
    started_at: startedAt.toISOString(),
    finished_at: new Date().toISOString(),
    result,
    error,
    state_after: await opts.getState(),
  };
}

/** Small shared helper: promise-based sleep used by wait/collect handlers. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
