#!/usr/bin/env python3
"""
Tag each grammar point with the job it does in a sentence.

Level tags let you study N3 in isolation, but they do not let you sit down with
every way of saying "although" at once — and that is where the real confusions
live: のに, くせに, ものの and にもかかわらず differ by register and attitude, not
by meaning. Grouping by function puts the confusable set in front of you
together, which is when the distinctions actually separate.

Classification runs on the English meaning and the formation note, matched
against ordered keyword rules. It is deliberately conservative: a point that
matches nothing is reported rather than guessed at, so the gaps stay visible
instead of turning into a wrong tag.
"""

import re

# Ordered: the first matching rule wins for the primary tag, but a point may
# collect several tags where it genuinely does several jobs.
RULES = [
    ("conditional", r"\bif\b|unless|as long as|in case|provided|supposing"),
    ("concessive", r"although|even though|even if|despite|in spite of|"
                   r"regardless|whereas|nevertheless|far from|"
                   r"not as if|leaving .* aside|setting .* aside"),
    ("causation", r"because|thanks to|due to|owing to|since |reason|"
                  r"therefore|that's why|no wonder|result of|blame"),
    ("purpose", r"in order to|so that|for the purpose|aimed at|intended for|"
                r"so as"),
    ("time", r"\bwhen\b|while|after|before|as soon as|during|the moment|"
             r"the instant|ever since|until|by the time|in the middle|"
             r"no sooner|whenever|already|not yet|still"),
    ("evidential", r"seems|apparently|looks like|I hear|according to|"
                   r"as if|it is said|reportedly|judging from"),
    ("obligation", r"must|should|ought to|have to|need to|no need|"
                   r"had better|cannot avoid|no choice but|forced to|"
                   r"unbecoming|do not have to"),
    ("possibility", r"\bcan\b|able to|might|may |possible|impossible|"
                    r"no way|cannot|unlikely|bound to|certainly|"
                    r"there is a risk|worthy of"),
    ("volition", r"want|intend|plan|decide|shall|let's|try to|"
                 r"make an effort|scheduled|about to|will not"),
    ("comparison", r"than|as .* as|the more|the most|compared|rather than|"
                   r"instead of|in exchange|unlike|no match"),
    ("limitation", r"only|nothing but|merely|just |at most|no more than|"
                   r"limited to|not limited|nothing more"),
    ("addition", r"not only|in addition|moreover|as well|besides|"
                 r"on top of|not to mention|along with|together with"),
    ("emphasis", r"even |precisely|indeed|extremely|the height|the extreme|"
                 r"unbearab|indescrib|not a single|absolutely|"
                 r"nothing other|so much that|undaunted"),
    ("listing", r"such as|things like|\bboth\b|whether|exhaustive|partial list|"
                r"and so on|one after"),
    ("quotation", r"say|said|called|named|the fact that|it means|"
                  r"in other words|quote"),
    ("nominalisation", r"the act of|-ness|the one who|the thing that|"
                       r"the way of|how to"),
    ("degree", r"to the extent|too |excessively|approximately|about |"
               r"a little|very |not very|not at all|depending on"),
    ("voice", r"passive|causative|make .* do|let someone|be made to|"
              r"do .* for|have someone"),
    ("politeness", r"honorific|humble|polite|please |command|imperative"),
    ("tendency", r"tend to|apt to|prone|-ish|show signs|make a point|"
                 r"come to |used to|every time|habit"),
    ("aspect", r"finish|begin|start|continue|in the process|"
               r"leave .* as|in advance|end up|completely|"
               r"has been|state"),
    ("existence", r"there is|exists|become"),
    ("topic", r"marker|topic|subject|object|direction|destination"),
]

COMPILED = [(name, re.compile(pat, re.I)) for name, pat in RULES]

