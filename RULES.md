# Diplomatio – Rulebook (prototype)

Status: consolidated rules for the prototype, as of 2026-10-27 (reworked for `Diplomatio 4.0.docx`).
How the rules are implemented is described in [IMPLEMENTATION.md](IMPLEMENTATION.md).

**Sources, in order of priority:**
1. Decisions made with the user (marked *[decided]*)
2. `Diplomatio 4.0.docx` (newest spec, marked *[4.0]*)
3. `Diplomatio 3.0.docx` (marked *[3.0]*), used where 4.0 is silent
4. `Feliximmediat.docx` (older draft) and the Discord chat, used only where 4.0 and 3.0 are silent
5. Proposed defaults (marked *[default]*). They are used until somebody objects.

**Design principle:** no gameplay number is fixed in code. Every value written like `this_name` is a setting
in the rules config (see section 13) and gets tuned through playtesting. Where a rule is a choice between two
behaviours, it is also a setting if that's cheap.

Gap IDs (G1 …) refer to the original question list and are kept for traceability.

---

## 1. Overview
- Online strategy game for up to **12 players**, each on their own device; diplomacy happens in the in-game chat or by talking.
- The game runs in **turns**. Every turn all players enter orders at the same time and press **Ready**.
  All decisions take effect only at the end of the turn, when everyone is ready or the timer runs out *[4.0]*.
- Goal of the redesign: combat takes less time and is easier to understand, so there is more time for diplomacy.

## 2. Map
- Hexagon grid. One hexagon = **field**. A connected group of land fields = **province**. Every land field belongs
  to exactly one province; borders are fixed by the map (editor) *[4.0]*.
- Three field types *[4.0]*:
  - **land** – always has an owner (the owner of its province)
  - **sea** – no owner
  - **impassable** – no owner, cannot be entered by armies or fleets
- Every province has a **name**, a fixed **income value** (gold), exactly one **city** (its capital) and possibly **ports**.
  The income value is not necessarily equal to the number of fields.
- Cities and ports are fixed by the map. Nothing can be built or demolished. Fortresses no longer exist.
- A **port** is a specific land field. It belongs to the owner of its province *[4.0, answers G33]*.
- Every province belongs to a nation. Nations without a player are run by the **AI ruleset** (section 8.2)
  *[4.0, answers G19]*. There are no ownerless provinces.
- Fields never change owner on their own. Only taking the city changes the owner of the whole province *[decided, G12/G13]*.
- At most one army stands on a land field. An army may stand on a city or a port *[4.0]*.

## 3. Turn structure

### 3.1 Order phase
- Players enter orders: recruit, disband, move (incl. standing marches), toggle forced march, send gold,
  give or sell a province, "do not attack" toggle.
- A player sees only **their own** orders. The whole map (all provinces and armies) is visible to everyone *[decided, G42]*.
- The order in which a player enters their orders is remembered and matters during resolution.
- The **player order** for this turn's resolution is shown at the right edge of the screen (section 3.3).
- Ready button. The turn resolves when all active players are ready or `turn_timer_seconds` runs out
  (0 = no timer). Orders that were entered count even if the player wasn't ready *[default, G41]*.

### 3.2 Resolution
Resolution runs in fixed phases *[decided, 4.0]*. Inside each phase, players go one after another in the player
order, and each player's orders run in the order they were entered *[3.0]*.
1. **Diplomacy phase** (milestone 3, section 11): "do not attack" toggles, alliance invitations, acceptances and
   leaves, sale offers. They count for the rest of this resolution.
2. **Recruitment phase:** recruiting and disbanding. New divisions appear on the map.
3. **Gold phase:** every player receives **income** (sum of the income values of their provinces) and pays
   **upkeep** (section 4.2); gold transfers and province gifts/sales are carried out.
4. **Movement phase:** moves, including combat and conquest.

After the last phase: members who left an alliance are out, old invitations and offers expire, the victory check runs
(section 11.5).

Then the next turn starts and a new player order is drawn.
- Turn 1 starts with `start_gold`; the first income is paid at the end of turn 1 *[default]*.
- Gold received during resolution (income, transfers, disband refunds) can be spent in the **next** turn's
  orders *[decided, G8/G40]*.
- The replay shows recruitments and moves one by one with `animation_pause_seconds` (0.5) between them *[4.0]*.

