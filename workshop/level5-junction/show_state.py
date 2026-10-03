"""
See the city state as data: a map (JSON), an array (list of numbers), or text.

    python level5-junction/show_state.py                     # map (JSON) after 20 ticks
    python level5-junction/show_state.py --format array      # flat list of numbers + field names
    python level5-junction/show_state.py --format text       # what Jev reads by default
    python level5-junction/show_state.py --vehicles          # map with every vehicle (position, speed, turn)
    python level5-junction/show_state.py --tick 0 --map single

In your own code:

    from city import City
    city = City(seed=1)  # the default map: three junctions on Zhongxiao E. Rd
    city.arrive()
    data = city.state()          # dict: junctions -> lights, approaches, queues, speeds ...
    numbers = city.state_array() # [0.0, 1.0, 3.0, ...]
    names = city.array_fields()  # ["time_fraction", "raining", "fuxing_zhongxiao.light_NS", ...]
"""
import argparse
import json

from city import DEFAULT_MAP, MAPS, City
from officers import GreedyOfficer


def city_at(tick, seed, map_name):
    """Play `tick` ticks with the simple-rules officer, then stop (before the next decision)."""
    city = City(seed, map_name)
    officer = GreedyOfficer()
    city.arrive()
    for _ in range(tick):
        forced = city.forced_actions()
        ask = [jid for jid in city.junctions if jid not in forced]
        city.step({**forced, **officer.act(city, ask)["actions"]})
        city.arrive()
    return city


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--format", default="map", choices=["map", "array", "text"])
    ap.add_argument("--tick", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--map", default=DEFAULT_MAP, choices=sorted(MAPS))
    ap.add_argument("--vehicles", action="store_true", help="map: include every vehicle")
    args = ap.parse_args()

    city = city_at(args.tick, args.seed, args.map)
    if args.format == "map":
        print(json.dumps(city.state(vehicles=args.vehicles), indent=2, ensure_ascii=False))
    elif args.format == "array":
        values, names = city.state_array(), city.array_fields()
        print(json.dumps(values))
        print(f"\n{len(values)} numbers. What each one means:")
        for i, (name, value) in enumerate(zip(names, values)):
            print(f"  [{i:>3}] {name:<45} {value}")
    else:
        print(city.describe())


if __name__ == "__main__":
    main()
