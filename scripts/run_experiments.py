import sys
from pathlib import Path
import copy
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gameday_lab.sim.config import load_config
from gameday_lab.sim.engine import run_scenario
from gameday_lab.factory import build_client
from gameday_lab.client import ResilientClient

def run_exp1():
    print("=== EXPERIMENT 1: RETRY BUDGET AS LAST LINE OF DEFENSE ===")
    cfg_base = load_config("configs/gameday.yaml", "configs/scenarios.yaml")
    
    for scen in ["G2_overload_storm", "G3_brownout"]:
        print(f"\nScenario: {scen}")
        # Case A: Budget kept, breaker misconfigured
        cfg_a = copy.deepcopy(cfg_base)
        cfg_a.client["breaker"]["min_calls"] = 1_000_000_000
        cfg_a.client["max_attempts_per_provider"] = 5
        sim_a = run_scenario(cfg_a, scen, build_client("resilient", cfg_a, seed=25), seed=25)
        m_a = sim_a.metrics()
        print(f"  (a) With budget: avail={m_a['availability']:.4f}, p95={m_a['latency_p95_s']:.3f}, ampl={m_a['amplification']:.3f}, retry={m_a['retry_ratio']:.3f}, recov={m_a['recovery_s']:.1f}, cost/turn={m_a['cost_per_good_turn']:.3f}")
        
        # Case B: Budget disabled, breaker misconfigured
        cfg_b = copy.deepcopy(cfg_base)
        cfg_b.client["breaker"]["min_calls"] = 1_000_000_000
        cfg_b.client["max_attempts_per_provider"] = 5
        cfg_b.client["retry_budget_ratio"] = 100.0
        cfg_b.client["retry_budget_max_tokens"] = 1.0e9
        cfg_b.client["retry_budget_min_per_s"] = 1.0e6
        sim_b = run_scenario(cfg_b, scen, build_client("resilient", cfg_b, seed=25), seed=25)
        m_b = sim_b.metrics()
        print(f"  (b) Without budget: avail={m_b['availability']:.4f}, p95={m_b['latency_p95_s']:.3f}, ampl={m_b['amplification']:.3f}, retry={m_b['retry_ratio']:.3f}, recov={m_b['recovery_s']:.1f}, cost/turn={m_b['cost_per_good_turn']:.3f}")

def run_exp2():
    print("\n=== EXPERIMENT 2: TIMEOUT 30s ===")
    cfg_base = load_config("configs/gameday.yaml", "configs/scenarios.yaml")
    for scen in ["G4_slow_region", "G6_provider_outage"]:
        # Baseline (8s)
        sim_base = run_scenario(cfg_base, scen, build_client("resilient", cfg_base, seed=25), seed=25)
        m_base = sim_base.metrics()
        
        # 30s timeout
        cfg_30 = copy.deepcopy(cfg_base)
        cfg_30.client["attempt_timeout_s"] = 30.0
        sim_30 = run_scenario(cfg_30, scen, build_client("resilient", cfg_30, seed=25), seed=25)
        m_30 = sim_30.metrics()
        
        print(f"Scenario: {scen}")
        print(f"  timeout=8.0s : avail={m_base['availability']:.4f}, p95={m_base['latency_p95_s']:.3f}, ampl={m_base['amplification']:.3f}, cost/turn={m_base['cost_per_good_turn']:.3f}")
        print(f"  timeout=30.0s: avail={m_30['availability']:.4f}, p95={m_30['latency_p95_s']:.3f}, ampl={m_30['amplification']:.3f}, cost/turn={m_30['cost_per_good_turn']:.3f}")

def run_exp3():
    print("\n=== EXPERIMENT 3: NO TOOL FILTER IN LADDER ===")
    cfg_base = load_config("configs/gameday.yaml", "configs/scenarios.yaml")
    scen = "G6_provider_outage"
    
    # Subclass client to remove tool filtering
    class UnfilteredClient(ResilientClient):
        def ladder(self, task: str) -> list[str]:
            # deliberate omission of tool filtering
            return list(self.order)
            
    client = UnfilteredClient(cfg_base.provider_infos(), cfg_base.fallback_order, cfg_base.client, seed=25)
    sim = run_scenario(cfg_base, scen, client, seed=25)
    m = sim.metrics()
    print(f"Scenario: {scen} without tool filtering:")
    print(f"  avail={m['availability']:.4f}, p95={m['latency_p95_s']:.3f}, incompatible_routes={m['incompatible_routes']}")
    print(f"  attempts_by_provider={m['attempts_by_provider']}")
    print(f"  errors_by_code={m['errors_by_code']}")

def run_cache_experiments():
    print("\n=== CACHE EXPERIMENTS (PART G) ===")
    cfg_base = load_config("configs/gameday.yaml", "configs/scenarios_cache.yaml")
    scen = "C1_faq_outage"
    
    print("\n--- Cache Experiment 1: Similarity Threshold (0.80 vs 0.92 vs 0.97) ---")
    for thresh in [0.80, 0.92, 0.97]:
        cfg = copy.deepcopy(cfg_base)
        cfg.cache["similarity_threshold"] = thresh
        sim = run_scenario(cfg, scen, build_client("cached", cfg, seed=25), seed=25)
        m = sim.metrics()
        print(f"  threshold={thresh:.2f}: hit={m['cache_hit_ratio']:.3f}, wrong={m['wrong_answers']}, outdated={m['outdated_answers']}, avail={m['availability']:.4f}, faq_avail={m['faq_availability']:.4f}, cost/turn={m['cost_per_good_turn']:.3f}")
        if m.get("wrong_answers_by_reason"):
            print(f"    reasons: {m['wrong_answers_by_reason']}")

    print("\n--- Cache Experiment 2: TTL (30 vs 60 vs 300) ---")
    for ttl in [30.0, 60.0, 300.0]:
        cfg = copy.deepcopy(cfg_base)
        cfg.cache["ttl_s"] = ttl
        sim = run_scenario(cfg, scen, build_client("cached", cfg, seed=25), seed=25)
        m = sim.metrics()
        print(f"  ttl={ttl}s: outdated={m['outdated_answers']}, hit={m['cache_hit_ratio']:.3f}, wrong={m['wrong_answers']}, cost/turn={m['cost_per_good_turn']:.3f}, faq_avail={m['faq_availability']:.4f}")

    print("\n--- Cache Experiment 3: Stale-if-error (max_stale_s: 0 vs 300) ---")
    for max_stale in [0.0, 300.0]:
        cfg = copy.deepcopy(cfg_base)
        cfg.cache["max_stale_s"] = max_stale
        sim = run_scenario(cfg, scen, build_client("cached", cfg, seed=25), seed=25)
        m = sim.metrics()
        print(f"  max_stale_s={max_stale}s: faq_avail={m['faq_availability']:.4f}, avail={m['availability']:.4f}, stale_served={m['stale_served']}, hit={m['cache_hit_ratio']:.3f}")

if __name__ == "__main__":
    run_exp1()
    run_exp2()
    run_exp3()
    run_cache_experiments()
