"""Synthetic work-order fixtures for exercising the routing pipeline against drawings OTHER
than WO 9374 - different component combinations, assembly quantities, and (deliberately, for
test coverage) an unknown component and a missing-parameter case. These are SYNTHETIC: unlike
WO 9374 (verified against a real CAD drawing and indent sheet), they are not derived from an
actual MB drawing. They prove the ROUTING logic generalizes; they do not by themselves prove
real-world extraction accuracy on a new drawing - see README.md's "Generalization status".
"""
