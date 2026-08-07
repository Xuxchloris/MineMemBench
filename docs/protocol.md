# Bot Bridge Protocol (v1)

Single source of truth for the contract between the TypeScript Minecraft adapter
(`minecraft/`) and the Python benchmark core (`benchmark/minemembench/`).
Both sides MUST validate payloads against these schemas (zod on TS, pydantic on Python).

Transport: HTTP JSON for request/response + WebSocket for the raw event stream.
Default port: `8081` (env `BOT_API_PORT`).

## Endpoints

### `GET /health`
```json
{
  "status": "ok",
  "mode": "minecraft" | "mock",
  "connected": true,
  "username": "BenchBot" | null,
  "uptime_s": 12.3
}
```

### `GET /state` → `WorldState`
```json
{
  "timestamp": "ISO-8601 string",
  "mode": "minecraft" | "mock",
  "username": "BenchBot",
  "health": 20.0,
  "food": 20,
  "saturation": 5.0,
  "oxygen": 20,
  "position": { "x": 0.0, "y": 64.0, "z": 0.0 },
  "yaw": 0.0,
  "pitch": 0.0,
  "dimension": "minecraft:overworld",
  "time_of_day": 6000,
  "is_raining": false,
  "experience_level": 0,
  "inventory": [
    { "slot": 0, "name": "stone", "display_name": "Stone", "count": 12 }
  ],
  "equipped": {
    "hand": { "name": "stone_sword", "display_name": "Stone Sword" }
  },
  "nearby_entities": [
    {
      "id": 123,
      "name": "zombie",
      "display_name": "Zombie",
      "kind": "hostile" | "passive" | "player" | "item" | "other",
      "position": { "x": 1.0, "y": 64.0, "z": 2.0 },
      "distance": 3.2
    }
  ],
  "nearby_players": [
    {
      "username": "Steve",
      "position": { "x": 1.0, "y": 64.0, "z": 2.0 },
      "distance": 2.0
    }
  ]
}
```
Rules: `equipped.hand` may be `null`. `nearby_entities` excludes player entities
(they are in `nearby_players`) and is sorted by `distance` ascending, max 32 entries,
max radius 32 blocks. Distances in blocks, 1 decimal.

### `POST /action`
Request:
```json
{ "action": "move_to", "arguments": { "x": 10, "y": 64, "z": 10 }, "timeout_ms": 30000 }
```
`timeout_ms` optional, default 30000, max 120000. Actions execute strictly serially
(server-side FIFO queue).

Response: `ActionResult` (HTTP 200 even when the action failed; check `status`)
```json
{
  "action_id": "uuid",
  "action": "move_to",
  "status": "completed" | "failed" | "timeout",
  "started_at": "ISO-8601",
  "finished_at": "ISO-8601",
  "result": { "position": { "x": 10.0, "y": 64.0, "z": 10.0 } },
  "error": null,
  "state_after": { "...": "WorldState" }
}
```
`result` is null on failure; `error` is a human-readable string or null.
HTTP 400 = invalid request body; HTTP 503 = bot not connected.

### Supported actions and arguments

| action | arguments | result fields |
|---|---|---|
| `move_to` | `{x, y, z}` (numbers) | `{position}` |
| `follow_player` | `{username: str, distance?: number=2}` | `{}` |
| `attack_entity` | `{name?: str, entity_id?: int}` (one required) | `{entity_name, killed: bool}` |
| `collect_item` | `{name: str, max_distance?: number=16}` | `{item_name, collected: bool}` |
| `give_item` | `{username: str, item: str, count?: int=1}` | `{item, count, target}` |
| `equip_item` | `{item: str, destination?: "hand"="hand"}` | `{item}` |
| `wait` | `{seconds: number}` (0.1–60) | `{}` |
| `chat` | `{message: str}` (≤256 chars) | `{}` |

Semantics:
- `move_to`: pathfind to within 1 block of target; `failed` if unreachable.
- `follow_player`: moves within `distance` of the named player once (not a continuous
  follow); `failed` if player not visible.
- `attack_entity`: attacks nearest matching entity until it dies/disappears or timeout.
- `collect_item`: walks to the nearest matching dropped item entity.
- `give_item`: tosses `count` of `item` from own inventory toward the player;
  `failed` if not in inventory. Does NOT use `/give` cheats.
- `chat`: sends a public chat message.

### `GET /events` (WebSocket)
Server sends, for each raw game event:
```json
{
  "type": "event",
  "event": {
    "event_id": "uuid",
    "timestamp": "ISO-8601",
    "kind": "chat" | "player_joined" | "player_left" | "entity_hurt" | "entity_dead"
          | "health" | "death" | "item_dropped" | "message",
    "data": { "...": "kind-specific fields, raw and uninterpreted" }
  }
}
```
On connect the server sends `{"type": "hello", "mode": ..., "username": ...}`.
These are RAW events. Semantic interpretation (`ExperienceEvent`) happens on the
Python side; the TS adapter must not annotate meaning.

## Versioning
Any breaking change bumps the protocol version in this file's title and must be
reflected on both sides in the same commit.
