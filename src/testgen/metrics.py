"""Set-similarity metrics shared by the measurement tools.

One function, in its own module, because the 0/0 answer is a ruling rather than
arithmetic and duplicating it across recall.py and stability.py is how the two
tools would come to disagree about what "no data" means.
"""

from __future__ import annotations


def jaccard(a: frozenset, b: frozenset) -> float:
    """|a and b| / |a or b|, with two empty sets defined as 1.0.

    Two empty sets are identical, so 1.0 is the correct reading -- but it is also
    the least informative number this function can return, so **every caller must
    report the set sizes alongside it.** A stability report saying "jaccard 1.0"
    over two runs that emitted nothing is true and reads as success.

    Rounded to six places so two runs over the same data produce byte-identical
    output and diff-runs does not report float formatting as variance.
    """
    if not a and not b:
        return 1.0
    return round(len(a & b) / len(a | b), 6)
