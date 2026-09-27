"""The v3 intent pattern set: four relations over six entity types.

Phase 8.4 built the relation machinery and used it for one category, as its
brief required. Phase 8.5's pipeline needs four relations, so this module
declares the remaining two by **reusing** the Phase 8.4 model classes -
`EntityType`, `EntityLexicon`, `Frame`, `Relation`, `IntentPattern`,
`PatternSet` - rather than copying or reimplementing any of them.

    GUARANTEE      an outcome is made unconditional            financial_guarantee
    RISK_REMOVED   risk is denied without the word guarantee   financial_guarantee
    PREDICTION     a future market outcome asserted as fact    market_prediction
    ADVICE         a directive plus a financial object         investment_advice

`unverified_information` and `emotional_manipulation` are deliberately **not**
here. Sourcing and reader pressure are not relations between an entity and a
predicate, and inventing frames for them would be pattern-fitting. They come
from the semantic fallback, which is what the fallback is for.

The entity set is the phase's four - RETURN, CAPITAL, VALUE, OUTCOME - plus two
the remaining relations need: `You should buy this stock.` has no object among
the four, because a stock is not a return, a capital amount, a value or an
outcome. INSTRUMENT and REVENUE are marked as extensions in `model.py`.

The GUARANTEE and RISK_REMOVED frames are taken from Phase 8.4 unchanged in
structure; the only difference is that this lexicon is shared across three
patterns, so the object group is composed here rather than in one module.
"""

from __future__ import annotations

from ..intent_patterns.model import (
    ACTIVE,
    ATTRIBUTIVE,
    COPULAR,
    NOMINAL,
    PASSIVE,
    EntityLexicon,
    EntityType,
    Frame,
    IntentPattern,
    PatternSet,
    Relation,
)
from .model import (
    ADVICE,
    CAPITAL,
    GUARANTEE,
    INSTRUMENT,
    OUTCOME,
    PREDICTION,
    RETURN,
    REVENUE,
    RISK_REMOVED,
    VALUE,
)


ENTITIES = EntityLexicon(
    {
        RETURN: EntityType(
            RETURN,
            (
                r"returns?",
                r"yields?",
                r"income",
                r"payouts?",
                r"interest",
                r"dividends?",
                r"earnings",
                r"profits?",
                r"gains?",
                r"coupons?",
                r"\u6536\u76ca",
                r"\u56de\u62a5",
                r"\u5229\u6da6",
            ),
            "what the investment pays out",
        ),
        CAPITAL: EntityType(
            CAPITAL,
            (
                r"capital",
                r"principal",
                r"your money",
                r"your investment",
                r"your savings",
                r"your stake",
                r"the deposit",
                r"your deposit",
                r"\u672c\u91d1",
                r"\u6295\u5165\u7684\u94b1",
            ),
            "what the investor put in",
        ),
        VALUE: EntityType(
            VALUE,
            (
                r"values?",
                r"valuations?",
                r"prices?",
                r"the share price",
                r"the unit price",
                r"the balance",
                r"the index",
                r"the market",
                r"markets",
                r"the sector",
                r"\u4ef7\u683c",
                r"\u4ef7\u503c",
            ),
            "a measured worth",
        ),
        OUTCOME: EntityType(
            OUTCOME,
            (
                r"outcomes?",
                r"results?",
                r"performance",
                r"\u7ed3\u679c",
            ),
            "how it turns out",
        ),
        INSTRUMENT: EntityType(
            INSTRUMENT,
            (
                r"stocks?",
                r"shares?",
                r"the shares?",
                r"funds?",
                r"this fund",
                r"the fund",
                r"bonds?",
                r"equit(?:y|ies)",
                r"portfolio",
                r"the index",
                r"ETFs?",
                r"this company",
                r"the company",
                r"\u80a1\u7968",
                r"\u57fa\u91d1",
                r"\u503a\u5238",
            ),
            "an instrument that can be bought or held",
        ),
        REVENUE: EntityType(
            REVENUE,
            (r"revenues?", r"sales", r"turnover", r"top line", r"\u8425\u6536", r"\u6536\u5165"),
            "a company's income line",
        ),
    }
)

