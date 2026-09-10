# Campaign persistence

The current save version is **4.1**. New saves preserve the installed component
inventory and its configuration and runtime state. Loading does not reconstruct
current-format units from templates, so refits, removed components, empty weapon
bays, and changes to template files cannot silently change an existing ship.

## Testing campaign catalogue

Loading any save uses the normal construction catalogue plus custom designs, even when the saved campaign started with the Testing profile. Existing Testing ships retain their saved components. The spawn profile is not persisted, and the save version remains 4.1.

After order restoration on the isolated load candidate, active Testing-only construction is cancelled without promoting queued work. Recorded charges are refunded once to the original payer; historical inferred prices and orphaned jobs without recorded charges do not generate refunds. A load warning reports each cancellation. Queued Testing-only construction remains queued and fails through normal unavailable-template handling when attempted. Failed loads preserve the running campaign, its credits, and its active catalogue.

Older campaign-save migrations can read Testing definitions privately to recover historical component configuration; this does not make those templates buildable. Custom-design library migration from the repository is no longer supported and is separate from campaign-save migration.

## Component and ability schemas

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

Tactical activation checks the current shared equipment requirements in
`tactical_balance.py`. Nebula Catalyst therefore requires operational Sensors and
Antimatter Storage even when a saved definition retains the historical Harvester
prerequisite. Loading preserves installed components, saved definitions and runtime
state; this balance change needs no save migration or component replacement.

Commander stores its stance in `configuration` and explicit `current_order` and
`orders_queue` in `runtime`. Public order UUIDs, descendants, charges/refunds, and
bounded outcome history remain persistent. Loading preserves the current/queued
split, including an empty current slot. Active orders rebind their actuators
without executing startup again. Transient stance engagement trees and their
actuators are reacquired through normal play.

When adding a component or ability, register it, declare every persistent field,
and extend its independent round-trip fixture. A schema change requires an
explicit migration; changing constructor defaults is not a migration.

## Transactional load

`campaign_persistence.prepare_campaign()` completes these steps on an isolated
candidate before changing the running game:

1. Parse JSON and reject duplicate keys, invalid values, and excessive nesting.
2. Migrate by the declared save version.
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

## Legacy migration

Supported paths are `3.0 → 3.1 → 3.2 → 4.0 → 4.1`; recognized unversioned historical
documents enter at 3.0. Unknown and future versions are rejected. Migration works
on a copy and leaves the input unchanged. Legacy orders receive deterministic
public UUIDs where missing; later migration passes preserve them.

Versions before 4.0 omitted component damage, turret cooldowns, ability timers,
and some configuration. That information cannot be recovered. Migration retains
available fields and uses the named template or documented constructor defaults
for omitted state, with a visible warning. It clears orphaned temporary status
flags whose source timers were never saved. Empty legacy Weapons/Ability payloads
without a matching template component are rejected with a specific error.
Missing legacy celestial subtype keys use valid G-type star, hydrogen nebula,
and plasma storm defaults.

## Verification

`tests/test_persistence_integrity.py` covers all 26 registered components and all
legacy abilities, including non-default definitions and dynamically installed
components. Its canonical snapshot inspects runtime objects independently of the
serialization field declarations. It exercises a deliberately mutated mid-game
campaign through the actual file writer/reader, repeated loads, and idempotent
reconciliation. Separate tests cover legacy wire fixtures, minefield IDs, queued
orders, paid construction/refit/replenishment, next-turn continuation, overlapping
effects, stored timers, and injected failures throughout loading.

Run the regression suite from the repository root:

```powershell
./.venv/Scripts/python.exe -m pytest -q -o cache_dir=.codex_test_cache
```

## Tactical state in 4.1

The 4.0 to 4.1 migration adds empty `deployables` and `catalyst_patches` arrays to
each sector while retaining all existing abilities and timers. Deployables store
owner, immutable historical deploying-ship ID, kind, position, HP, cache contents
and emitter identification. Emitters/caches have no lifetime or expiry field.
Patches store original owner, source ID, nebula ID, radius and finite deadline.

New ability runtime persists owner-round readiness/expiry deadlines, active
targets, source allegiance, processed pull phase and Guardian split/cap/mitigation
tuning. Recovery and celestial-targeted orders retain typed references and UUIDs.
Loading restores these without activation, fuel charges, spawns or repeated pulls,
and reconciles expired effects according to each owner's last started turn.

Counts are rebuilt galaxy-wide from surviving objects. Source destruction, capture
and equipment changes do not erase provenance or reset caps. Duplicate object IDs
and invalid patch references are rejected. Historical deploying-ship references
may point to destroyed units; they still raise the object allocator's high-water
mark so their IDs cannot be reused. See `tests/test_tactical_abilities.py` for
independent gameplay, migration, round-trip and fake-provider acceptance coverage.
