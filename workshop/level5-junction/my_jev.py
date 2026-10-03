"""
YOUR TRAFFIC BRAIN. The city runs, but its traffic lights do nothing until this function answers.

    async def decide(history, current) -> new lights

    history   the earlier states, oldest first (like the accumulator of a fold / reduce)
    current   the state now (the same shape, see State below), for example:
              {"tick": 3, "clock": "09:09", "crossings": [
                  {"id": 0, "name": "Fuxing × Zhongxiao", "lights": "A", "ticks": 2,
                   "cars": {"north": {"left": 0, "straight_right": 2, "bikes": 0}, "east": {...}, "south": {...}, "west": {...}},
                   "people": {"north": 4, "east": 0, "south": 0, "west": 2}},
                  ... 3 more crossings ]}
    return    the new lights, one phase per crossing:   {0: "A", 1: "C", 2: "W", 3: "B"}

    A = north-south straight + right turn     B = north-south left turn
    C = east-west straight + right turn       D = east-west left turn
    W = everyone walks (all four zebras)

The city moves in ticks, one decide() call each (city_server.py --tick: 2 s, 1 s, 0.5 s ...). At the
start of a tick, per lane, the first car at the stop line goes if its light is green, and it is across
the crossing at the end of that tick: exactly 1 tick. The lights become exactly what you return and
stay so for the tick (all red before your first answer). A crossing you leave out keeps its lights.
People too: on W, the people waiting at a zebra go when a tick starts and are across at its end.
"""
import asyncio
import sys
from pathlib import Path
from typing import Literal, Optional, TypedDict, Union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev as _jev  # noqa: E402

Phase = Literal["A", "B", "C", "D", "W"]
Lights = dict[int, Phase]
Side = Literal["north", "east", "south", "west"]


class Lanes(TypedDict):
    """Who waits on one side of a crossing, per lane."""
    left: int                                # cars waiting to turn left
    straight_right: int                      # cars waiting to go straight or turn right
    bikes: int                               # bikes and scooters waiting


class Crossing(TypedDict):
    id: int                                  # 0 .. 3, the key of your answer
    name: str
    lights: Optional[Phase]                  # None = all red (before your first answer)
    ticks: int                               # how many ticks these lights have been on
    cars: dict[Side, Lanes]                  # per side the traffic comes from
    people: dict[Side, int]                  # people waiting at each zebra


class State(TypedDict):
    tick: int                                # 1, 2, 3, ... one per decide() call
    clock: str                               # "09:09"
    crossings: list[Crossing]                # in history, each state also has "lights_chosen": what you returned


# =============================================================================================
# Calling Jev, typed. One call = one state (text) + any number of questions; Jev answers each
# question on its own, against the same state. Three kinds of question:
#
#   yes_no(...)  -> answer["noul"]          0.0 .. 1.0, the chance the answer is YES
#   choice(...)  -> answer["choice"]        one of your labels (+ "probabilities" per label)
#   score(...)   -> answer["score"]         0 .. len(levels)-1, can be a fraction like 2.4
# =============================================================================================
class YesNoAnswer(TypedDict):
    type: Literal["noul"]
    noul: float                              # chance of YES


class ChoiceAnswer(TypedDict):
    type: Literal["choice"]
    choice: str                              # the label Jev picked
    confidence: float
    probabilities: dict[str, float]          # every label with its probability


class ScoreAnswer(TypedDict):
    type: Literal["score"]
    score: float                             # 0 .. len(levels)-1
    confidence: float


Answer = Union[YesNoAnswer, ChoiceAnswer, ScoreAnswer]


def yes_no(question: str, yes: str = None, no: str = None) -> dict:
    """A yes/no question. yes / no: optional, what exactly counts as yes and as no."""
    return _jev.noul(question, yes=yes, no=no)


def choice(question: str, options: dict[str, str]) -> dict:
    """Pick one of the options: {"label": "what it means", ...}."""
    return _jev.choice(question, options)


