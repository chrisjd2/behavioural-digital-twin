from backend import personas
from backend.arms import ARM_SPECS, ArmResources
from backend.data import NewsItem, build_candidate_set
from backend.personas import invent_persona
from tests.factories import make_impression

CANDIDATES = build_candidate_set(make_impression(), seed=1, max_candidates=8, max_clicked=2)
NEWS = {
    news_id: NewsItem(news_id, "sports", "nfl", f"Headline {news_id}", f"Abstract {news_id}")
    for news_id in CANDIDATES.items
}


def test_same_user_id_always_yields_the_same_persona() -> None:
    assert invent_persona("U42") == invent_persona("U42")


def test_different_user_ids_yield_different_personas() -> None:
    assert len({str(invent_persona(f"U{i}")) for i in range(20)}) > 15


def test_persona_fields_come_from_the_fixed_lists() -> None:
    for user_id in ("U1", "U2", "U3", "U999"):
        persona = invent_persona(user_id)

        assert persona["invented"] is True
        first_name, _, last_name = str(persona["name"]).partition(" ")
        assert first_name in personas.FIRST_NAMES
        assert last_name in personas.LAST_NAMES
        assert persona["job"] in personas.JOBS
        assert persona["location"] in personas.LOCATIONS
        assert persona["news_habit"] in personas.NEWS_HABITS
        assert persona["age"] in range(personas.MIN_AGE, personas.MAX_AGE + 1)
        big_five = persona["big_five"]
        assert isinstance(big_five, dict)
        assert list(big_five) == list(personas.BIG_FIVE)
        assert set(big_five.values()) <= set(personas.LEVELS)
        values = persona["values"]
        assert isinstance(values, list)
        assert len(set(values)) == 2
        assert set(values) <= set(personas.SCHWARTZ_VALUES)


async def test_arm_b_knowledge_ignores_the_users_data() -> None:
    other = build_candidate_set(
        make_impression(history=3, clicks=1, non_clicks=4), seed=7, max_candidates=8, max_clicked=1
    )
    assert other.user_id == CANDIDATES.user_id
    assert (other.items, other.history, other.labels) != (
        CANDIDATES.items,
        CANDIDATES.history,
        CANDIDATES.labels,
    )

    first = await ARM_SPECS["B"].prepare(CANDIDATES, ArmResources())
    second = await ARM_SPECS["B"].prepare(other, ArmResources())

    assert first == second == invent_persona(CANDIDATES.user_id)


def test_arm_b_prompt_speaks_as_the_persona_with_the_shared_feed_framing() -> None:
    persona = invent_persona(CANDIDATES.user_id)

    messages = ARM_SPECS["B"].render(CANDIDATES, NEWS, persona, base_rate_hint=False)

    system, user = messages[0]["content"], messages[1]["content"]
    assert system.startswith(f"You are {persona['name']}, a {persona['age']}-year-old")
    assert str(persona["job"]) in system
    assert str(persona["news_habit"]) in system
    values = persona["values"]
    assert isinstance(values, list)
    assert all(v in system for v in values)
    assert "invented" not in system.lower()
    assert user.startswith("Each of these headlines appeared in your Microsoft News feed")
    assert 'clicked": 1' not in user
    assert "label" not in (system + user).lower()
