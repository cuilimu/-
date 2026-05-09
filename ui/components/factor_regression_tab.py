"""
ui/components/factor_regression_tab.py
Backward-compatible shim -> delegates to factor_workspace_tab.
"""
from stock_engine.ui.components.factor_workspace_tab import render_factor_workspace_tab

def render_factor_regression_tab(single_result, group_results, config, mode=None):
    render_factor_workspace_tab(
        single_result=single_result,
        group_results=group_results or {},
        config=config,
        mode=mode or "single",
    )
