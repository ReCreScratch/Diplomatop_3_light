"""Map editor endpoint: PUT /api/maps/{name} validates with the engine's map loader before writing."""
import copy
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import ROOT, TEST_MAP
from server.app import create_app


@pytest.fixture
def client(tmp_path):
    maps = tmp_path / "maps"
    shutil.copytree(ROOT / "maps" / "europa", maps / "europa", ignore=shutil.ignore_patterns("*.png", "*.webp"))
    shutil.copytree(TEST_MAP, maps / "mini")
    (maps / "mini" / "theme.json").write_text(json.dumps({"nation_colors": {"AA": "#123456"}}), encoding="utf-8")
    c = TestClient(create_app(tmp_path / "saves", maps))
    c.maps = maps
    return c


def mini(c):
    return json.loads((c.maps / "mini" / "map.json").read_text(encoding="utf-8"))


def test_save_new_map_appears_in_lists_and_static_files(client):
    data = mini(client)
    data["provinces"]["A1"]["income"] = 7
    data["provinces"]["A1"]["name"] = "Neuland"
    data["nations"]["AA"]["start_gold"] = 40
    data["rules"] = {"max_alliance_size": 3, "victory_share_single": 0.45, "alliance_min_turns": 2, "ai_recruit_per_city": 2}
    r = client.put("/api/maps/meine-karte_2", json={"map": data, "theme_from": "mini"})
    assert r.status_code == 200 and r.json() == {"ok": True, "name": "meine-karte_2"}
    assert "meine-karte_2" in client.get("/api/maps").json()
    saved = client.get("/maps/meine-karte_2/map.json").json()
    assert saved["provinces"]["A1"]["income"] == 7 and saved["rules"]["max_alliance_size"] == 3
    assert saved["nations"]["AA"]["start_gold"] == 40
    assert client.get("/maps/meine-karte_2/theme.json").json() == {"nation_colors": {"AA": "#123456"}}   # copied from mini
    assert not list((client.maps / "meine-karte_2").glob("*.tmp"))


def test_new_map_is_playable_with_its_rules(client):
    data = mini(client)
    data["rules"] = {"start_gold": 3, "ai_recruit_per_city": 2}
    data["nations"]["AA"]["start_gold"] = 40
    client.put("/api/maps/spiel", json={"map": data})
    r = client.post("/api/games", json={"map": "spiel"}).json()
    gid = r["game_id"]
    t1 = client.post(f"/api/games/{gid}/join", json={"name": "A", "nation": "AA", "host_token": r["host_token"]}).json()["token"]
    t2 = client.post(f"/api/games/{gid}/join", json={"name": "B", "nation": "BB"}).json()["token"]
    lob = client.get(f"/api/games/{gid}/lobby", params={"token": t1}).json()
    assert lob["rules"]["ai_recruit_per_city"] == 2 and lob["nations"]["AA"] == "Aland"
    assert client.post(f"/api/games/{gid}/start", params={"token": t1}).status_code == 200
    v1 = client.get(f"/api/games/{gid}/state", params={"token": t1}).json()
    v2 = client.get(f"/api/games/{gid}/state", params={"token": t2}).json()
    assert v1["my_gold"] == 40 and v2["my_gold"] == 3                          # per-nation start gold beats the rules


def test_overwrite_same_name_and_own_theme(client):
    data = mini(client)
    data["provinces"]["B1"]["income"] = 9
    theme = {"nation_colors": {"AA": "#abcdef"}, "background": "#000000"}
    assert client.put("/api/maps/mini", json={"map": data, "theme": theme}).status_code == 200
    assert mini(client)["provinces"]["B1"]["income"] == 9
    assert client.get("/maps/mini/theme.json").json() == theme


@pytest.mark.parametrize("name", ["../evil", "a/b", "a\\b", ".hidden", "", "x" * 41, "with space", "..", "ä", "mini.json", "a.b"])
def test_bad_names_are_refused_and_nothing_is_written(client, name):
    r = client.put(f"/api/maps/{name}", json={"map": mini(client)})
    assert r.status_code in (400, 404, 405)
    outside = [p.name for p in client.maps.parent.iterdir()]
    assert "evil" not in outside and sorted(p.name for p in client.maps.iterdir()) == ["europa", "mini"]