def score(question: str, levels: list[str]) -> dict:
    """Rate on a scale, lowest first: ["none", "a few", "many", "a lot"]."""
    return _jev.score(question, levels)


async def ask_jev(state: str, questions: dict[str, dict]) -> dict[str, Answer]:
    """ONE call to the Jev API. state: what Jev reads. questions: {id: yes_no(...) | choice(...) | score(...)}.
    Returns {id: answer} with the same ids."""
    result = await asyncio.to_thread(_jev.decide, state=state, questions=questions)
    return result["answers"]


# =============================================================================================
# Your function
# =============================================================================================
PHASES: dict[Phase, str] = {
    "A": "green for north and south: straight and right turn",
    "B": "green for north and south: left turn",
    "C": "green for east and west: straight and right turn",
    "D": "green for east and west: left turn",
    "W": "all cars stop, people walk across all four roads",
}


def describe(j: Crossing) -> str:
    """One crossing of the state, in plain numbers."""
    lights = f"{j['lights']} ({PHASES[j['lights']]})" if j["lights"] else "all red"
    return "\n".join([f"✨ Crossing {j['id']} state: {j['lights']}. "]
                     + [f"{side}: ({lanes['straight_right']} cars waiting to go straight or right) "
                        f"({lanes['left']} waiting to turn left) ({lanes['bikes']} bikes)"
                        for side, lanes in j["cars"].items()]
                     + [f"Finally, people waiting: {sum(j['people'].values())}"])


async def decide(history: list[State], current: State) -> Lights:
    state = "\n".join([f"Time {current['clock']}. Traffic lights of 4 crossings."]
                      + [describe(j) for j in current["crossings"]]) + " \n\nThe more cards are queueing, the more urgent it is. Try to learn from historical choices. Sometimes it's smart to drain the hole queue. Lesser cars & people there are waiting on the map, the better it is. Junction 0 is top left, 1 is top right, 2 is bottom left and 3 is bottom right. So cars passing soutbound of jnction 0 would soon arrive junction 2. U can use it smartly."


    print(str(state))

    # One choice question per crossing, all in ONE call:
    answers = await ask_jev(state, {
        str(j["id"]): choice(f"Which lights should crossing {j['id']} show to minimize queues for all citizens (cars, people, bikes etc)?",
                             PHASES)
        for j in current["crossings"]
    })

    choices = {k: v["choice"] for k, v in answers.items()}


    return choices

    # ---- more examples (copy into the code above) -------------------------------------------
    #
    # A yes/no question: should crossing 0 let people walk now?
    #   a = await ask_jev(state, {"walk": yes_no("Should crossing 0 let people walk now?",
    #                                            yes="many people wait, or they waited long",
    #                                            no="few people wait and many cars wait")})
    #   if a["walk"]["noul"] > 0.5: ...                       # 0.0 .. 1.0
    #
    # A score: how busy is the north-south road at crossing 0?
    #   a = await ask_jev(state, {"busy": score("How busy is the north-south road at crossing 0?",
    #                                           ["empty", "a few cars", "busy", "jammed"])})
    #   a["busy"]["score"]                                    # 0.0 .. 3.0, e.g. 2.4
    #
    # Several kinds in one call (each answered on its own, against the same state):
    #   a = await ask_jev(state, {
    #       "phase": choice("Which lights for crossing 0?", PHASES),
    #       "walk":  yes_no("Do people at crossing 0 need to walk now?"),
    #       "busy":  score("How busy is crossing 0?", ["quiet", "normal", "busy", "jammed"]),
    #   })
    #   a["phase"]["choice"], a["phase"]["probabilities"], a["walk"]["noul"], a["busy"]["score"]
    #
    # Using the history (the earlier states, oldest first):
    #   def cars_waiting(s: State) -> int:
    #       return sum(sum(lanes.values()) for c in s["crossings"] for lanes in c["cars"].values())
    #   before = history[-1] if history else None              # the state one call ago
    #   waited_before = cars_waiting(before) if before else 0
    #   state += f"\nOne step ago {waited_before} vehicles waited; now {cars_waiting(current)}."