### 3.3 Player order
- Random each turn *[3.0/4.0]*.
- Nobody gets the **same position** as in the previous turn *[decided, 4.0 – replaces G39]*.
  If no order satisfies this (e.g. only one player), the restriction is dropped for that turn.
- Setting `turn_order_rule` (`no_repeat_position`) allows other rules (e.g. `no_repeat_first_last` from 3.0,
  the draft's "first 30 %" rule).

## 4. Economy

### 4.1 Gold
- Gold may have **decimals** *[4.0]*. Nothing is rounded.
- Gold may go **negative (debt)** *[decided, G5]*. Debt has no extra penalty for now.
- Recruiting needs enough gold at the time the order is entered *[default]*: the total cost of all recruit orders
  plus all gold sent must not be more than the player's current gold *[decided, G52]*. Setting: `allow_spending_into_debt` (off).
- A player's gold is secret; only they see it *[4.0, decided G51]*.

### 4.2 Upkeep
- `upkeep_per_division` (0.25) per division, `upkeep_per_ship` (0.25) per ship *[4.0]*.
- No upkeep per army any more: `upkeep_per_army` is 0 *[decided, 4.0]*. No rounding: `upkeep_rounding` is `none`.

### 4.3 Recruiting (Aufrüsten)
- New divisions can be recruited only on an **own city** *[decided, 4.0 – replaces G11]*. They join the army standing
  there, or create a new army if the field is empty.
- Cost: `division_cost` (5) per division *[4.0]*. An army has no size limit.
- Limit per turn: `recruit_limit_per_province` (3) × number of provinces owned at turn start, counting all
  divisions recruited that turn *[default, G7 – not in 4.0]*.
- Recruitment is resolved first, so new divisions are on the map from the next turn on and **cannot move** in the
  turn they were ordered. If an army was reinforced, only the divisions that were already there can move *[decided, G50]*.

### 4.4 Disbanding (Abrüsten)
- Only an own army standing on an **own city** can disband, any number of its divisions *[decided, 4.0]*.
- Refund: `disband_refund` (2 gold) per division, received during resolution.
- Disbanding doesn't count against the recruitment limit.

### 4.5 Transfers
- A player can send gold to another player.
- A player can **give** or **sell** a province to another player *[4.0]*. Selling: offer → accept next turn, atomic
  swap in the gold phase (section 11.4) *[decided, G9]*.
- Gifted or sold provinces count towards victory only after `gift_delay_turns` (10) turns *[3.0 – not in 4.0]* (section 11).

## 5. Armies & movement
- An **army** is a group of divisions of one player on one field. No size limit.
- A player has at most one army per field: if an army ends its move on a field with an own army, they **merge** *[decided, G10]*.
- Two different players' armies never end on the same field (they fight, section 6).
- **Move order:** army, number of divisions, path of adjacent fields. Moving only part of an army **splits** it:
  the moving part becomes a new army, the rest stays *[decided, G10, 4.0]*.
- **Range:** `move_range` (1) field per turn.
- **Forced march** (Gewaltmarsch): toggled per army *[default – 4.0 says "divisions" without values]*. Range
  `forced_march_range` (3), combat value `forced_march_combat_value` (0.5). It stays on until the player switches it off;
  switching takes effect before movement. A part split off a forced-marching army keeps forced march *[decided, G53]*.
- Moves are executed one at a time in player order, against the state at that moment *[decided, G16]*:
  - If the target army already moved away, there is no fight.
  - If the army was destroyed earlier this turn, its order is skipped. If it has fewer divisions than ordered, all remaining ones move.
- Walking through own fields and enemy provinces is allowed *[decided, G12]*. Only an **enemy army** starts a fight,
  not an enemy field on its own *[decided]*.
- Entering a field with an **enemy army** starts a fight. The moving army stops there, even if it had range left *[decided, G14]*.
- Allied armies and armies of players with mutual "do not attack" (section 11) never fight.
- **Standing march orders** *[decided, G58, 4.0]*: a move order may name a destination beyond the range. The army moves
  as far as it can each turn and keeps the rest of the route as a standing order, which runs automatically in later
  turns (in the owner's slot of the player order, before that player's new orders) until the destination is reached.
  It can be changed or deleted in every turn. Setting: `standing_marches` (on). Defaults for the details *[default]*:
  - A new move order for the army replaces its route; the player can also cancel it ("Halt").
  - The route ends when the army fights, when a conquest is attempted (success or failure), or when it merges
    with another own army at the end of a turn's segment.
  - A part split off with a long route takes that route; the rest keeps its own (if any).
  - Each turn's segment follows the normal rules (range incl. forced march, fights stop it, conquest only where the
    segment ends).
