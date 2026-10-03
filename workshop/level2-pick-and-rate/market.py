"""
The market, 10 years later: what really happened to the five (made-up) companies in portfolio.py.
The browser's "Fast-forward 10 years" plays it, and `python level2-pick-and-rate/portfolio.py` scores you
with it. No peeking before you invest!
"""
BUDGET = 1_000_000   # NT$ you invest

# The bucket an expert puts each company in: your sorting score. "HUMAN?" = a person should look first.
EXPERT = {
    "Pearl Robotics": "rocket",
    "Formosa Fax": "shrinking",
    "Island Power Grid": "steady",
    "SkyDumpling Delivery": "HUMAN?",
    "Taipei Chip Design": "grower",
}

# What NT$1 in each company was worth at the end of each year (year 0 to year 10).
FUTURE = {
    "Pearl Robotics":       [1, 1.5, 2.1, 2.6, 3.0, 3.6, 4.1, 4.6, 5.1, 5.6, 6.0],
    "Formosa Fax":          [1, 0.85, 0.72, 0.6, 0.5, 0.42, 0.36, 0.3, 0.26, 0.22, 0.2],
    "Island Power Grid":    [1, 1.05, 1.1, 1.15, 1.2, 1.26, 1.32, 1.39, 1.45, 1.52, 1.6],
    "SkyDumpling Delivery": [1, 1.4, 1.7, 1.2, 0.4, 0, 0, 0, 0, 0, 0],
    "Taipei Chip Design":   [1, 1.3, 1.6, 1.4, 1.8, 2.2, 2.5, 2.7, 3.0, 3.2, 3.5],
}


def worth(allocation, year=10):
    """What an allocation {name: NT$} is worth after `year` years. Money in other companies (or not
    invested) stays as it was: nobody knows their future."""
    invested = sum(allocation.values())
    return BUDGET - invested + sum(amount * FUTURE.get(name, [1] * 11)[year] for name, amount in allocation.items())


def sorting_score(buckets):
    """buckets: {bucket: [(name, confidence), ...]} -> how many of the five are where the expert puts them."""
    where = {name: bucket for bucket, names in buckets.items() for name, _ in names}
    return sum(where.get(name) == bucket for name, bucket in EXPERT.items())
