"""Diplomacy orders (RULES.md section 11): do-not-attack, alliances (invite / accept / leave) and selling provinces.
Registered like the others in orders.py, which imports this module at its end."""
from .alliances import accept_invitation, has_room
from .events import make_event
from .orders import Order, gold_errors, register


def other_player(state, player, who):
    """Error text if `who` is not another player of this game."""
    if who not in state.players or who == player:
        return ["Ungültiger Empfänger."]
    return []


def invitation(state, inviter, invitee):
    """The open invitation inviter -> invitee (made in the previous turn), or None."""
    return next((i for i in state.invitations if i["from"] == inviter and i["to"] == invitee
                 and i["turn"] == state.turn - 1), None)


def offer(state, province):
    """The open offer to sell province (made in the previous turn; at most one per province), or None."""
    return next((o for o in state.offers if o["province"] == province and o["turn"] == state.turn - 1), None)


@register
class NoAttack(Order):
    type = "no_attack"
    phase = "diplomacy"
    priority = 0
    fields = {"to": "str", "on": "bool"}

    def validate(self, state, player, pending):
        return self.shape_errors() or other_player(state, player, self.data["to"])

    def apply(self, state, player, events):
        to, on = self.data["to"], self.data["on"]
        mine = state.no_attack.setdefault(player, [])
        if on == (to in mine):
            return   # nothing changes
        if on:
            mine.append(to)
        else:
            mine.remove(to)
            if not mine:
                del state.no_attack[player]
        name, other = state.nation_name(player), state.nation_name(to)
        mutual = on and player in state.no_attack.get(to, ())
        text = (f"{name} verzichtet darauf, {other} anzugreifen." if on else
                f"{name} nimmt den Angriffsverzicht gegenüber {other} zurück.")
        events.append(make_event("no_attack", player, text + (" Beide Seiten greifen sich nun nicht mehr an." if mutual else ""),
                                 to=to, on=on, mutual=mutual))


@register
class Leave(Order):
    type = "leave"
    phase = "diplomacy"
    priority = 1

    def validate(self, state, player, pending):
        if not state.alliance_of(player):
            return ["Du bist in keinem Bündnis."]
        return []

    def apply(self, state, player, events):
        if player not in state.leaving:
            state.leaving.append(player)   # still allied for the rest of this resolution
            events.append(make_event("leave", player, f"{state.nation_name(player)} verlässt das Bündnis "
                                                      f"(wirksam nach dieser Runde).", alliance=state.alliance_of(player)["id"]))


@register
class Invite(Order):
    type = "invite"
    phase = "diplomacy"
    priority = 2
    fields = {"to": "str"}

    def validate(self, state, player, pending):
        errors = self.shape_errors() or other_player(state, player, self.data["to"])
        if errors:
            return errors
        to = self.data["to"]
        if not has_room(state, player):
            return ["Dein Bündnis ist voll." if state.alliance_of(player) else "Bündnisse sind hier nicht möglich."]
        if state.alliance_of(to):
            return [f"{state.nation_name(to)} ist schon in einem Bündnis."]
        if to in pending.invited:
            return ["Einladung schon verschickt."]
        return []

    def reserve(self, state, pending):
        pending.invited.add(self.data["to"])

    def apply(self, state, player, events):
        # stored for the next turn only; replaces an older one to the same player. Stays private (no event).
        state.invitations = [i for i in state.invitations if not (i["from"] == player and i["to"] == self.data["to"])]
        state.invitations.append({"from": player, "to": self.data["to"], "turn": state.turn})


@register
class Accept(Order):
    type = "accept"
    phase = "diplomacy"
    priority = 3
    fields = {"from": "str"}

    def validate(self, state, player, pending):
        errors = self.shape_errors() or other_player(state, player, self.data["from"])
        if errors:
            return errors
        inviter = self.data["from"]
        if state.alliance_of(player):
            return ["Du bist schon in einem Bündnis."]
        if pending.accepted:
            return ["Du kannst nur eine Einladung annehmen."]
        if not invitation(state, inviter, player):
            return ["Keine Einladung von diesem Spieler."]
        if not has_room(state, inviter):
            return ["Das Bündnis ist voll."]
        return []

    def reserve(self, state, pending):
        pending.accepted = True

    def apply(self, state, player, events):
        accept_invitation(state, self.data["from"], player, events)


@register
class OfferSale(Order):
    type = "offer_sale"
    phase = "diplomacy"
    priority = 4
    fields = {"province": "str", "to": "str", "price": "int"}

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        if state.owners.get(self.data["province"]) != player:
            return ["Provinz gehört dir nicht."]
        errors = other_player(state, player, self.data["to"])
        if errors:
            return errors
        if self.data["price"] <= 0:
            return ["Preis muss positiv sein."]
        return []

    def apply(self, state, player, events):
        # one open offer per province; valid next turn only. Stays private (no event).
        code = self.data["province"]
        state.offers = [o for o in state.offers if o["province"] != code]
        state.offers.append({"province": code, "from": player, "to": self.data["to"],
                             "price": self.data["price"], "turn": state.turn})


@register
class Buy(Order):
    type = "buy"
    phase = "gold"
    fields = {"province": "str"}

    def validate(self, state, player, pending):
        errors = self.shape_errors()
        if errors:
            return errors
        code = self.data["province"]
        sale = offer(state, code)
        if not sale or sale["to"] != player:
            return ["Kein Angebot für diese Provinz."]
        if state.owners.get(code) != sale["from"]:
            return ["Der Verkäufer besitzt die Provinz nicht mehr."]
        if code in pending.bought:
            return ["Provinz wird schon gekauft."]
        return gold_errors(state, player, pending, sale["price"])

    def reserve(self, state, pending):
        sale = offer(state, self.data["province"])
        pending.spent += sale["price"]
        pending.bought.add(self.data["province"])

    def apply(self, state, player, events):
        code = self.data["province"]
        sale = offer(state, code)
        state.players[player]["gold"] -= sale["price"]
        state.players[sale["from"]]["gold"] += sale["price"]
        state.owners[code] = player
        state.gifts.append({"province": code, "from": sale["from"], "to": player, "turn": state.turn, "price": sale["price"]})
        state.offers = [o for o in state.offers if o["province"] != code]
        events.append(make_event("buy", player,
                                 f"{state.nation_name(player)} kauft {state.map['provinces'][code]['name']} von "
                                 f"{state.nation_name(sale['from'])} für {sale['price']} Gold.",
                                 province=code, to=player, seller=sale["from"], price=sale["price"]))
