# Diplomatio 3.0 – Rulebook (prototype)

Status: consolidated rules for the prototype, as of 2026-10-26.
How the rules are implemented is described in [IMPLEMENTATION.md](IMPLEMENTATION.md).

**Sources, in order of priority:**
1. Decisions made with the user (marked *[decided]*)
2. `Diplomatio 3.0.docx` (newest spec)
3. `Feliximmediat.docx` (older draft) and the Discord chat, used only where 3.0 is silent
4. Proposed defaults (marked *[default]*). They are used until somebody objects.

**Design principle:** no gameplay number is fixed in code. Every value written like `this_name` is a setting
in the rules config (see section 13) and gets tuned through playtesting. Where a rule is a choice between two
behaviours, it is also a setting if that's cheap.

Gap IDs (G1 …) refer to the original question list and are kept for traceability.

---

## 1. Overview
- Online strategy game for up to **12 players**, each on their own device; diplomacy happens by talking (e.g. Discord).
- The game runs in **turns**. Every turn all players enter orders at the same time and press **Ready**.
  When everyone is ready (or the timer runs out), the turn is resolved.
- Goal of the 3.0 redesign: combat takes less time and is easier to understand, so there is more time for diplomacy.

## 2. Map
- Hexagon grid. One hexagon = **field**. A connected group of fields = **province**.
- Fields are **land** or **sea**. No other terrain *[default, G18 – depends on the map]*.
- Every province has a **name**, an **income value**, exactly one **capital** (its only city) and possibly **ports**.
  The income value is not necessarily equal to the number of fields.
- Capitals and ports are fixed by the map. Nothing can be built or demolished. Fortresses no longer exist.
- Provinces belong to a player or are **neutral** *[default, G19 – depends on the map]*.
- Fields never change owner on their own. Only taking the capital changes the owner of the whole province *[decided, G12/G13]*.

## 3. Turn structure

### 3.1 Turn start
1. Every player receives **income** = sum of the income values of their provinces. This already happens in turn 1.
2. Every player pays **upkeep** (section 4.2).
3. A new **player order** is drawn (section 3.4) and shown to everyone.

### 3.2 Order phase
- Players enter orders: recruit, disband, move, toggle forced march, send gold, give a province.
- A player sees only **their own** orders. The whole map (all provinces and armies) is visible to everyone *[decided, G42]*.
- The order in which a player enters their orders is remembered and matters during resolution.
- Ready button. The turn resolves when all active players are ready or `turn_timer_seconds` runs out
  (0 = no timer). Orders that were entered count even if the player wasn't ready *[default, G41]*.

### 3.3 Resolution
Resolution runs in fixed phases. Inside each phase, players go one after another in the player order, and each
player's orders run in the order they were entered *[3.0]*.
1. **Transfer phase:** gold and province gifts.
2. **Recruitment phase:** recruiting and disbanding.
3. **Movement phase:** moves, including combat and conquest.

Gold received during resolution (transfers, disband refunds) can be spent in the **next** turn's orders *[decided, G8/G40]*.

### 3.4 Player order
- Random each turn *[3.0]*.
- Nobody can be first two turns in a row, and nobody can be last two turns in a row *[decided, G39]*.
  If no order satisfies this (e.g. only one player), the restriction is dropped for that turn.