- When armies merge, the army that was already standing there keeps its forced-march setting *[default, G54]*.
- Land armies cannot enter impassable fields. Sea fields only via a port (section 10); in milestone 1 sea is
  impassable *[default, G55]*.
- An army can get several move orders per turn, each one splitting off its divisions, as long as together they use
  at most its movable divisions. A part split off cannot get further orders that turn *[decided, G56]*.

## 6. Combat
*[decided, 4.0 – replaces the 3.0 formula of G20/G21]*
- Every unit has **combat value** (damage it deals) and **hit points**:
  - division: combat value 1 and hit points 1 (`unit_types.division.combat_value` / `hp`); on forced march its combat value is
    `forced_march_combat_value` (0.5), hit points stay 1
  - ship: `ship_combat_value` (4) and `ship_hp` (4) (milestone 2)
- An army's total combat value = sum over its divisions; total hit points likewise. No rounding, no minimum.
- In a fight, each side loses hit points equal to the **other** side's total combat value, at the same time.
  - Hit points at or below 0: the army is destroyed.
  - Otherwise its divisions are set to its remaining hit points ÷ `division_hp`, rounded with `survivor_rounding`
    (default: up – a side with hit points left keeps at least 1 division) *[default]*.
- Examples: 10 normal vs 4 normal → defender destroyed, attacker keeps 6. 4 vs 4 → both destroyed.
  10 on forced march (combat value 5) vs 4 normal → defender destroyed, attacker keeps 10 − 4 = 6.
- The value applies to attackers and defenders alike *[default, G24]*.
- If the defender is destroyed and the attacker survives, the attacker **moves onto** the field *[decided, G22]*.
  If both survive (possible with forced march), the attacker stays on the field it came from *[default, G59]*.
- Setting `combat_formula` (`hp_attrition`) keeps the formula swappable (the 3.0 formula stays available as `strength_3_0`).

## 7. Conquest
- A province is conquered only by moving an army onto its **city**.
- Any defending army on the city is fought first (section 6).
- Conquest is tried only on the field where a move ends (end of the path, or the field of a fight that stopped it).
  Cities passed on the way are not conquered *[default, G57]*.
- Then the attacker pays the **conquest cost**: divisions equal to the province's income value (× `conquest_cost_factor`, default 1) *[4.0]*.
  - The cost also applies to an empty city *[default, G28]*.
  - If the attacker has exactly enough divisions, it pays them and the army disappears – the province is still conquered
    (`conquest_allow_army_used_up`, default on) *[default, G27, chat: "Armeen dürfen verpuffen"]*.
  - If the attacker does not have enough divisions, the province does not change owner and the attacker stays on the
    field it came from *[4.0]*.
- After a successful conquest the remaining attacker stands on the city and the whole province belongs to the attacker.
- Armies of the old owner inside the province stay where they are *[default, G31]*.
- Provinces of AI nations are conquered the same way.

## 8. Players

### 8.1 Players, surrender, kick
- A player with no provinces stays in the game *[decided, G30]*.
- A player can **surrender** and keep watching as a spectator. Their nation then follows the AI ruleset; all its
  units stay where they are *[4.0]*.
- The host can kick players *[4.0]*.

### 8.2 AI ruleset *[4.0]*
Applies to nations without a player and to nations of surrendered players. Set in the editor; default:
- recruits `ai_recruit_per_city` (1) division in every own city every turn
- its divisions never move
- hostile to all other nations
- builds no ships

## 9. Visibility & interface
- Everyone sees the whole map: provinces, owners, armies and their sizes.
- Everyone sees only their own orders until the turn resolves.
- Other players' gold is hidden *[decided, G51, 4.0]*.
- **Nation overview** (book icon, bottom left) *[4.0]*: own fields, provinces, unit counts, income, running costs and
  expected gold next turn; the map's victory conditions; alliance status of all nations; share of land fields per
  nation and per alliance. (3.0's public board with income/upkeep of all players: these are shown for oneself only
  in 4.0; the land-field share is public.)
