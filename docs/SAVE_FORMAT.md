# Campaign persistence

The current save version is **4.12**. New saves preserve the installed component
inventory and its configuration and runtime state. Loading does not reconstruct
current-format units from templates, so refits, removed components, empty weapon
bays, and changes to template files cannot silently change an existing ship.

Only version **4.12** is supported. Unversioned, older, unknown and future saves
are rejected with the expected version before hydration. Alpha schema changes
require a new campaign; no migrations or automatic conversions are provided.
Rejected files are never modified.

## Testing campaign catalogue

Loading any save uses the normal construction catalogue plus custom designs, even when the saved campaign started with the Testing profile. Existing Testing ships retain their saved components. The spawn profile is not persisted, and the save version is 4.12.

After order restoration on the isolated load candidate, active Testing-only construction is cancelled without promoting queued work. Recorded charges are refunded once to the original payer; orphaned jobs without recorded charges are rejected during validation. A load warning reports each cancellation. Queued Testing-only construction remains queued and fails through normal unavailable-template handling when attempted. Failed loads preserve the running campaign, its credits, and its active catalogue.

## Design validation

Campaign saves preserve installed equipment, HP, speed, field radii, component
hull costs and subsystem HP. Unit hull capacity follows current hull rules.
Changing catalogue balance does not rebuild saved ships from templates.