#: Who can be the guarantor, for the active guarantee frame.
GUARANTORS = EntityType(
    "GUARANTOR",
    (
        r"we",
        r"i",
        r"our fund",
        r"our team",
        r"our platform",
        r"the fund",
        r"this fund",
        r"the scheme",
        r"this scheme",
        r"the plan",
        r"this plan",
        r"the product",
        r"this product",
        r"the company",
        r"the issuer",
        r"the bank",
        r"the manager",
        r"the provider",
        r"the operator",
        r"the platform",
        r"they",
        r"\u6211\u4eec",
    ),
    "who makes the promise",
)

#: Verbs that name a change in a market quantity. A prediction needs one.
MOVEMENT_VERBS = (
    r"rise|fall|double|triple|reach|grow|climb|drop|decline|crash|recover|"
    r"rally|surge|slip|tumble|soar|multiply|increase|decrease|expand|contract|"
    r"\u4e0a\u6da8|\u4e0b\u8dcc|\u7ffb\u500d|\u589e\u957f"
)

#: Certainty carriers for the copular prediction frame.
CERTAINTY_ADJECTIVES = r"certain|sure|bound|destined|set|poised|guaranteed"

#: Directive verbs. The advice relation is a directive plus an object.
DIRECTIVES = (
    r"buy|sell|hold|add|shift|move|invest|allocate|put|acquire|avoid|reduce|"
    r"trim|consider|pick|choose|reallocate|recommend(?:s|ed|ing)?|urge[sd]?|"
    r"suggest(?:s|ed)?|\u4e70\u5165|\u5356\u51fa|\u52a0\u4ed3"
)

ADVICE_OBJECT = ENTITIES.group(RETURN, CAPITAL, VALUE, OUTCOME, INSTRUMENT)

_GUARANTEE_OBJECT = ENTITIES.group(RETURN, CAPITAL, VALUE, OUTCOME)

#: A short noun phrase between the object and its predicate. Bounded to four
#: words; unbounded filler matches across unrelated clauses.
_FILLER = r"(?:\s+[A-Za-z'\u4e00-\u9fff]+){0,4}?"

_COPULA = (
    r"(?:is|are|was|were|remains?|stays?|comes?|is\s+held|has\s+been|have\s+been|"
    r"will\s+be|be)"
)
_ADVERB = r"(?:\w+ly\s+)?"


GUARANTEE_RELATION = Relation(
    name=GUARANTEE,
    object_entities=(RETURN, CAPITAL, VALUE, OUTCOME),
    description="an outcome is made unconditional by a promise",
    frames=(
        Frame(
            ATTRIBUTIVE,
            rf"\bguaranteed\s+(?P<object>{_GUARANTEE_OBJECT})\b",
            ("predicate", "object"),
            "guaranteed + noun",
        ),
        Frame(
            PASSIVE,
            rf"\b(?P<object>{_GUARANTEE_OBJECT}){_FILLER}\s+{_COPULA}\s+{_ADVERB}"
            rf"(?P<predicate>guaranteed)\s+by\s+(?P<agent>[A-Za-z' ]{{2,40}})",
            ("predicate", "object", "agent"),
            "object + be + guaranteed + agent",
        ),
        Frame(
            COPULAR,
            rf"\b(?P<object>{_GUARANTEE_OBJECT}){_FILLER}\s+{_COPULA}\s+{_ADVERB}"
            rf"(?P<predicate>guaranteed)\b",
            ("predicate", "object"),
            "object + be + guaranteed",
        ),
        Frame(
            ACTIVE,
            rf"\b(?P<subject>{GUARANTORS.pattern})\s+(?:\w+ly\s+)?"
            rf"(?:do(?:es|did)?\s+|will\s+|would\s+|can\s+|could\s+|must\s+|shall\s+)?"
            rf"(?:not\s+|never\s+)?"
            rf"(?P<predicate>guarantee(?:s|d)?)\s+"
            rf"(?:a\s+|an\s+|the\s+|your\s+|our\s+|this\s+|these\s+|that\s+)?"
            rf"(?P<object>{_GUARANTEE_OBJECT})\b",
            ("predicate", "subject", "object"),
            "subject + guarantee + object",
        ),
        Frame(
            NOMINAL,
            rf"\b(?:a|the|its|our|their)\s+(?P<predicate>guarantee)\s+"
            rf"(?:of|on|for|over|that)\s+"
            rf"(?:your\s+|our\s+|the\s+|a\s+)?(?P<object>{_GUARANTEE_OBJECT})\b",
            ("predicate", "object"),
            "a guarantee of + object",
        ),
        Frame(
            NOMINAL,
            r"\b(?:is|are|was|were)\s+(?:a|the)\s+(?P<predicate>guarantee)\b"
            r"(?!\s+(?:of|on|for|that))",
            ("predicate",),
            "is a guarantee, object implicit",
        ),
    ),
)