- **Chat** at the bottom *[4.0]*: a group chat for all players ("Schwarzes Brett") and direct chats with every other
  player. Both can be minimized.
- **Keys** *[4.0]*: `f` shows the coordinates of every field (letters horizontal, numbers vertical); `h` centres the map.
- **End of game statistics** *[4.0]*: the game tracks as many values as possible and shows them at the end
  (e.g. heatmap of fields where most divisions and ships died, gold generated per nation, enemy divisions and ships
  destroyed per nation).

## 10. Naval system (milestone 2)
### 10.1 Ports
- A **port** is a specific land field of a province, set in the map (`ports` of the province) *[4.0, G33]*.
  It belongs to the owner of its province.
- Europa map placeholder: one port per coastal province, on the city if the city is at the coast, else on the coastal
  field next to the city *[default, M7]*.

### 10.2 Armies at sea (transports)
- A land army can put to sea only **from an own port field** to an adjacent sea field *[decided]*. Putting to sea and
  landing each end that turn's move *[default, G34]*.
- At sea an army moves `transport_move_range` (1) field per turn; forced march has no effect at sea *[default]*.
  Its combat value at sea is `transport_combat_value` (0.25) per division, hit points stay 1.
- It can land on **any** adjacent land field. If an enemy army stands there it fights with 0.25; a landing on an
  enemy city is a normal conquest attempt *[decided, G25/G29]*.
- An army putting to sea onto a sea field with enemy units fights there with 0.25 *[decided]*. Land armies can attack
  sea units only this way. Fleets never attack land *[decided, 4.0]*.
- Armies at sea cannot be reinforced or disbanded *[decided, G38]*.

### 10.3 Fleets
- **Fleets** consist of **ships** *[4.0]*. A ship is built in an own port: the player picks a sea field next to the
  port, the ship appears there in the recruitment phase and cannot move that turn (like divisions). Cost `ship_cost` (5),
  upkeep `upkeep_per_ship` (0.25). Ships count against the recruit limit *[default]*. No size limit.
- Ships are disbanded only on a sea field next to an own port; refund `ship_disband_refund` (2) per ship *[decided, G60]*.
- Per ship: combat value 4, hit points 4 (`unit_types.ship`). Range `fleet_move_range` (3) *[4.0]*.
  Fleets have no forced march *[decided]*. Fleets never enter land.
- A player has at most **one fleet and one army** per sea field; own fleets ending on the same field merge, like
  armies *[decided, G36]*. Fleets can be split like armies.
- A fleet and an army can share a sea field as long as they are the same player's (or allied, milestone 3) *[4.0]*.
- A fleet entering a sea field with enemy units fights there and stops, like armies.

### 10.4 Linking
- A fleet and an army of the same player on the same sea field can be **linked** *[4.0]*. They then move together
  (one move order for either of them) and the fleet's range drops to `fleet_linked_move_range` (1) until the link is
  removed. A linked army is still a transport (0.25) *[decided, G49]*.
- Linking and unlinking take effect before movement, like forced march *[default]*. Landing the army or splitting
  either unit ends the link *[default]*.

### 10.5 Combat at sea (tank rule)
- *[decided, 4.0 – replaces G35]*: all units of one player on a sea field fight as **one side**. Its damage is the sum
  of all its units' combat values. The damage it takes goes first to the fleet's hit points and only the rest to the
  army's. Only units on the **same** sea field are protected.
- Losses: the fleet loses ships by the same rule as divisions (section 6, `survivor_rounding`), then the army.
- If the attacking side survives and the defending side is destroyed, the attacker moves onto the field; if both
  survive, the attacker stays where it came from (G59).

## 11. Diplomacy, alliances & victory (milestone 3)
Resolution gets a **diplomacy phase** before the recruitment phase: diplomacy → recruitment → gold → movement.

### 11.1 Hostility
- Two players are **hostile** unless they are allied or both have "do not attack" on for each other. AI nations and
  neutral provinces are hostile to everyone.