- Setting `turn_order_rule` allows other rules later (e.g. the draft's "first 30 %" rule).

## 4. Economy

### 4.1 Gold
- Gold may go **negative (debt)** *[decided, G5]*. Debt has no extra penalty for now.
- Recruiting needs enough gold at the time the order is entered *[default]*: the total cost of all recruit orders
  plus all gold sent must not be more than the player's current gold *[decided, G52]*. Setting: `allow_spending_into_debt` (off).

### 4.2 Upkeep
- `upkeep_per_division` (0.25) per division, summed over the whole nation and then rounded with `upkeep_rounding`
  (default: round half up) *[default, G3]*.
- `upkeep_per_army` (2) per army.
- Draft idea to test: 0.5 per division – just a change of the setting.

### 4.3 Recruiting (Aufrüsten)
- New divisions can be placed on:
  - an **own capital** – joins the army standing there, or creates a new army if the field is empty
  - an **own army**, wherever it stands *[decided, G11]*
- Cost: `division_cost` per division.
- Limit per turn: `recruit_limit_per_province` (3) × number of provinces owned at turn start, counting all
  divisions recruited that turn *[default, G7]*. There is no limit per army.
- Divisions recruited this turn **cannot move** in the same turn. If an army was reinforced, only the divisions that
  were already there can move; a move order for more divisions moves only those *[decided, G50]*.

### 4.4 Disbanding (Abrüsten)
- Any own army, anywhere, can disband any number of divisions *[default]*.
- Refund: `disband_refund` (2 gold) per division, received during resolution.
- Disbanding doesn't count against the recruitment limit.

### 4.5 Transfers
- A player can send gold to another player.
- A player can **give** a province to another player.
- Selling (province for gold, both sides agree) comes in a later milestone *[G9]*.
- Gifted provinces count towards victory only after `gift_delay_turns` (10) turns (section 11).

## 5. Armies & movement
- An **army** is a group of divisions of one player on one field. No size limit.
- A player has at most one army per field: if an army ends its move on a field with an own army, they **merge** *[decided, G10]*.
- Two different players' armies never end on the same field (they fight, section 6).
- **Move order:** army, number of divisions, path of adjacent fields. Moving only part of an army **splits** it:
  the moving part becomes a new army, the rest stays *[decided, G10]*.
- **Range:** `move_range` (1) field per turn.
- **Forced march** (Gewaltmarsch): toggled per army. Range `forced_march_range` (3), combat value
  `forced_march_combat_value` (0.5). It stays on until the player switches it off; switching takes effect before movement.
  A part split off a forced-marching army keeps forced march *[decided, G53]*.
- Moves are executed one at a time in player order, against the state at that moment *[decided, G16]*:
  - If the target army already moved away, there is no fight.
  - If the army was destroyed earlier this turn, its order is skipped. If it has fewer divisions than ordered, all remaining ones move.
- Walking through own fields, neutral fields and enemy provinces is allowed *[decided, G12]*.
- Entering a field with an **enemy army** starts a fight. The moving army stops there, even if it had range left *[decided, G14]*.
- Allied armies never fight (alliances: later milestone).
- When armies merge, the army that was already standing there keeps its forced-march setting *[default, G54]*.
- Land armies move only over land fields with a province; sea and blocked land are impassable in milestone 1 *[default, G55]*.
- An army can get several move orders per turn, each one splitting off its divisions, as long as together they use
  at most its movable divisions. A part split off cannot get further orders that turn *[decided, G56]*.

## 6. Combat
- Basic rule: **1 division kills 1 division**, no defender advantage.
- Each army has a **combat value** per division: normal 1, forced march 0.5, (later: transport 0.25, fleet 1).
  The value applies to attackers and defenders alike *[default, G24]*.
- **Default formula** *[decided as first version, G20; swappable]*:
  - `strength = floor(divisions × combat value)`, at least 1 if the army has divisions *[default, G21]*
  - The side with lower strength is destroyed.
  - The winner loses `ceil(loser strength ÷ winner combat value)` divisions (never more than it has).
  - Equal strength: both armies are destroyed.
  - Example: 10 divisions on forced march (strength 5) attack 4 normal divisions (strength 4) → defender destroyed,
    attacker loses 4 ÷ 0.5 = 8 divisions, 2 are left.
- The winning attacker **moves onto** the field *[decided, G22]*. If the defender wins, the attacker is gone.

## 7. Conquest
- A province is conquered only by moving an army onto its **capital**.
- Any defending army on the capital is fought first (section 6).
- Conquest is tried only on the field where a move ends (end of the path, or the field of a fight that stopped it).
  Capitals passed on the way are not conquered *[default, G57]*.
- Then the attacker pays the **conquest cost**: divisions equal to the province's income value (× `conquest_cost_factor`, default 1).
  - The cost also applies to an empty capital *[default, G28]*.
  - If the attacker has exactly enough divisions, it pays them and the army disappears – the province is still conquered
    (`conquest_allow_army_used_up`, default on) *[default, G27, chat: "Armeen dürfen verpuffen"]*.
  - If the attacker does not have enough divisions, the province does not change owner and the attacker stays on the
    field it came from.
- After a successful conquest the remaining attacker stands on the capital and the whole province belongs to the attacker.
- Armies of the old owner inside the province stay where they are *[default, G31]*.
- Neutral provinces are conquered the same way.

## 8. Players
- A player with no provinces stays in the game *[decided, G30]*.
- Later milestones: surrender button → spectator, host can kick players.

## 9. Visibility
- Everyone sees the whole map: provinces, owners, armies and their sizes.
- Everyone sees only their own orders until the turn resolves.
- Other players' gold is hidden *[decided, G51]*.
- A public **board** shows everything else for every player: provinces owned, province share, income,
  upkeep, number of armies, total divisions *[decided, G51]*.

## 10. Naval system (milestone 2 – provisional)
- **Transports:** a land army can put to sea from an own port field to an adjacent sea field. It moves 1 field
  per turn, combat value `transport_combat_value` (0.25), and can land on any land field.
- **Fleets** (warships): built in sea fields next to own ports, reinforced and disbanded only next to an own port.
  Range `fleet_move_range` (2), combat value 1. Forced march: range 4, combat value 0.5. Cannot enter or attack land.
  Same cost and upkeep as armies.
- An own fleet and an own transport can share a sea field (chat 25.11.2023).
- **Tank rule:** if an army next to an own fleet is attacked, the fleet fights first; the army fights only if the fleet is destroyed.
- Open: G25, G29, G33–G38, G49 (section 14).

## 11. Alliances & victory (milestone 3 – provisional)
- Alliances: shared ownership calculation, 10-turn counter, max size `max_alliance_size` (lobby setting).
  Allies cannot attack or conquer each other. Alliances can be broken.
- Victory: a single player needs more than `victory_share_single` (40 %) of all provinces, an alliance more than
  `victory_share_alliance` (60 %) – the first fraction that is strictly higher.
- Gifted and sold provinces count only after `gift_delay_turns` (10). The display shows both percentages, the second in brackets.
- Milestone 1 only shows each player's province share. There is no automatic game end yet.
- Open: G43–G48 (section 14).

## 12. Later features (milestone 4+)
Map editor, lobby with map preview, random nation assignment with delayed reveal, pause (unlimited for host,
one per player, anyone can end it), idle warning, surrender/spectator, kick. Saving is already in milestone 1.

## 13. Rules config – all settings and their starting values

| Setting | Start value | Meaning |
|---|---|---|
| `division_cost` | 3 | gold per recruited division (placeholder) |
| `disband_refund` | 2 | gold back per disbanded division |
| `upkeep_per_division` | 0.25 | per division per turn |
| `upkeep_per_army` | 2 | per army per turn |
| `upkeep_rounding` | half_up | `half_up`, `up` or `down`, applied to the nation total |
| `allow_spending_into_debt` | false | may recruit/send gold beyond current gold |
| `recruit_limit_per_province` | 3 | divisions per owned province per turn |
| `recruits_can_move_same_turn` | false | G50 |
| `move_range` | 1 | fields per turn |
| `forced_march_range` | 3 | fields per turn on forced march |
| `forced_march_combat_value` | 0.5 | combat value on forced march |
| `strength_rounding` | down | how `divisions × value` is rounded |
| `min_strength` | 1 | lowest strength of an army that has divisions (G21) |
| `combat_formula` | default | which combat module is used |
| `conquest_cost_factor` | 1 | conquest cost = income × factor |
| `conquest_allow_army_used_up` | true | exactly enough divisions is enough |
| `turn_order_rule` | no_repeat_first_last | which turn-order module is used |
| `turn_timer_seconds` | 0 | 0 = wait until all are ready |
| `start_gold` | per map | gold at game start |
| `show_other_players_gold` | false | G51 |
| `gift_delay_turns` | 10 | milestone 3 |
| `victory_share_single` | 0.40 | milestone 3 |
| `victory_share_alliance` | 0.60 | milestone 3 |
| `max_alliance_size` | lobby | milestone 3 |
| `transport_combat_value` | 0.25 | milestone 2 |
| `fleet_move_range` / `fleet_forced_march_range` | 2 / 4 | milestone 2 |

## 14. Open questions

**Milestone 1:** no open rule questions left (G50–G53 decided, see sections 4, 5 and 9).
G54, G55, G57 (merge flag, impassable sea, conquest only at move end) are defaults set during implementation –
object if they feel wrong. G56 (several moves per army) is decided.

**Europa map** (`maps/europa/`, see IMPLEMENTATION.md section 4.3):
| ID | Question | Current state |
|---|---|---|
| M1 | The screenshot is cut off at the bottom by the taskbar. Does the map continue further south (more of Africa)? | map ends at the last visible row |
| M2 | Scandinavia, Russia and the Ottoman region have no capitals or borders. Playable later, neutral provinces, or blocked? | blocked (`?SE`, `?RU`, `?TR`) |
| M3 | Income per province is not in the picture. | placeholder: half the field count, 1–5 |
| M4 | Start armies and start gold per nation? | none / rules config |
| M5 | Only 7 nations on this map, the game supports 12. Fine for testing? | 7 |
| M6 | Province and capital names (chosen by Claude) – OK? | see `map.json` |

G18 (terrain) is answered by the map: only land and sea. G19 (neutral provinces) depends on M2.

**Ships (milestone 2):**
| ID | Question | Default |
|---|---|---|
| G25 | Can a land army attack a transport at sea, or a transport attack a land field directly? | transport may attack land with 0.25; land armies can't attack sea |
| G29 | Can a transport land directly on an enemy capital? | yes, counts as an attack with 0.25 |
| G33 | Is a port a specific coastal field? Must it be your own to embark / build fleets? | specific field; own |
| G34 | Do embarking and disembarking use a normal 1-field move? | yes |
| G35 | Does the tank rule also protect armies on land next to the coast? | yes, any own army next to an own fleet |
| G36 | Several fleets next to the army: which tanks first? Allied fleets? Does leftover damage pass to the army? | largest first; no allies; yes |
| G37 | Can transports merge with fleets or be carried? | share a field yes, merge no, carry no |
| G38 | Can transports be reinforced? | no |
| G49 | Does a fleet on the same field as a transport also tank for it? | yes |

**Alliances & victory (milestone 3):**
| ID | Question | Default |
|---|---|---|
| G43 | What is the **10-turn counter**? Alliance must exist 10 turns before its % counts, or victory must be held 10 turns? | **ask your friend** |
| G44 | How are alliances formed? Can a player be in more than one? | invite/accept; one only |
| G45 | Does breaking an alliance take effect immediately? | next turn |
| G46 | Is victory instant, or does it have to be held? Does the game end automatically? | depends on G43 |
| G47 | Is the alliance's share simply the sum of its members' provinces? | yes |
| G48 | Does the 10-turn delay apply to conquered provinces too? | no, only gifted/sold |
| G9 | How does selling work (offer → accept, atomic swap)? | offer/accept, atomic |

---

## Appendix A – Contradictions between the sources

| Topic | Draft | Chat | 3.0 | Used |
|---|---|---|---|---|
| Disband refund | no gold back | – | 2 gold/division | 3.0 |
| Division upkeep | 0.25, maybe 0.5 | – | 0.25 | setting |
| Province transfer | gift only | gift | gift or sell | 3.0 |
| Enemy army blocks income | yes | – | not mentioned | decided: no |
| Turn-order fairness | "first 30 %" rule | – | not first/last twice | 3.0 |
| Ports | open question | only buildable building | fixed, nothing buildable | 3.0 |
| Recruit limit | – | per army | per turn total, none per army | 3.0 |

## Appendix B – Relevant notes from the Discord chat (2023–2024)
- 08.02.2023: "Ab sofort Gold in der ersten Runde?" → income is paid already in turn 1.
- 25.10.2023: homework list (bigger provinces, splitting vs. "pinseln", only building tiles conquerable) → background for the province rework; army splitting existed in 2.0.
- 12.11.2023: gift provinces, flexible alliances, "how to avoid victory by angry gifting?" → solved by the 10-turn delay.
- 12.11.2023: "Vorerst dürfen Armeen einfach verpuffen" → conquest may use up the whole army.
- 25.11.2023: own fleet + own army may share a sea field.
- 17.03.2023: a 2.0 Unreal save file was shared; not usable here.