RISK_REMOVED_RELATION = Relation(
    name=RISK_REMOVED,
    object_entities=(),
    description="risk is denied outright, without using the word guarantee",
    frames=(
        Frame(ATTRIBUTIVE, r"\brisk[-\s]?free\b", ("predicate",), "risk-free"),
        Frame(
            ATTRIBUTIVE,
            r"\b(?:no|zero|without)\s+risk\b",
            ("predicate",),
            "no risk",
            self_negating=True,
        ),
        Frame(
            ATTRIBUTIVE,
            r"\b(?:safe bet|sure thing|sure win|free money)\b",
            ("predicate",),
            "colloquial certainty",
        ),
        Frame(
            ACTIVE,
            r"\bcan(?:not|'t)\s+(?P<predicate>fail|lose|go wrong)\b",
            ("predicate",),
            "cannot fail or lose",
            self_negating=True,
        ),
        Frame(
            ATTRIBUTIVE,
            r"\b(?:impossible|no way)\s+to\s+lose\b",
            ("predicate",),
            "no way to lose",
            self_negating=True,
        ),
        Frame(
            COPULAR,
            r"\bnever\s+(?P<predicate>falls?|fallen|fails?|failed|loses?|lost|drops?|"
            r"dropped|declines?|declined)\b",
            ("predicate",),
            "never falls",
            self_negating=True,
        ),
        Frame(
            ATTRIBUTIVE,
            r"\bno way\s+(?:this|that|it|the|these|those)\b",
            ("predicate",),
            "no way this can happen",
            self_negating=True,
        ),
        Frame(
            ATTRIBUTIVE,
            r"(?:\u7a33\u8d5a\u4e0d\u8d54|\u5305\u8d5a|\u96f6\u98ce\u9669|\u65e0\u98ce\u9669|"
            r"\u4e0d\u4f1a\u4e8f|\u4fdd\u672c|\u5fc5\u8d5a|\u8d5a\u94b1)",
            ("predicate",),
            "Chinese risk denial",
            self_negating=True,
        ),
    ),
)

#: What a prediction is about: a market quantity, not an instrument. `The stock
#: will rise` predicts the stock's value, and VALUE covers the index and price.
_PREDICTION_SUBJECT = ENTITIES.group(VALUE, RETURN, REVENUE, OUTCOME, INSTRUMENT)

PREDICTION_RELATION = Relation(
    name=PREDICTION,
    object_entities=(VALUE, RETURN, REVENUE, OUTCOME),
    description="a future market outcome asserted as fact",
    frames=(
        Frame(
            ACTIVE,
            rf"\b(?P<subject>{_PREDICTION_SUBJECT}){_FILLER}\s+"
            rf"(?:will|shall|is\s+going\s+to)\s+"
            rf"(?:certainly\s+|definitely\s+|surely\s+)?"
            rf"(?P<predicate>{MOVEMENT_VERBS})\b",
            ("predicate", "subject"),
            "subject + will + movement verb",
        ),
        Frame(
            COPULAR,
            rf"\b(?P<subject>{_PREDICTION_SUBJECT}){_FILLER}\s+"
            rf"(?:is|are)\s+(?P<predicate>{CERTAINTY_ADJECTIVES})\s+to\s+"
            rf"(?:{MOVEMENT_VERBS})\b",
            ("predicate", "subject"),
            "subject + is certain to + movement verb",
        ),
        Frame(
            ACTIVE,
            rf"\b(?P<subject>{_PREDICTION_SUBJECT}){_FILLER}\s+"
            rf"(?P<predicate>{MOVEMENT_VERBS})\b[^.;]{{0,24}}?"
            rf"\b(?:next\s+(?:year|quarter|month)|by\s+\w+|from\s+here)\b",
            ("predicate", "subject"),
            "present-tense assertion with a future horizon",
        ),
        Frame(
            ACTIVE,
            rf"\b(?:expect(?:s|ed)?|project(?:s|ed)?|forecast(?:s|ed)?|"
            rf"predict(?:s|ed)?|anticipat(?:es|ed)|sees?)\b[^.;]{{0,30}}?\b"
            rf"(?P<subject>{_PREDICTION_SUBJECT}){_FILLER}\s+to\s+"
            rf"(?P<predicate>{MOVEMENT_VERBS})\b",
            ("predicate", "subject"),
            "reported expectation plus a to-infinitive movement verb",
        ),
    ),
)

