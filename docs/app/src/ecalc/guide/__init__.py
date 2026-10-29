"""Plain-language guide for every component and skill, personalised with the user's calculated package.

Knowledge follows Boxwell, *Solar Electricity Handbook* (2012) - paraphrased, with § references - and is
updated with current practice (LiFePO4, MPPT, TOPCon modules, NEPQA-2025, Nepal grid rules). Every number
either comes from the user's own calculated package or is clearly labelled "typical".
"""

from .components import component_guide, series_parallel_explainer
from .skills import legal_and_safety_stop_points, skills

__all__ = ["component_guide", "series_parallel_explainer", "skills", "legal_and_safety_stop_points"]
