"""Template discovery by deterministic agglomerative clustering (Phase M2).

Turns the M1 open questions *"when are two templates the same?"* and *"what does
'recurring' mean?"* into a concrete, auditable procedure:

1. compute the pairwise similarity matrix (:mod:`multimodal_creator.similarity`),
2. repeatedly merge the most similar pair of clusters while that similarity
   meets the threshold,
3. report each surviving cluster with its evidence, members, and a
   deterministic identifier.

Deliberate properties
---------------------

**Not hardcoded.** No cluster membership is ever supplied by a caller. Clusters
are a function of the similarity contract and the threshold alone.

**Deterministic.** Ties are broken by cluster identifier, not by input order, so
the same sample set always produces the same clusters with the same ids — even
if the samples are presented in a different order. There is no randomness, no
seed, and no iteration-order dependence.

**Evidence-carrying.** Every cluster records its threshold, the mean and minimum
internal similarity, the pairs that justified each merge, and the structural
properties its members agree on. A cluster that cannot show this evidence is not
reported as a template.
"""

from .template_discovery import (
    DEFAULT_SIMILARITY_THRESHOLD,
    MIN_CLUSTER_SIZE,
    RECURRENCE_MIN,
    Cluster,
    ClusterEvidence,
    ClusterMember,
    MergeStep,
    TemplateClusterError,
    TemplateDiscovery,
    discover_templates,
    dominant_layout_class,
)

__all__ = [
    "DEFAULT_SIMILARITY_THRESHOLD",
    "MIN_CLUSTER_SIZE",
    "RECURRENCE_MIN",
    "Cluster",
    "ClusterEvidence",
    "ClusterMember",
    "MergeStep",
    "TemplateClusterError",
    "TemplateDiscovery",
    "discover_templates",
    "dominant_layout_class",
]