- Only hostile units fight, and only hostile cities can be conquered *[4.0]*.
- Units may **pass through** fields with units of non-hostile players but may not end their move there; the move then
  ends on the last free field before *[decided]*. Exception: allied units may share a **sea** field *[4.0]*. A player
  still has at most one fleet and one army per sea field; armies and fleets of the same player merge as before.
  Players with only a "do not attack" pact may not share a sea field.
- A fight that is won also ends on the start field if the target field still holds non-hostile foreign units
  (like G59) *[default]*.
- Recruiting or building a ship on a field that holds non-hostile foreign units is not possible
  ("Feld ist von fremden Truppen besetzt.") *[default]*.
- **Standing marches** *[default]*: if the end of a segment is blocked, the army stops on the last free field (or stays)
  and keeps the rest of the route, including the blocked part. The march tries again every turn until it is free;
  it ends only for the usual reasons (fight, conquest attempt, merge, halt). A whole army that cannot start keeps its
  route; a part that is split off and cannot move is not created (no route). With `standing_marches` off the rest
  is dropped.
- An attack on a sea field with units of several allied players fights all of them as one side (tank rule, 10.5).

### 11.2 "Do not attack" toggle *[4.0]*
- Each player can switch it on or off for any other player. It stays until switched again.
- It takes effect **immediately**, in the resolution of the same turn (diplomacy phase) *[decided, G61]*.

### 11.3 Alliances *[decided, G44/G45]*
- A player **invites** another player; the invited player **accepts** in the next turn (the invitation is valid for
  that one turn) *[default]*. If the inviting player is in an alliance, the new player joins it, else a new alliance
  of the two is founded.
- A player is in at most **one** alliance. An alliance has at most `max_alliance_size` (2, per map) members.
- All players are told when an alliance is formed or changes *[4.0]*.
- A member can **leave**; in this turn's resolution they are still allied, afterwards not *[decided]*. The leave is
  carried out at the end of the resolution, before the victory check. An alliance with one member left is dissolved.
- Every change of members (founding, joining, leaving) sets the alliance's `since` to that turn; `alliance_min_turns`
  counts from there *[default]*: the alliance is old enough at the end of resolution T if T − since ≥ `alliance_min_turns`.
- Invitations and sale offers stay private: they are not part of the public events; only the two players see them.
  Forming an alliance, leaving, dissolving and "do not attack" are public events.

### 11.4 Selling provinces *[decided, G9]*
- The seller offers a province to a player for a price in gold (whole number). The buyer accepts ("buy") in the next turn
  (valid for that one turn). In the gold phase, after income and upkeep, the province and the gold change hands
  together, if the seller still owns the province and the buyer has the gold (checked when the order is entered, like
  sending gold, and again at resolution). Otherwise the order is skipped and nothing changes. A province has at most
  one open offer; a new one replaces it. A sale counts like a gift for the gift delay.

### 11.5 Victory *[decided, 4.0, G46]*
- Measured in **land fields** (not provinces), checked at the end of every resolution:
  - a single player: more than `victory_share_single` (40 %) of all land fields (also when in an alliance)
  - an alliance: its members together (G47) more than `victory_share_alliance` (55 %); the alliance must exist for
    `alliance_min_turns` (10) turns, counted from its last change of members *[default]*
- The condition must hold at the end of `victory_hold_turns` (3) resolutions in a row *[decided]*, for the same leader.
  Then the game ends: no more orders are accepted. If several meet it, the one with the highest counted share leads
  (an alliance before its own member). Changing the leader or breaking the condition resets the count to 0 *[default]*.
- Gifted and sold provinces count only after `gift_delay_turns` (10) turns; conquered provinces count at once
  *[decided, G48]*. The display shows both shares, the counted one first and the real one in brackets.
  A gift or sale made in resolution g counts from the end of resolution g + `gift_delay_turns` *[default]*. If a
  province is conquered, its gift record is cleared.

## 12. Lobby, editor & technical features (milestone 4+)
- **Lobby** *[4.0]*: nations are chosen by each player or handed out at random; random nations are revealed one by
  one with `nation_reveal_pause_seconds` (1) between them. Map preview. Turn time limit in minutes and seconds
  (`turn_timer_seconds`).
- **Timer** *[4.0]*: players who let the time run out are named to everybody in the next turn. A player who has made
  no input for `idle_warning_seconds` (40) and isn't ready gets a written prompt to press Ready.
