"""Generalized CAD-to-indent routing layer.

Pipeline (per the spec):
  Drawing Input -> Drawing Extraction -> Component Identification -> Component Classification
  -> Parameter Mapping -> Manufacturing Rule Selection -> Dimension Calculation
  -> Engineering Validation -> BOM Quantity Calculation -> Indent JSON Generation

This package does NOT reimplement any of that math - it only identifies which EXISTING
calculator (engineering_engine.calculations.*) applies to a given component and calls it with
the right parameters. See registry.py for the component catalog and component_builders.py for
the per-component adapters that do the actual calling.
"""