def test_name_check_on_the_server_function(client):
    from server import maps
    assert maps.save_map(client.maps, "../evil", mini(client)).startswith("Ungültiger")
    assert maps.save_map(client.maps, "", mini(client)).startswith("Ungültiger")
    assert maps.save_map(client.maps, None, mini(client)).startswith("Ungültiger")
    assert not (client.maps.parent / "evil").exists()


@pytest.mark.parametrize("change, text", [
    (lambda m: m["provinces"]["A1"].update(capital=[5, 2]), "Hauptstadt"),
    (lambda m: m["provinces"]["A1"].update(owner="ZZ"), "Besitzer"),
    (lambda m: m["provinces"]["A1"].update(income=-3), "Einkommen"),
    (lambda m: m["provinces"].update(Z9=copy.deepcopy(m["provinces"]["A1"])), "keine Felder"),
    (lambda m: m["provinces"]["A1"].update(ports=[[0, 2]]), "Hafen"),
    (lambda m: m["grid"].__setitem__(0, "QQ ~~ ~~ ~~ ~~ ~~ ~~ ~~"), "Token"),
    (lambda m: m.update(rules={"nonsense": 1}), "Regel"),
    (lambda m: m["nations"]["AA"].update(start_gold="viel"), "Startgold"),
    (lambda m: m.pop("provinces"), "fehlt"),
    (lambda m: m.update(grid="kaputt"), ""),
])
def test_invalid_maps_are_refused_with_the_engine_message(client, change, text):
    data = mini(client)
    change(data)
    r = client.put("/api/maps/kaputt", json={"map": data})
    assert r.status_code == 400 and text in r.json()["detail"]
    assert not (client.maps / "kaputt").exists() and "kaputt" not in client.get("/api/maps").json()


def test_failed_overwrite_keeps_the_old_file(client):
    before = (client.maps / "mini" / "map.json").read_bytes()
    data = mini(client)
    data["provinces"]["A1"]["capital"] = [7, 2]
    assert client.put("/api/maps/mini", json={"map": data}).status_code == 400
    assert (client.maps / "mini" / "map.json").read_bytes() == before


def test_missing_or_wrong_bodies(client):
    assert client.put("/api/maps/neu", json={}).status_code == 400
    assert client.put("/api/maps/neu", json={"map": [1, 2]}).status_code == 400
    assert client.put("/api/maps/neu", json={"map": mini(client), "theme": "rot"}).status_code == 400
    assert client.put("/api/maps/neu", json=[1]).status_code == 422
    assert "neu" not in client.get("/api/maps").json()


def test_theme_from_must_be_a_valid_existing_map(client):
    r = client.put("/api/maps/nt", json={"map": mini(client), "theme_from": "../../x"})
    assert r.status_code == 200 and not (client.maps / "nt" / "theme.json").exists()
    assert client.put("/api/maps/nt2", json={"map": mini(client), "theme_from": "nonexistent"}).status_code == 200


def test_europa_roundtrip_through_the_editor_format(client):
    """The editor sends back what it loaded: saving europa unchanged under a new name is valid."""
    data = json.loads((client.maps / "europa" / "map.json").read_text(encoding="utf-8"))
    assert client.put("/api/maps/europa2", json={"map": data, "theme_from": "europa"}).status_code == 200
    again = json.loads((client.maps / "europa2" / "map.json").read_text(encoding="utf-8"))
    assert again == data


def test_default_rules_and_editor_page_are_served(client):
    rules = client.get("/api/rules").json()
    assert rules["ai_recruit_per_city"] == 1 and rules["idle_warning_seconds"] == 40 and rules["nation_reveal_pause_seconds"] == 1
    page = client.get("/editor")
    assert page.status_code == 200 and "Karteneditor" in page.text
    assert client.get("/client/editor.js").status_code == 200