ADVICE_RELATION = Relation(
    name=ADVICE,
    object_entities=(RETURN, CAPITAL, VALUE, OUTCOME, INSTRUMENT),
    description="an action-directive aimed at the reader plus a financial object",
    frames=(
        Frame(
            ACTIVE,
            rf"(?:^|(?<=[.!?;]\s))(?P<predicate>{DIRECTIVES})\b[^.;]{{0,40}}?"
            rf"\b(?P<object>{ADVICE_OBJECT})\b",
            ("predicate", "object"),
            "imperative directive plus object",
        ),
        Frame(
            COPULAR,
            rf"\b(?:you|readers?|investors?)\s+(?:should|ought\s+to|must)\s+"
            rf"(?P<predicate>{DIRECTIVES})\b[^.;]{{0,32}}?"
            rf"\b(?P<object>{ADVICE_OBJECT})\b",
            ("predicate", "object"),
            "you should + directive + object",
        ),
        Frame(
            NOMINAL,
            rf"\b(?:the\s+)?(?:sensible|obvious|best|only)\s+(?:move|choice|action)\b"
            rf"[^.;]{{0,40}}?\b(?P<object>{ADVICE_OBJECT})\b",
            ("predicate", "object"),
            "implicit directive naming the sensible move",
        ),
        Frame(
            ACTIVE,
            rf"(?P<predicate>{DIRECTIVES})\b[^.;]{{0,40}}?\b"
            rf"(?P<object>{ADVICE_OBJECT})\b",
            ("predicate", "object"),
            "directive verb plus object, anywhere in the sentence",
        ),
    ),
)

FINANCIAL_GUARANTEE = IntentPattern(
    pattern_id="v3-financial-guarantee",
    category="financial_guarantee",
    required_entities=(RETURN, CAPITAL, VALUE, OUTCOME),
    relations=(GUARANTEE_RELATION, RISK_REMOVED_RELATION),
    confidence=0.85,
    evidence=(
        "Guide v2 section 7: risk removed or an outcome made unconditional. "
        "Detected by relation, not by word order."
    ),
)

MARKET_PREDICTION = IntentPattern(
    pattern_id="v3-market-prediction",
    category="market_prediction",
    required_entities=(VALUE, RETURN, REVENUE, OUTCOME, INSTRUMENT),
    relations=(PREDICTION_RELATION,),
    confidence=0.8,
    evidence=(
        "Guide v2 section 2: an author-voice certainty about a future outcome "
        "is market_prediction, however it is worded."
    ),
)

INVESTMENT_ADVICE = IntentPattern(
    pattern_id="v3-investment-advice",
    category="investment_advice",
    required_entities=(RETURN, CAPITAL, VALUE, OUTCOME, INSTRUMENT),
    relations=(ADVICE_RELATION,),
    confidence=0.75,
    evidence=(
        "Guide v2 section 7: an action-directive aimed at the reader plus a "
        "financial object."
    ),
)

PATTERNS = PatternSet(
    name="intent-patterns-v3",
    lexicon=ENTITIES,
    patterns=(FINANCIAL_GUARANTEE, MARKET_PREDICTION, INVESTMENT_ADVICE),
    version="3.0.0",
)


def relation_names() -> tuple[str, ...]:
    """Every relation the v3 pattern set can report."""

    seen: dict[str, None] = {}
    for pattern in PATTERNS.patterns:
        for relation in pattern.relations:
            seen.setdefault(relation.name, None)
    return tuple(seen)


def pattern_for_category(category: str) -> IntentPattern | None:
    for pattern in PATTERNS.patterns:
        if pattern.category == category:
            return pattern
    return None


#: Which relations can produce which category. Used by the decision policy and
#: by the tests that check no relation is left unhandled.
RELATION_CATEGORY: dict[str, str] = {
    GUARANTEE: "financial_guarantee",
    RISK_REMOVED: "financial_guarantee",
    PREDICTION: "market_prediction",
    ADVICE: "investment_advice",
}
