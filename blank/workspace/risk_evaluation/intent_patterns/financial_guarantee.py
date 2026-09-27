"""The `financial_guarantee` pattern set.

Only `financial_guarantee` is implemented, as the phase requires. The point is
not to widen coverage but to replace a word-order rule with a relation rule.

The blind spot, stated precisely. The old rule for this category is

    risk_negation  ->  \\bguaranteed\\s+(?:return|returns|profit|profits|gain|gains|
                                          income|outcome)\\b

`guaranteed` matched only when it *precedes* the noun it modifies. English
realises the same relation at least three other ways:

    copular       This return is guaranteed.      adjective after the copula
    passive       Returns are guaranteed by us.   participle plus agent
    active        We guarantee this return.       the verb form

and all three were invisible. The category is `block` severity, so the miss is
the most consequential one found in Phase 8.1.

The GUARANTEE relation below covers attributive, copular, passive, active and
nominal realisations. A second relation, RISK_REMOVED, carries the rest of what
the old rule matched -- `risk-free`, `no risk`, `cannot lose`, `never falls` --
so that the new layer is a **superset** of the old one. Without it, any change in
recall could equally be caused by dropping coverage, and the comparison would
prove nothing.
"""

from __future__ import annotations

from .model import (
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


#: The things a guarantee can be about. These are the "object" role.
ENTITIES = EntityLexicon(
    {
        "RETURN": EntityType(
            "RETURN",
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
                r"\u6536\u76ca",  # 收益
                r"\u56de\u62a5",  # 回报
                r"\u5229\u6da6",  # 利润
            ),
            "what the investment pays out",
        ),
        "CAPITAL": EntityType(
            "CAPITAL",
            (
                r"capital",
                r"principal",
                r"your money",
                r"your investment",
                r"your savings",
                r"your stake",
                r"the deposit",
                r"your deposit",
                r"the investment",
                r"\u672c\u91d1",  # 本金
                r"\u6295\u5165\u7684\u94b1",  # 投入的钱
            ),
            "what the investor put in",
        ),
        "VALUE": EntityType(
            "VALUE",
            (
                r"values?",
                r"valuations?",
                r"prices?",
                r"the share price",
                r"the unit price",
                r"the balance",
                r"\u4ef7\u683c",  # 价格
                r"\u4ef7\u503c",  # 价值
            ),
            "a measured worth",
        ),
        "OUTCOME": EntityType(
            "OUTCOME",
            (
                r"outcomes?",
                r"results?",
                r"performance",
                r"the outcome",
                r"\u7ed3\u679c",  # 结果
            ),
            "how it turns out",
        ),
    }
)

#: Who can be the guarantor, for the active frame.
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
        r"\u6211\u4eec",  # 我们
    ),
    "who makes the promise",
)

#: A short noun phrase between the object and its predicate, so that
#: `The value of your investment is guaranteed` is matched. Bounded to four
#: words: unbounded filler makes the frame match across unrelated clauses.
_FILLER = r"(?:\s+[A-Za-z'\u4e00-\u9fff]+){0,4}?"

_COPULA = r"(?:is|are|was|were|remains?|stays?|comes?|is\s+held|has\s+been|have\s+been|will\s+be|be)"

#: An adverb may sit between the copula and the participle: `is reportedly
#: guaranteed`, `is fully guaranteed`. `not` is not an -ly adverb, so this does
#: not swallow a negator.
_ADVERB = r"(?:\w+ly\s+)?"

_OBJECT = ENTITIES.group("RETURN", "CAPITAL", "VALUE", "OUTCOME")

GUARANTEE = Relation(
    name="GUARANTEE",
    object_entities=("RETURN", "CAPITAL", "VALUE", "OUTCOME"),
    description="an outcome is made unconditional by a promise",
    frames=(
        Frame(
            ATTRIBUTIVE,
            rf"\bguaranteed\s+(?P<object>{_OBJECT})\b",
            ("predicate", "object"),
            "guaranteed + noun, the only form the old rule matched",
        ),
        Frame(
            PASSIVE,
            rf"\b(?P<object>{_OBJECT}){_FILLER}\s+{_COPULA}\s+{_ADVERB}"
            rf"(?P<predicate>guaranteed)\s+by\s+(?P<agent>[A-Za-z' ]{{2,40}})",
            ("predicate", "object", "agent"),
            "object + be + guaranteed + agent",
        ),
        Frame(
            COPULAR,
            rf"\b(?P<object>{_OBJECT}){_FILLER}\s+{_COPULA}\s+{_ADVERB}"
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
            rf"(?P<object>{_OBJECT})\b",
            ("predicate", "subject", "object"),
            "subject + guarantee + object, with optional auxiliary and negator",
        ),
        Frame(
            NOMINAL,
            rf"\b(?:a|the|its|our|their)\s+(?P<predicate>guarantee)\s+"
            rf"(?:of|on|for|over|that)\s+"
            rf"(?:your\s+|our\s+|the\s+|a\s+)?(?P<object>{_OBJECT})\b",
            ("predicate", "object"),
            "a guarantee of + object",
        ),
        Frame(
            NOMINAL,
            r"\b(?:is|are|was|were)\s+(?:a|the)\s+(?P<predicate>guarantee)\b"
            r"(?!\s+(?:of|on|for|that))",
            ("predicate",),
            "is a guarantee, with the object left implicit",
        ),
    ),
)

RISK_REMOVED = Relation(
    name="RISK_REMOVED",
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
            r"\u4e0d\u4f1a\u4e8f|\u4fdd\u672c|\u5fc5\u8d5a|\u8eba\u8d5a)",
            ("predicate",),
            "Chinese risk denial",
            self_negating=True,
        ),
    ),
)

FINANCIAL_GUARANTEE = IntentPattern(
    pattern_id="financial-guarantee-relational-v1",
    category="financial_guarantee",
    required_entities=("RETURN", "CAPITAL", "VALUE", "OUTCOME"),
    relations=(GUARANTEE, RISK_REMOVED),
    confidence=0.8,
    evidence=(
        "Guide v2 section 7: the category is risk removed or an outcome made "
        "unconditional. The relation is what carries the meaning, not the word "
        "order, so every frame that realises it counts."
    ),
)

PATTERNS = PatternSet(
    name="intent-patterns",
    lexicon=ENTITIES,
    patterns=(FINANCIAL_GUARANTEE,),
    version="1.0.0",
)


def guarantee_frames() -> tuple[str, ...]:
    """Frame kinds the GUARANTEE relation can realise."""

    return GUARANTEE.kinds
