# Titans

A player may own one surviving Titan or reserve one acquisition. Titan Flagship
and Titan Citadel are public designs, and the Designer supports custom Titan
ships and installations. Normal starts have no Titan; Testing starts include one
Flagship per player. There is no research or separate hero progression gate.

## Hull and economics

| Property | Value |
| --- | ---: |
| Capacity / hull HP | 800 / 1,600 |
| Base construction credits / owner turns | 20,000 / 60 |
| Equipped storage minimum | 1,000 AM |
| Credit upkeep per owner turn | 50 + 0.1 × installed hull usage |
| Engine and hyperdrive hull/fuel multipliers | 4 × Medium |
| Titan Core | 100 hull, fixed |
| Each Titan ability | 25 hull, plus the ordinary 10-hull Abilities base |

Ordinary equipment surcharges, material costs and duration scaling still apply.
At 800 hull usage, construction costs 44,000 credits, 1,200 metal and 400 crystal,
takes 120 owner turns, and upkeep is 130 credits per owner turn. Removing or
destroying the Core does not change the ownership limit or hull upkeep formula.
Remove dependent abilities before removing the Core. Core damage and repair use
ordinary subsystem rules.

Flagship uses 744.80 hull: an 8-turret heavy capital battery, tripled defenses,
2,000 AM, an eight-slot Strikecraft Bay, Advanced Hyperdrive, fleet repair,
extended sensors with 3-ring long-range coverage, marines, counter-intelligence,
all five Titan powers, and tactical fleet abilities. Citadel uses 675.80 hull,
adds a 300-radius Hyperspace Inhibitor field and 4-ring long-range sensors, and
omits Engines, Hyperdrive, Fleet Jump, and Marines. Bay production selections
start empty. The catalogue computes prices from the equipment.

New wormholes are 70% Titan, 15% Large and 15% Medium diameter. A Huge-diameter
connection excludes Titans. Ordinary terrain, docking and atmospheric restrictions
remain in force.

## Strategic powers

All powers require working Titan Core, Abilities and Antimatter Storage. Issuance
reserves AM without activating the power. Execution occurs once per owner round,
at owner End Turn before movement and hazards, and rechecks live conditions.
Titan powers never create automatic approach orders.

| Power | Additional equipment | AM | Duration | Cooldown |
| --- | --- | ---: | --- | ---: |
| Fleet Jump | Engines; ready Basic or Advanced Hyperdrive | 200 | Instant | 30 rounds |
| Aegis Field | Defenses | 150 | 10 rounds | 20 rounds |
| Siege Lance | Weapons, Sensors | 200 | One-round charge | 25 rounds |
| Deep Scan | Sensors | 150 | 5 rounds | 20 rounds |
| Carrier Supremacy | Strikecraft Bay, Sensors | 200 | 10 rounds | 25 rounds |

**Fleet Jump:** choose an explored hex and explicit arrival position anywhere in
the current system. Destination distance has no limit. Gather owned, deployed,
enabled non-wing ships with working engines within 750; escorts need no drive.
More than 800 escort hull capacity rejects the whole cast. Every departure and
arrival must satisfy inhibition, terrain, collision clearance and boundaries.
Formation offsets and carried craft are preserved. Passenger explicit orders are
cancelled with ordinary cleanup while stances remain selected. The Titan drive
starts normal recharge. The sidebar and observations preview participants and
replaced orders.

**Aegis Field:** a moving radius of 1,000 protects the caster and deployed allies
from half of incoming weapon damage, including subsystem hits. It expires at the
owner-turn start ten rounds after activation. Identical fields do not stack.
Other protection multiplies with Aegis; mines and environmental hazards bypass it.

**Siege Lance:** charge a 500-damage beam against a visible enemy ship or station
within 3,000. Pay and start cooldown when charging begins. Hold position, suppress
ordinary weapons and block queued work until the next owner End Turn, allowing
every opponent an intervening turn. Visibility, allegiance, equipment, range and
firing clearance are rechecked. Cancellation, displacement, disablement, capture
or lost targeting aborts without refund or cooldown reset. Target owners and
allies receive a warning with the source identity redacted when unseen.

**Deep Scan:** choose any existing hex in the current system, including an
unexplored hex. Owner and allies continuously receive ordinary short-range
sensor detail throughout it. Cloaks and terrain that defeat only radar do not
hide deployed contacts. Decoys and exploration use existing intelligence rules.
No extra mines, atmospheric hidden craft, docked craft, agents, covert equipment,
enemy orders or private cargo are disclosed. New arrivals appear; departures
need another visibility source. Coverage stays on the chosen hex and ends on
expiry, equipment/source invalidation or departure from the system. Historical
intelligence remains. Read-only visibility queries neither tick nor mutate it.

**Carrier Supremacy:** all deployed friendly wings in the Titan's current sector
gain double weapon damage, +50% speed and half incoming weapon damage, including
other owned and allied carriers' wings. Membership follows movement. Orders,
roles, target restrictions, endurance, servicing, recovery and launch locks remain
authoritative; no creation, healing or weapon cooldown reset occurs. Identical
effects do not stack. Attack Run can yield a four-times-damage salvo. Combined
Aegis and Supremacy yield 75% less incoming weapon damage before other mitigation.
Mines and hazards bypass this protection; stored equipment statistics are unchanged.

Cooldown deadlines stay on the unit across component replacement, repair,
capture, hiding and saves. Active effects end when their source becomes invalid
and never restart automatically. `cancel_ability` ends Aegis, Lance charging,
Deep Scan or Supremacy without refunds.

## Acquisition and persistence

Living hidden, disabled, refitting and dismantling Titans occupy the slot.
Accepted queued/approaching construction and pending capture attempts reserve it.
Construction roots, approach children and paid jobs represent one acquisition.
Cancellation/failure releases reservations; completion converts a reservation to
ownership. Destruction, completed dismantling and enemy capture release the former
owner's slot. Capture requires free recipient capacity and ordinary boarding
eligibility; preflight never assumes success.

Construction freezes the accepted hull class and rejects a changed class at
execution/completion. Reservations are reconstructed from the ownership graph,
orders and jobs. Current-format saves persist cooldown deadlines, active effect
locations/deadlines, charge progress, phase guards and construction classification.
Invalid Titan equipment and duplicate ownership/acquisitions reject the detached
load candidate transactionally.

The shared implementation is `titan_balance.py`, `titan_acquisition.py` and
`titan_abilities.py`, with integration into the ordinary visibility, damage,
component, construction, command and turn services. All controllers use these rules.