# Assigned by hand: these carry meanings no keyword rule reaches without
# loosening the rules to the point where they mislabel everything else.
MANUAL = {
    "〜であろうと": ["concessive"], "〜ともなく": ["aspect"],
    "〜ともなると": ["conditional"], "〜ないものか": ["volition"],
    "〜にひきかえ": ["comparison"], "〜に至るまで": ["emphasis"],
    "〜まで (extreme)": ["emphasis"], "〜まみれ": ["degree"],
    "〜をものともしない": ["concessive"], "〜ことだから": ["evidential"],
    "〜ことなく": ["aspect"], "〜ずじまい": ["aspect"],
    "〜というものだ": ["quotation"], "〜ものを": ["concessive"],
    "〜とばかりに": ["quotation"], "〜こととて": ["causation"],
    "〜ゆえに": ["causation"], "〜がゆえに": ["causation"],
    "〜あっての": ["conditional"], "〜ならでは": ["limitation"],
    "〜きわまりない": ["emphasis"], "〜ずくめ": ["degree"],
    "〜の極み": ["emphasis"], "〜の至り": ["emphasis"],
    "〜だに": ["emphasis"], "〜すら": ["emphasis"],
    "〜たりとも": ["emphasis"], "〜こそ": ["emphasis"],
    "〜こそすれ": ["concessive"], "〜ばこそ": ["causation"],
    "〜てやまない": ["emphasis"], "〜んばかり": ["evidential"],
    "〜ながらに": ["aspect"], "〜にして": ["time"],
    "〜をもって": ["time"], "〜をこめて": ["voice"],
    "〜がてら": ["purpose"], "〜かたわら": ["time"],
    "〜きり": ["limitation"], "〜だらけ": ["degree"],
    "〜わ〜わ": ["listing"], "〜まい": ["volition"],
}

# Relational noun-markers (に対して, に関して, にとって, をめぐって ...) are one of
# the most confused sets in the deck, and no meaning-keyword catches them:
# their glosses are all short prepositions. They get their own group.
MANUAL.update({
    "〜にこたえて": ["relation"], "〜にすれば": ["relation"],
    "〜のもとで": ["relation"], "〜わりに": ["relation", "comparison"],
    "〜をめぐって": ["relation"], "〜をもとに": ["relation"],
    "〜にしては": ["relation", "comparison"], "〜にとって": ["relation"],
    "〜にわたって": ["relation", "time"], "〜に基づいて": ["relation"],
    "〜に対して": ["relation"], "〜に関して": ["relation"],
    "〜を通じて": ["relation"], "〜ぬきで": ["relation", "negation"],

    "〜にあたって": ["time"], "〜に際して": ["time"],
    "〜につれて": ["time"], "〜に伴って": ["time"],
    "〜にしたがって": ["time", "relation"], "〜ごろ": ["time"],

    "〜をよそに": ["concessive"], "〜どころではない": ["concessive"],
    "〜はんめん": ["concessive"], "〜とは限らない": ["concessive"],
    "〜わけではない": ["concessive"], "〜だけあって": ["causation"],

    "〜ことか": ["emphasis"], "〜ことになっている": ["obligation"],
    "〜だらけ・〜まみれ": ["degree"], "〜気味": ["degree"],
    "〜ずつ": ["degree"], "〜いくら": ["question"],
    "〜にくい": ["degree"], "〜やすい": ["degree"],

    "〜ぬ・〜ん": ["negation"], "〜ずに": ["negation"],
    "〜ないで": ["negation"], "〜がする": ["evidential"],
    "〜てくれる": ["voice"], "〜てみる": ["volition"],
    "〜でしょう": ["evidential"],

    "〜どうして・なぜ": ["question"], "〜どこ": ["question"],
    "〜よ": ["discourse"],
    "〜で (joining nouns / な-adjectives)": ["topic"],
    "〜で (means)": ["topic"], "〜の (possessive)": ["topic"],
})


def classify(entry):
    """Return the function tags for one grammar entry, most relevant first."""
    haystack = " ".join([
        entry.get("meaning", ""),
        entry.get("formation", ""),
        entry.get("notes", ""),
    ])
    manual = MANUAL.get(entry.get("point"))
    if manual:
        return manual
    tags = [name for name, rx in COMPILED if rx.search(haystack)]
    # Two tags is enough to be useful; more turns the tag list into noise.
    return tags[:2]


def report(entries):
    """Coverage summary, and the points no rule matched."""
    import collections
    counts = collections.Counter()
    unmatched = []
    for e in entries:
        tags = classify(e)
        if tags:
            counts.update(tags)
        else:
            unmatched.append(e["point"])
    return counts, unmatched


if __name__ == "__main__":
    import glob
    import json
    import os

    data = []
    for p in sorted(glob.glob(os.path.join(os.path.dirname(__file__),
                                           "data", "*.json"))):
        data.extend(json.load(open(p, encoding="utf-8")))

    counts, unmatched = report(data)
    print(f"{len(data)} points, {len(data)-len(unmatched)} classified "
          f"({100*(len(data)-len(unmatched))//len(data)}%)\n")
    for name, n in counts.most_common():
        print(f"  {name:16} {n}")
    if unmatched:
        print(f"\n{len(unmatched)} unmatched:")
        for p in unmatched:
            print("   ", p)
