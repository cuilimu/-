"""
agents/ — Multi-agent system for the Stock Simulation Engine.

Entry point: AgentPipeline in pipeline.py.

Architecture (see MULTI_AGENT_DESIGN.md):
  OrchestratorAgent
    ├── [parallel] FinanceAgent
    ├── [parallel] StatisticsAgent
    ├── [parallel] CodingAgent
    └── [parallel] VizAgent
            │
       AggregatorAgent
            │
       VerifierAgent ◄──┐
            │           │  (evaluator-optimizer loop, max 3 iterations)
       FixerAgent ──────┘
            │
       OutputAgent
"""
from stock_engine.agents.pipeline import AgentPipeline

__all__ = ["AgentPipeline"]