Custom design libraries must pass current equipment and field validation before
loading. Duplicate JSON keys, unknown fields, old field aliases and invalid designs
reject the entire library. A rejected load preserves the disk and registered
designs and blocks writes until a successful reload. Errors identify the template
and field to repair. Editing uses the same equipment rules; opening a design does
not repair it. See [design validation](REFERENCE.md#external-design-validation).

## Component and ability schemas

Saves include carrier participant IDs and deadlines, Attack Run and Emergency
Recovery phases, recovery launch locks and Flak phase markers. Commander roots
restore before carrier effects reconcile. Loading never replays activation costs,
salvos, docking or Flak damage. Antimatter Storage uses component schema 2 and
stores capacity and current fuel; passive regeneration is not part of the model.

Every registered component owns its persistence through `UnitComponent.to_state()`
and `restore_state()`. Each component declares its configuration, runtime fields,
object references, and owned children. Specialized codecs handle turrets,
abilities, and Commander orders. A component entry has this envelope:

```json
{
  "type": "Engines",
  "schema_version": 1,
  "hull_cost": 2.5,
  "current_hit_points": 3,
  "max_hit_points": 25,
  "configuration": {"speed": 50.0},
  "runtime": {}
}
```

Enums, positions, tuples, and sets use explicit JSON tags in `state_codec.py`.
Component names come from a registry; save data cannot import arbitrary classes.
Unknown types, unsupported schema versions, missing component fields, invalid
types, and non-finite or out-of-range numbers fail validation.

Weapons save the complete turret inventory, effective turret statistics, variants,
and current cooldowns. Restoration does not apply variant modifiers a second time.
Each ability has its own type and schema version, a saved definition, and separate
runtime state: active flag, cooldown, remaining duration, target ID/position, and
spawned-unit IDs. Restoration never calls ability activation.

Ability schema **2** adds `activation_mode` (`cast` or `toggle`) and
`ongoing_antimatter` to each definition. Loading validates these against the
registered ability; upkeep must also be finite and non-negative. Environmental
resistances persist their active flag with zero timers and no targets or
deployments. Active toggles survive loading when eligible, without payment or
activation replay. Ineligible toggles reconcile to disabled. No previous-save
migration is provided.

Tactical activation checks the current shared equipment requirements in
`tactical_balance.py`. Nebula Catalyst therefore requires operational Sensors and
Antimatter Storage even when a saved definition retains the historical Harvester
prerequisite. Loading preserves installed components, saved definitions and runtime
state.

Commander stores its stance in `configuration` and explicit `current_order` and
`orders_queue` in `runtime`. Public order UUIDs, descendants, charges/refunds, and
bounded outcome history remain persistent. Loading preserves the current/queued
split, including an empty current slot. Active orders rebind their actuators
without executing startup again. Transient stance engagement trees and their
actuators are reacquired through normal play.

`ATTACK_LONG_RANGE` uses the same order envelope as `ATTACK`, retaining its distinct
type, target/subsystem, UUID and approach descendants. Restoring it rebinds firing
and navigation without replaying execution. The save format remains 4.12.

When adding a component or ability, register it, declare every persistent field,
and extend its independent round-trip fixture. An incompatible schema change
advances the save version and the affected component schema. Only the current
versions are accepted.

## Transactional load

`campaign_persistence.prepare_campaign()` completes these steps on an isolated
candidate before changing the running game:

1. Parse JSON and reject duplicate keys, invalid values, and excessive nesting.
2. Require the current save version.
3. Validate the current document and hydrate players and the ownership graph.
4. Resolve references, rebuild derived state, and validate graph invariants.
5. Calculate allocator high-water marks and prepare the committed state.

`commit_campaign()` then installs the prepared graph without GUI or AI callbacks.
`Game.load_game()` resets and schedules AI and refreshes the interface only after
commit. A rejected save preserves the existing graph, selection, conversations,
global allocators, random state, and AI scheduling. A presentation failure after
commit is logged as a refresh failure; it is not reported as a rejected save.

Constructors use context-local counters while staging. Outside staging, the game
still uses process-global allocators; this implementation does not introduce
independent concurrently running campaigns.

## References, indexes, and timers

`campaign_graph.iter_objects()` follows ownership edges across celestial bodies,
minefields, deployed units, gas-giant storage, and recursively nested hangars and
strikecraft bays. Duplicate ownership, cycles, duplicate IDs, and inconsistent
container locations are invalid. Carrier links, targets, and agent sources are
references rather than additional ownership edges.

Reconciliation rebuilds celestial lookup tables, reciprocal wormhole links and
the system graph, static and dynamic inhibition zones, carrier/wing associations,
deployed-agent lists, homeworld mappings, and visibility. Visibility reconstruction
does not rewrite saved historical intel. Active deployed inhibitors block jumps
immediately after load. Invalid active zone geometry is rejected.

For objects, players, and agents the allocator becomes
`max(serialized_counter, observed_max_id + 1)`. The object scan includes minefields
and every stored unit. The message counter retains its existing last-issued-ID
convention and reconciles against saved messages.

Timed buffs/debuffs are owned by their source unit and ability. Hull status flags
are rebuilt from active instances, so one source expiring cannot remove another
source's contribution. Cleanup is idempotent on expiry, component destruction or
replacement/removal, source/target destruction, and load reconciliation. Expired
missile batteries remove their temporary platforms. Missing targets terminate
active targeted effects. Docked and hidden units still tick ability timers and
temporary lifetimes on their owner's turn; stored units do not apply ongoing
external ability actions.

## Verification

`tests/test_persistence_integrity.py` covers all 28 registered components and all
registered abilities, including non-default definitions and dynamically installed
components. Its canonical snapshot inspects runtime objects independently of the
serialization field declarations. It exercises a deliberately mutated mid-game
campaign through the actual file writer/reader, repeated loads, and idempotent
reconciliation. Separate tests cover unsupported format rejection, minefield IDs, queued
orders, paid construction/refit/replenishment, next-turn continuation, overlapping
effects, stored timers, and injected failures throughout loading.

Run the regression suite from the repository root:

```powershell
./.venv/Scripts/python.exe -m pytest -q -o cache_dir=.codex_test_cache
```

## Tactical state

Each sector stores `deployables` and `catalyst_patches` arrays. Deployables store
owner, immutable historical deploying-ship ID, ghost-emitter kind, position, HP
and identification. Emitters have no lifetime or expiry field.
Patches store original owner, source ID, nebula ID, radius and finite deadline.

New ability runtime persists owner-round readiness/expiry deadlines, active
targets, source allegiance, processed pull phase and Guardian split/cap/mitigation
tuning. Antimatter exchange, depot transport, and celestial-targeted orders retain typed references and UUIDs.
Loading restores these without activation, fuel charges, spawns or repeated pulls,
and reconciles expired effects according to each owner's last started turn.

Counts are rebuilt galaxy-wide from surviving objects. Source destruction, capture
and equipment changes do not erase provenance or reset caps. Duplicate object IDs
and invalid patch references are rejected. Historical deploying-ship references
may point to destroyed units; they still raise the object allocator's high-water
mark so their IDs cannot be reused. See `tests/test_tactical_abilities.py` for
independent gameplay, round-trip and fake-provider acceptance coverage.


## Retrofit settlement

Active Constructor refit jobs persist `payer_id` and `salvage_due` alongside the
existing target, action, configuration, paid installation cost and duration. The
original order retains its charge ownership. A valid completed removal grants
salvage once; failed or cancelled new removals grant none. Installation validation
failures and cancellation refund the paid charge once to its original payer.

All jobs restore their recorded payer, salvage, costs and progress. Loading does not
recharge a job, apply equipment changes, or reject historical equipment merely
because it fails current Designer rules. Active jobs are revalidated against the
complete resulting equipment when they complete. Pending jobs use current rules
and prices when they start. No new retrofit AI or socket command is introduced.


## Turn briefings

Save 4.12 requires each player's `briefing` state: initialization/collection flags,
reporting boundary, event sequence, bounded pending entries and omission count,
economic baseline, discovery keys, frozen current report and human acknowledgement.
The current report contains its start/end rounds, grouped entries, net economy
changes and omission count. Reports and pending collections are limited to 128
entries and 32,000 serialized characters including reserved report overhead.

The loader validates field shapes, flags, finite amounts, counters, locations and
retention limits on the isolated candidate. Historical references may identify
objects that no longer exist and are not rebound to live targets. Hydration does
not emit briefing events or refresh the frozen report. An unacknowledged human
report reopens after load; an acknowledged one remains available from Turn Summary.
Unsupported saves, including 4.4, require a new campaign.

## Antimatter state

Unit schema 3 requires nonnegative integer `multiply_cast_ready_round` and
`multiply_receive_ready_round` fields, including for docked units and units with
no Ability component. They survive equipment replacement and ownership changes.
New units initialize both to zero. A successful pulse at round R sets the caster
deadline and each positive recipient's shared deadline to R + 30. Loading never
replays the pulse or its 20 AM charge.

`TAKE_ANTIMATTER` and `TRANSFER_ANTIMATTER` persist typed target references.
`CONTINUOUS_ANTIMATTER_TRANSPORT` stores `source_unit_id` and nullable
`target_unit_id`; `CONTINUOUS_RESUPPLY` stores typed `source_body_id` and nullable
`target_unit_id`. Null targets mean Automatic; non-null targets mean Manual.
Both require runtime `active_destination_unit_id` (nullable and separate from the
configured target), phase, bounded waiting reason, return reserve, and an active
approach subtree. Source phases are `loading` for transport and `harvesting` for
resupply; both use `delivering`. Waiting reasons are null, `source_empty`,
`destination_full`, `insufficient_load`, or `no_destination`. Movement children
retain a private location anchor to follow moving depots after restoration.

Loading resumes without extra transfer ticks, recipient selection, or harvesting.
Invalid IDs, phases, reserves, and inconsistent manual active recipients reject
transactionally. Save 4.12 is required; older saves and legacy resupply source
fields have no migration or aliases. Fuel-cache deployables, recovery orders and
the old ability identifier remain unsupported.


## Planetary warfare state

Save 4.12 uses unit schema 3. Every unit stores the nonnegative integer
`last_planetary_action_round`, bounded by the saved campaign round. This survives
refits, cancellation and capture, preventing replay or an extra action after load.
Troop Transport schema 1 stores integer `capacity` and current `troops`; destroyed
cargo must contain zero troops. Siege Battery schema 1 uses fixed siege rules.

Planets, moons and colonizable asteroids require `fortification_level` (0–3),
`defense_readiness` (0.25–1), `last_hostile_action_round` and
`last_defense_upgrade_round` (nonnegative integers no later than the saved round).
The campaign stores tagged `invasion_rng_state`, restored into an independent
`random.Random`. Invalid colony, cargo, RNG or action-marker state rejects the
whole candidate transactionally.

The three planetary orders preserve typed targets, amounts, UUIDs and approach
subtrees through ordinary order serialization. Restore does not recruit, charge,
bombard or roll. The next End Turn rechecks authoritative eligibility; completed
orders and unit markers prevent repeated attacks. Identical restored state and
action sequences produce identical invasion rolls. Older saves, including 4.7,
are unsupported under the Alpha policy.

## Wormhole support state

Format 4.12 registers `WormholeStabilizerComponent` and `STABILIZE_WORMHOLE`.
The component stores its last paid round and payer ID; the order stores its typed
wormhole target, normal UUID/approach descendants, powered flag and phase.
Coverage is derived from live eligible maintainers after references restore.
Loading does not charge fuel, advance orders or modify natural wormhole stability.
Invalid payment/state values reject the candidate; ineligible support reconciles
to unpowered. Only 4.12 is supported; older saves require a new campaign.


## Fixed destination validation

Save 4.12 requires complete fixed destinations recursively in positional orders
and patrol waypoints. System names must resolve, hexes must exist and use integer
coordinates, and positions must contain finite numbers. Missing coordinates are
never replaced with a unit's location. Constructor component schema 3 stores its
active job as `template_name`, `system_name`, `hex_coord`, `position`,
`turret_type_override` and `defense_type_override`, with the
existing progress, charge and owning-order identity. Loading rejects a job without
a matching active Construct order; site validation does not charge, refund, or replay execution.
Older save versions and Constructor schemas are rejected without migration.

Both override fields are present and nullable in saved Construct parameters and
active jobs. Non-null values must be supported weapon/defense choices, and active
job choices must match the owning Construct order. Pending and approaching orders
retain their choices; loading never restarts construction or charges again.
Completed ships persist their actual equipment through existing Weapons and
Defenses component state, without reconstructing it from the catalogue.