- **Pause** *[4.0]*: the host can pause the timer any time. Every player has one pause per game; the host can end it.
- **Editor** *[4.0]*: load and change maps, incl. provinces' gold values, borders and names, start gold of the
  nations, victory conditions (max. alliance size, shares, `alliance_min_turns`) and the AI ruleset.
- **Saving** *[4.0]*: an importable save is written at the end of every turn, so a game can continue after a crash
  (already in milestone 1).
- **Reconnect** *[decided]*: a player who drops out without surrendering (browser closed, connection lost, device
  changed) can reconnect and re-enter the running game as their nation. Their orders and ready state of the current
  turn are kept. Milestone 1 already does this in the same browser (token in the link and in browser storage);
  missing is re-entry without the personal link (G62).
- **Video** *[4.0]*: a screenshot of the map is stored at the end of every turn; at the end of the game they are
  exported as an mp4 video.

## 13. Rules config – all settings and their starting values

| Setting | Start value | Meaning |
|---|---|---|
| `start_gold` | per map | gold at game start |
| `division_cost` | 5 | gold per recruited division |
| `disband_refund` | 2 | gold back per disbanded division |
| `upkeep_per_division` | 0.25 | per division per turn |
| `upkeep_per_army` | 0 | per army per turn (removed in 4.0) |
| `upkeep_rounding` | none | `none`, `half_up`, `up` or `down`, applied to the nation total |
| `allow_spending_into_debt` | false | may recruit/send gold beyond current gold |
| `recruit_limit_per_province` | 3 | divisions per owned province per turn |
| `recruits_can_move_same_turn` | false | G50 |
| `move_range` | 1 | fields per turn |
| `standing_marches` | true | move orders beyond the range keep marching in later turns (G58) |
| `forced_march_range` | 3 | fields per turn on forced march |
| `forced_march_combat_value` | 0.5 | combat value per division on forced march |
| `unit_types.division.combat_value` / `hp` | 1 / 1 | section 6 |
| `strength_rounding` / `min_strength` | down / 1 | only for the 3.0 formula `strength_3_0` |
| `survivor_rounding` | up | how remaining hit points become divisions |
| `combat_formula` | hp_attrition | which combat module is used |
| `conquest_cost_factor` | 1 | conquest cost = income × factor |
| `conquest_allow_army_used_up` | true | exactly enough divisions is enough |
| `turn_order_rule` | no_repeat_position | which turn-order module is used |
| `phases` | diplomacy, recruitment, gold, movement | resolution phases in order (milestone 3 added `diplomacy`) |
| `turn_timer_seconds` | 0 | 0 = wait until all are ready |
| `animation_pause_seconds` | 0.5 | pause between replay steps |
| `show_other_players_gold` | false | G51 |
| `ai_recruit_per_city` | 1 | AI ruleset, section 8.2 |
| `ship_cost` / `upkeep_per_ship` | 5 / 0.25 | milestone 2 |
| `unit_types.ship.combat_value` / `hp` | 4 / 4 | per ship, milestone 2 |
| `fleet_move_range` / `fleet_linked_move_range` | 3 / 1 | milestone 2 |
| `ship_disband_refund` | 2 | milestone 2 |
| `transport_move_range` | 1 | milestone 2 |
| `transport_combat_value` | 0.25 | milestone 2 |
| `gift_delay_turns` | 10 | milestone 3 |
| `victory_hold_turns` | 3 | milestone 3 |
| `victory_share_single` | 0.40 | share of land fields, milestone 3 |
| `victory_share_alliance` | 0.55 | share of land fields, milestone 3 |
| `max_alliance_size` | 2 (per map) | milestone 3 |
| `alliance_min_turns` | 10 | turns since the alliance's last change of members before it can win, milestone 3 |
| `nation_reveal_pause_seconds` | 1 | milestone 4 |
| `idle_warning_seconds` | 40 | milestone 4 |

## 14. Open questions

**Milestone 1:** none open. New defaults from the 4.0 rework – object if they feel wrong:
- First income at the end of turn 1 (turn 1 is played with `start_gold` only).
- Recruit limit per province (3) kept, although 4.0 doesn't mention one.
- Forced march stays a per-army toggle; 4.0 says "divisions" but gives no values.
- `survivor_rounding` up, and G59: if both sides survive a fight, the attacker stays where it came from.

**Europa map** (`maps/europa/`, see IMPLEMENTATION.md section 4.3):
| ID | Question | Current state |
|---|---|---|
| M1 | The screenshot is cut off at the bottom by the taskbar. Does the map continue further south (more of Africa)? | map ends at the last visible row |
| M2 | Scandinavia, Russia and the Ottoman region have no cities or borders. With 4.0: AI nations, or impassable? | impassable (`?SE`, `?RU`, `?TR`) |
| M3 | Income per province is not in the picture. | placeholder: half the field count, 1–5 |
| M4 | Start armies and start gold per nation? | none / rules config |
| M5 | Only 7 nations on this map, the game supports 12. Fine for testing? | 7 |
| M6 | Province and city names (chosen by Claude) – OK? | see `map.json` |

**Ships (milestone 2):** G25, G29, G34, G36, G38, G49, G60 decided (section 10). Open:
| ID | Question | Default |
|---|---|---|
| M7 | Where are the ports on the Europa map? | one per coastal province, on or next to the city |

**Alliances & victory (milestone 3):** G9, G43–G48, G61 decided (section 11). New defaults – object if they feel wrong:
- Invitations and sale offers are private (no public event).
- A blocked move keeps its route and waits (11.1); a won fight whose target is still blocked ends on the start field.
- The victory counter restarts when the leader changes. A single player at 40 % wins alone even if his ally
  does not qualify.
- Saves from before milestone 3 get the new settings and the diplomacy phase when loaded.

**Technical:**
| ID | Question | Default |
|---|---|---|
| G62 | How does a player re-enter without their personal link (new device, cleared browser)? | the join screen of a running game lists the nations; picking one asks the host to confirm (or a per-player rejoin code shown in the game) |

---

## Appendix A – Contradictions between the sources

| Topic | Draft | Chat | 3.0 | 4.0 | Used |
|---|---|---|---|---|---|
| Disband refund | no gold back | – | 2 gold/division | 2 gold, only in cities | 4.0 |
| Where to recruit | – | – | city or any own army | city only | 4.0 |
| Division cost | – | – | – | 5 | 4.0 |
| Division upkeep | 0.25, maybe 0.5 | – | 0.25 + 2 per army | 0.25, decimals | 4.0 |
| Province transfer | gift only | gift | gift or sell | gift or sell | 4.0 |
| Enemy army blocks income | yes | – | not mentioned | not mentioned | decided: no |
| Turn-order fairness | "first 30 %" rule | – | not first/last twice | never same position | 4.0 |
| Resolution order | – | – | income at start; transfers → recruit → move | recruit → gold → move | 4.0 |
| Combat | – | – | lower strength dies, winner loses ceil(…) | damage vs. hit points | 4.0 |
| Victory measure | – | – | provinces 40/60 % | land fields 40/55 % | 4.0 |
| Armies at sea | – | – | via own port | any sea field | 3.0 (decided) |
| Fleet range / value | – | – | 2 / 1 | 3 / 4 (+4 HP) | 4.0 |
| Tank rule | – | – | neighbouring fields too | same sea field only | 4.0 |
| Fleet carries army | – | – | no | linking | 4.0 |
| Ports | open question | only buildable building | fixed, nothing buildable | fixed field | 4.0 |
| Recruit limit | – | per army | per turn total | not mentioned | 3.0 |
| Neutral provinces | – | – | possible | AI nations | 4.0 |
| Who ends a pause | – | – | anyone | host | 4.0 |

## Appendix B – Relevant notes from the Discord chat (2023–2024)
- 08.02.2023: "Ab sofort Gold in der ersten Runde?" → there is gold in turn 1 (now: `start_gold`; income at the end of the turn).
- 25.10.2023: homework list (bigger provinces, splitting vs. "pinseln", only building tiles conquerable) → background for the province rework; army splitting existed in 2.0.
- 12.11.2023: gift provinces, flexible alliances, "how to avoid victory by angry gifting?" → solved by the 10-turn delay.
- 12.11.2023: "Vorerst dürfen Armeen einfach verpuffen" → conquest may use up the whole army.
- 25.11.2023: own fleet + own army may share a sea field.
- 17.03.2023: a 2.0 Unreal save file was shared; not usable here.
