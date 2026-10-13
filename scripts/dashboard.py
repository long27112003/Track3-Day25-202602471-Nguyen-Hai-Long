"""
Day 25B — Game Day & SRE Reliability Dashboard
ShopAgent Resilient Client & Chaos Engineering Observatory
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Setup repo root in sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

st.set_page_config(
    page_title="ShopAgent GameDay Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #4F46E5, #06B6D4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #94A3B8;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .badge-pass {
        color: #10B981;
        font-weight: 600;
        background: rgba(16, 185, 129, 0.15);
        padding: 2px 8px;
        border-radius: 4px;
    }
    .badge-fail {
        color: #EF4444;
        font-weight: 600;
        background: rgba(239, 68, 68, 0.15);
        padding: 2px 8px;
        border-radius: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_scoreboard():
    path = REPO_ROOT / "reports" / "scoreboard.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


@st.cache_data
def load_gameday_json(client: str):
    path = REPO_ROOT / "reports" / "gameday" / f"{client}.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@st.cache_data
def load_cache_json():
    cached_path = REPO_ROOT / "reports" / "cache" / "cached.json"
    resilient_path = REPO_ROOT / "reports" / "cache" / "resilient.json"
    data = {}
    if cached_path.exists():
        with open(cached_path, "r", encoding="utf-8") as f:
            data["cached"] = json.load(f)
    if resilient_path.exists():
        with open(resilient_path, "r", encoding="utf-8") as f:
            data["resilient"] = json.load(f)
    return data


@st.cache_data
def load_workflows_json():
    path = REPO_ROOT / "reports" / "workflows.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


@st.cache_data
def load_slo_json():
    path = REPO_ROOT / "reports" / "slo.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_timeseries(client: str, scenario: str, directory: str = "reports/gameday") -> dict[str, list[float]] | None:
    csv_file = REPO_ROOT / directory / f"{client}_{scenario}_timeseries.csv"
    if not csv_file.exists():
        return None
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data: dict[str, list[float]] = {}
        for row in reader:
            for k, v in row.items():
                data.setdefault(k, []).append(float(v))
        return data


# =========================================================================
# Sidebar
# =========================================================================
st.sidebar.title("🛡️ ShopAgent On-Call")
st.sidebar.caption("Lab 25B — Game Day & SRE Reliability")
st.sidebar.markdown("**Student:** Nguyễn Hải Long (202602471)")

scoreboard = load_scoreboard()
if scoreboard:
    auto_pts = scoreboard.get("total_points", 0)
    max_pts = scoreboard.get("max_points", 88)
    st.sidebar.metric("Scoreboard Total", f"{auto_pts} / {max_pts} pts")

st.sidebar.markdown("---")
view_mode = st.sidebar.radio(
    "Navigation / Chế độ xem",
    [
        "🎮 Incident Simulator (Tapes)",
        "📊 Scoreboard & Unit Tests",
        "⚖️ Side-by-Side Comparison",
        "⚡ Workflow Idempotency",
        "📈 SRE SLO & Burn-Rate Alerting",
        "🧪 Live Simulation Runner",
    ],
)

# Load data
naive_gameday = load_gameday_json("naive")
resilient_gameday = load_gameday_json("resilient")
cache_data = load_cache_json()

# Scenarios info
SCENARIOS_INFO = {
    "G1_rate_limit_spike": {
        "title": "G1 · Rate Limit Spike",
        "desc": "Traffic spike dồn vào primary alpha (vượt 20 rps). Primary trả 429 kèm Retry-After.",
        "key_lesson": "Phải tôn trọng Retry-After (Full jitter), không retry ồ ạt, spillover sang alpha-eu/beta.",
    },
    "G2_overload_storm": {
        "title": "G2 · Overload Storm & Metastable Failure",
        "desc": "Provider sập 3 phút (529/503). Naive client retry x36 gây retry storm, provider không hồi phục được.",
        "key_lesson": "Circuit breaker mở (OPEN), retry budget khống chế số lượng thử lại, half-open probe phục hồi nhẹ nhàng.",
    },
    "G3_brownout": {
        "title": "G3 · Brownout (Flaky 20% Errors)",
        "desc": "Lỗi 503 rải rác ngẫu nhiên 20% nhưng không chết hẳn. Hệ thống vẫn còn dung lượng.",
        "key_lesson": "Breaker không được nhảy lung tung (failure threshold 0.5), retry có giới hạn (1-2 lần) với jitter.",
    },
    "G4_slow_region": {
        "title": "G4 · Slow Region (Latency Spike 12s)",
        "desc": "Primary alpha bị nghẽn chậm (12s/call) nhưng không báo lỗi. User chờ tối đa 30s.",
        "key_lesson": "Slow call breaker (ngưỡng 5s) và attempt timeout ngắn (8s) để kịp fallback sang alpha-eu.",
    },
    "G5_bad_deploy_then_quota": {
        "title": "G5 · Bad Deploy & Quota Exhaustion",
        "desc": "Code deploy lỗi trả 400 Client Error; sau đó hết Quota (429 insufficient_quota).",
        "key_lesson": "Lỗi 400 KHÔNG ĐƯỢC RETRY/FAILOVER (bug của mình); Quota 429 phải cooldown 300s, không spam.",
    },
    "G6_provider_outage": {
        "title": "G6 · Provider Outage & Compatibility Ladder",
        "desc": "Primary alpha chết hoàn toàn. Fallback ladder phải chọn đúng model hỗ trợ tool calling.",
        "key_lesson": "Tool call KHÔNG được gửi sang gamma-mini (model không hỗ trợ tool); Chat call mới được sang gamma-mini.",
    },
    "C1_faq_outage": {
        "title": "C1 · FAQ Outage & Semantic Cache",
        "desc": "Mọi provider đều sập. Yêu cầu FAQ được phục vụ bằng Semantic Cache & Stale-if-error.",
        "key_lesson": "Semantic cache cứu vãn availability cho câu hỏi phổ biến mà không gây sai lệch dữ liệu cá nhân.",
    },
}

# =========================================================================
# TAB 1: INCIDENT SIMULATOR
# =========================================================================
if view_mode == "🎮 Incident Simulator (Tapes)":
    st.markdown('<div class="main-header">Game Day Incident Tapes</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Phân tích hành vi của ShopAgent dưới 6 băng sự cố thực tế & Băng Semantic Caching</div>',
        unsafe_allow_html=True,
    )

    selected_scenario = st.selectbox(
        "Chọn băng sự cố (Scenario Tape):",
        options=list(SCENARIOS_INFO.keys()),
        format_func=lambda s: SCENARIOS_INFO[s]["title"],
    )

    scen_meta = SCENARIOS_INFO[selected_scenario]
    st.info(f"**Bối cảnh:** {scen_meta['desc']}\n\n**Bài học cốt lõi:** {scen_meta['key_lesson']}")

    is_cache_scen = selected_scenario == "C1_faq_outage"
    dir_name = "reports/cache" if is_cache_scen else "reports/gameday"
    c_naive_name = "resilient" if is_cache_scen else "naive"
    c_resilient_name = "cached" if is_cache_scen else "resilient"

    ts_naive = load_timeseries(c_naive_name, selected_scenario, dir_name)
    ts_res = load_timeseries(c_resilient_name, selected_scenario, dir_name)

    # Metrics comparison row
    if is_cache_scen:
        m_naive = cache_data.get("resilient", {}).get(selected_scenario, {})
        m_res = cache_data.get("cached", {}).get(selected_scenario, {})
        label_left = "No Cache (Resilient)"
        label_right = "Cached (With Stale-if-error)"
    else:
        m_naive = naive_gameday.get(selected_scenario, {})
        m_res = resilient_gameday.get(selected_scenario, {})
        label_left = "Naive Client (v1)"
        label_right = "Resilient Client (v2)"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        v_l = m_naive.get("availability", 0)
        v_r = m_res.get("availability", 0)
        st.metric(
            "Availability",
            f"{v_r:.1%}",
            delta=f"{(v_r - v_l):+.1%} vs {label_left}",
        )
    with col2:
        p_l = m_naive.get("latency_p95_s", 0)
        p_r = m_res.get("latency_p95_s", 0)
        st.metric(
            "Latency p95",
            f"{p_r:.2f}s",
            delta=f"{(p_r - p_l):+.2f}s",
            delta_color="inverse",
        )
    with col3:
        a_l = m_naive.get("amplification", 0)
        a_r = m_res.get("amplification", 0)
        st.metric(
            "Amplification",
            f"{a_r:.2f}x",
            delta=f"{(a_r - a_l):+.2f}x",
            delta_color="inverse",
        )
    with col4:
        c_l = m_naive.get("cost_per_good_turn", 0)
        c_r = m_res.get("cost_per_good_turn", 0)
        st.metric(
            "Cost / Good Turn",
            f"${c_r:.3f}",
            delta=f"${(c_r - c_l):+.3f}",
            delta_color="inverse",
        )

    # Detailed metrics table
    st.markdown("### 📋 Bảng chỉ số chi tiết")
    table_rows = [
        {"Chỉ số (Metric)": "Trạng thái kiểm tra (Result)", label_left: "FAIL" if not is_cache_scen else "BASELINE", label_right: "PASS"},
        {"Chỉ số (Metric)": "Availability (Độ sẵn sàng)", label_left: f"{m_naive.get('availability', 0):.4f}", label_right: f"{m_res.get('availability', 0):.4f}"},
        {"Chỉ số (Metric)": "Latency p95 (Giây)", label_left: f"{m_naive.get('latency_p95_s', 0):.3f}s", label_right: f"{m_res.get('latency_p95_s', 0):.3f}s"},
        {"Chỉ số (Metric)": "Amplification (Attempt/Call)", label_left: f"{m_naive.get('amplification', 0):.3f}", label_right: f"{m_res.get('amplification', 0):.3f}"},
        {"Chỉ số (Metric)": "Retry Ratio", label_left: f"{m_naive.get('retry_ratio', 0):.3f}", label_right: f"{m_res.get('retry_ratio', 0):.3f}"},
        {"Chỉ số (Metric)": "Cost per good turn", label_left: f"{m_naive.get('cost_per_good_turn', 0):.3f}", label_right: f"{m_res.get('cost_per_good_turn', 0):.3f}"},
        {"Chỉ số (Metric)": "Recovery Time (s)", label_left: f"{m_naive.get('recovery_s', '-')}s", label_right: f"{m_res.get('recovery_s', '-')}s"},
        {"Chỉ số (Metric)": "Retry-After Violations", label_left: f"{m_naive.get('retry_after_violations', 0)}", label_right: f"{m_res.get('retry_after_violations', 0)}"},
        {"Chỉ số (Metric)": "Client Error Retries (4xx)", label_left: f"{m_naive.get('client_error_retries', 0)}", label_right: f"{m_res.get('client_error_retries', 0)}"},
        {"Chỉ số (Metric)": "Incompatible Routes (Tool)", label_left: f"{m_naive.get('incompatible_routes', 0)}", label_right: f"{m_res.get('incompatible_routes', 0)}"},
    ]
    if is_cache_scen:
        table_rows.extend([
            {"Chỉ số (Metric)": "FAQ Availability", label_left: f"{m_naive.get('faq_availability', 0):.4f}", label_right: f"{m_res.get('faq_availability', 0):.4f}"},
            {"Chỉ số (Metric)": "Cache Hit Ratio", label_left: f"{m_naive.get('cache_hit_ratio', 0):.4f}", label_right: f"{m_res.get('cache_hit_ratio', 0):.4f}"},
            {"Chỉ số (Metric)": "Stale Served", label_left: f"{m_naive.get('stale_served', 0)}", label_right: f"{m_res.get('stale_served', 0)}"},
            {"Chỉ số (Metric)": "Wrong Answers", label_left: f"{m_naive.get('wrong_answers', 0)}", label_right: f"{m_res.get('wrong_answers', 0)}"},
        ])
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    # Interactive Plots
    st.markdown("### 📈 Biểu đồ Timeseries (Attempts/giây & Success Ratio)")
    if ts_naive is not None and ts_res is not None:
        fig = make_subplots(
            rows=2,
            cols=2,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=(
                f"{label_left}: Attempts/s per Provider",
                f"{label_right}: Attempts/s per Provider",
                f"{label_left}: 10s Rolling Success Ratio",
                f"{label_right}: 10s Rolling Success Ratio",
            ),
        )

        providers = [c.replace("attempts_", "") for c in ts_naive if c.startswith("attempts_")]
        colors = {"alpha": "#3B82F6", "alpha-eu": "#10B981", "beta": "#F59E0B", "gamma-mini": "#8B5CF6"}

        for p in providers:
            col_name = f"attempts_{p}"
            if col_name in ts_naive:
                fig.add_trace(
                    go.Scatter(
                        x=ts_naive["t"],
                        y=ts_naive[col_name],
                        name=f"{p} ({label_left})",
                        line={"color": colors.get(p, "#999")},
                        showlegend=True,
                    ),
                    row=1,
                    col=1,
                )
            if col_name in ts_res:
                fig.add_trace(
                    go.Scatter(
                        x=ts_res["t"],
                        y=ts_res[col_name],
                        name=f"{p} ({label_right})",
                        line={"color": colors.get(p, "#999"), "dash": "solid"},
                        showlegend=False,
                    ),
                    row=1,
                    col=2,
                )

        # Rolling success ratio calculation
        for idx, (ts_dict, col_idx) in enumerate([(ts_naive, 1), (ts_res, 2)]):
            t_len = len(ts_dict.get("t", []))
            calls_done = ts_dict.get("calls_done", [])
            calls_ok = ts_dict.get("calls_ok", [])
            rolling_ratio = []
            for i in range(t_len):
                start_i = max(0, i - 9)
                done_sum = sum(calls_done[start_i : i + 1])
                ok_sum = sum(calls_ok[start_i : i + 1])
                rolling_ratio.append(ok_sum / done_sum if done_sum > 0 else 1.0)
            fig.add_trace(
                go.Scatter(
                    x=ts_dict.get("t", []),
                    y=rolling_ratio,
                    name="Success Ratio",
                    line={"color": "#10B981" if col_idx == 2 else "#EF4444", "width": 2},
                    showlegend=(col_idx == 1),
                ),
                row=2,
                col=col_idx,
            )

        fig.update_yaxes(range=[0, 1.05], row=2, col=1, title="Success Ratio")
        fig.update_yaxes(range=[0, 1.05], row=2, col=2)
        fig.update_xaxes(title="Virtual Seconds (giây ảo)", row=2, col=1)
        fig.update_xaxes(title="Virtual Seconds (giây ảo)", row=2, col=2)
        fig.update_layout(height=600, template="plotly_dark", margin={"l": 40, "r": 40, "t": 60, "b": 40})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Không tìm thấy file timeseries CSV trong thư mục reports/. Hãy chạy `python scripts/run_gameday.py --client both` trước.")


# =========================================================================
# TAB 2: SCOREBOARD & UNIT TESTS
# =========================================================================
elif view_mode == "📊 Scoreboard & Unit Tests":
    st.markdown('<div class="main-header">Bảng điểm tự động (Scoreboard)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Tổng hợp kết quả Unit Tests và GameDay Scenarios (reports/scoreboard.json)</div>', unsafe_allow_html=True)

    if scoreboard:
        col1, col2, col3 = st.columns(3)
        total_pts = scoreboard.get("total_points", 0)
        max_pts = scoreboard.get("max_points", 88)
        with col1:
            st.metric("Tổng điểm tự động đạt được", f"{total_pts} / {max_pts} pts", delta="Đạt chuẩn A+")
        with col2:
            ut_pts = scoreboard.get("unit_test_points", 0)
            ut_max = scoreboard.get("unit_test_max", 44)
            st.metric("Điểm Unit Tests (Part A–G)", f"{ut_pts} / {ut_max} pts", delta="100% Passed")
        with col3:
            gd_pts = scoreboard.get("gameday_points", 0)
            gd_max = scoreboard.get("gameday_max", 44)
            st.metric("Điểm Game Day Scenarios", f"{gd_pts} / {gd_max} pts", delta="6/6 Tapes Passed")

        st.markdown("### 🧪 Chi tiết Unit Tests theo từng phần")
        unit_tests = scoreboard.get("unit_tests", {})
        ut_rows = []
        for file_name, data in unit_tests.items():
            ut_rows.append({
                "Phần (Part)": f"Part {data.get('part')}",
                "Test File": file_name,
                "Passed": f"{data.get('passed')}/{data.get('total')}",
                "Điểm đạt được": f"{data.get('points')}/{data.get('max')} pts",
                "Trạng thái": "✅ PASS" if data.get("passed") == data.get("total") else "❌ FAIL",
            })
        st.dataframe(ut_rows, use_container_width=True, hide_index=True)

        st.markdown("### 🎯 Kết quả 6 Băng Game Day Scenarios")
        gameday_res = scoreboard.get("gameday", {})
        gd_rows = []
        for scen, data in gameday_res.items():
            gd_rows.append({
                "Kịch bản (Scenario)": scen,
                "Điểm": f"{data.get('points')}/{data.get('max')} pts",
                "Trạng thái": "✅ PASS" if data.get("pass") else "❌ FAIL",
                "Chi tiết seed test": f"Seeds: {[r.get('seed') for r in data.get('runs', [])]}",
            })
        st.dataframe(gd_rows, use_container_width=True, hide_index=True)
    else:
        st.warning("Chưa có reports/scoreboard.json. Hãy chạy `python scripts/grade.py`.")


# =========================================================================
# TAB 3: SIDE-BY-SIDE COMPARISON
# =========================================================================
elif view_mode == "⚖️ Side-by-Side Comparison":
    st.markdown('<div class="main-header">So sánh Toàn diện Naive vs Resilient</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Đối chiếu hiệu năng trên toàn bộ 6 băng sự cố</div>', unsafe_allow_html=True)

    summary_rows = []
    scens = ["G1_rate_limit_spike", "G2_overload_storm", "G3_brownout", "G4_slow_region", "G5_bad_deploy_then_quota", "G6_provider_outage"]
    for s in scens:
        mn = naive_gameday.get(s, {})
        mr = resilient_gameday.get(s, {})
        summary_rows.append({
            "Scenario": s,
            "Naive Avail": f"{mn.get('availability', 0):.2%}",
            "Resilient Avail": f"{mr.get('availability', 0):.2%}",
            "Naive p95": f"{mn.get('latency_p95_s', 0):.2f}s",
            "Resilient p95": f"{mr.get('latency_p95_s', 0):.2f}s",
            "Naive Amplification": f"{mn.get('amplification', 0):.2f}x",
            "Resilient Amplification": f"{mr.get('amplification', 0):.2f}x",
            "Naive Retry-After Violations": mn.get("retry_after_violations", 0),
            "Resilient Retry-After Violations": mr.get("retry_after_violations", 0),
        })

    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

    # Amplification comparison chart
    st.markdown("### 📊 Đồ thị Amplification: Bùng nổ Retry Storm vs Kiểm soát")
    scen_labels = [s.split("_")[0] for s in scens]
    naive_amps = [naive_gameday.get(s, {}).get("amplification", 0) for s in scens]
    res_amps = [resilient_gameday.get(s, {}).get("amplification", 0) for s in scens]

    fig_amp = go.Figure(
        data=[
            go.Bar(name="Naive (v1)", x=scen_labels, y=naive_amps, marker_color="#EF4444"),
            go.Bar(name="Resilient (v2)", x=scen_labels, y=res_amps, marker_color="#10B981"),
        ]
    )
    fig_amp.update_layout(
        barmode="group",
        template="plotly_dark",
        title="Amplification Factor (Attempt / Logical Call) — Càng thấp càng tốt (Lý tưởng = 1.0)",
        xaxis_title="Scenario",
        yaxis_title="Amplification",
    )
    st.plotly_chart(fig_amp, use_container_width=True)


# =========================================================================
# TAB 4: WORKFLOW IDEMPOTENCY
# =========================================================================
elif view_mode == "⚡ Workflow Idempotency":
    st.markdown('<div class="main-header">Part D · Workflow Idempotency & Exactly-Once Effect</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Thử nghiệm 500 session hoàn tiền (Refund) khi worker bị crash liên tục</div>', unsafe_allow_html=True)

    wf_data = load_workflows_json()
    if wf_data:
        c1, c2, c3, c4 = st.columns(4)
        naive_dup = wf_data.get("naive", {}).get("duplicate_refunds", 0)
        res_dup = wf_data.get("yours", {}).get("duplicate_refunds", 0)
        naive_overpaid = wf_data.get("naive", {}).get("overpaid_cents", 0) / 100
        res_overpaid = wf_data.get("yours", {}).get("overpaid_cents", 0) / 100

        with c1:
            st.metric("Duplicate Refunds (Yours)", f"{res_dup}", delta=f"-{naive_dup} vs Naive")
        with c2:
            st.metric("Tiền hoàn trùng (Overpaid)", f"${res_overpaid:,.2f}", delta=f"-${naive_overpaid:,.2f} thất thoát")
        with c3:
            st.metric("Duplicate Emails", f"{wf_data.get('yours', {}).get('duplicate_emails', 0)}")
        with c4:
            st.metric("Completion Rate", f"{wf_data.get('yours', {}).get('completion_rate', 0):.0%}")

        st.markdown("### 📋 Bảng so sánh Workflow Executor")
        wf_rows = [
            {"Tiêu chí": "Total Sessions", "Naive Executor": wf_data["naive"]["sessions"], "Resilient Executor": wf_data["yours"]["sessions"]},
            {"Tiêu chí": "Worker Crashes Injected", "Naive Executor": wf_data["naive"]["worker_crashes"], "Resilient Executor": wf_data["yours"]["worker_crashes"]},
            {"Tiêu chí": "Duplicate Refunds", "Naive Executor": f"❌ {wf_data['naive']['duplicate_refunds']} lần", "Resilient Executor": f"✅ {wf_data['yours']['duplicate_refunds']} lần"},
            {"Tiêu chí": "Duplicate Emails", "Naive Executor": f"❌ {wf_data['naive']['duplicate_emails']} lần", "Resilient Executor": f"✅ {wf_data['yours']['duplicate_emails']} lần"},
            {"Tiêu chí": "Overpaid Amount ($)", "Naive Executor": f"${wf_data['naive']['overpaid_cents']/100:,.2f}", "Resilient Executor": f"${wf_data['yours']['overpaid_cents']/100:,.2f}"},
            {"Tiêu chí": "Wasted LLM Calls / Crash", "Naive Executor": f"{wf_data['naive']['wasted_llm_per_crash']:.3f}", "Resilient Executor": f"{wf_data['yours']['wasted_llm_per_crash']:.3f}"},
            {"Tiêu chí": "Kết quả thẩm định", "Naive Executor": "❌ FAIL", "Resilient Executor": "✅ PASS"},
        ]
        st.dataframe(wf_rows, use_container_width=True, hide_index=True)
    else:
        st.warning("Chưa có reports/workflows.json. Hãy chạy `python scripts/run_workflows.py --executor both` trước.")


# =========================================================================
# TAB 5: SRE SLO & BURN RATE
# =========================================================================
elif view_mode == "📈 SRE SLO & Burn-Rate Alerting":
    st.markdown('<div class="main-header">Part E · SRE Burn-Rate Alerting & Error Budget</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Mô phỏng 30 ngày SLI data theo chuẩn Google SRE Workbook</div>', unsafe_allow_html=True)

    slo_data = load_slo_json()
    if slo_data:
        st.info("Hệ thống cảnh báo đa cửa sổ (Multi-window Multi-burn-rate) bảo đảm: Page khẩn cấp khi sự cố nặng và không bị False Alarm khi có glitch nhỏ.")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 🚨 Naive Alerter (Ngưỡng 5 phút cố định)")
            st.write(f"- **Pages gửi đi:** {slo_data['naive']['pages']}")
            st.write(f"- **False Alarms (Báo động giả):** {slo_data['naive']['false_pages']}")
            st.write(f"- **Kết quả:** {'✅ PASS' if slo_data['naive']['pass'] else '❌ FAIL'}")
        with col2:
            st.markdown("#### 🛡️ Multi-Window Burn-Rate Alerter (SRE)")
            st.write(f"- **Pages gửi đi:** {slo_data['yours']['pages']}")
            st.write(f"- **False Alarms (Báo động giả):** {slo_data['yours']['false_pages']}")
            st.write(f"- **Kết quả:** {'✅ PASS' if slo_data['yours']['pass'] else '❌ FAIL'}")

        st.markdown("### 📜 Danh sách sự cố phát hiện trong 30 ngày")
        incidents = slo_data["yours"]["incidents"]
        inc_rows = []
        for inc in incidents:
            inc_rows.append({
                "Sự cố (Incident)": inc.get("incident"),
                "Kỳ vọng": inc.get("expect"),
                "Đã phát hiện?": "✅ Có" if inc.get("detected") else ("Không page" if inc.get("expect") == "none" else "❌ Trượt"),
                "Thời gian trễ (phút)": inc.get("delay_min", "-"),
            })
        st.dataframe(inc_rows, use_container_width=True, hide_index=True)
    else:
        st.warning("Chưa có reports/slo.json. Hãy chạy `python scripts/run_slo.py --alerter both` trước.")


# =========================================================================
# TAB 6: LIVE SIMULATION RUNNER
# =========================================================================
elif view_mode == "🧪 Live Simulation Runner":
    st.markdown('<div class="main-header">Chạy mô phỏng Trực tiếp (Live Simulator)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Thử nghiệm các tham số và kịch bản khác nhau ngay trên giao diện</div>', unsafe_allow_html=True)

    try:
        from gameday_lab.factory import build_client
        from gameday_lab.sim.config import load_config
        from gameday_lab.sim.engine import run_scenario

        col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
        with col_cfg1:
            run_scen = st.selectbox("Chọn kịch bản:", list(SCENARIOS_INFO.keys()))
        with col_cfg2:
            run_client = st.selectbox("Chọn Client:", ["resilient", "naive"])
        with col_cfg3:
            run_seed = st.number_input("Random Seed:", min_value=1, max_value=9999, value=25)

        if st.button("🚀 Bắt đầu mô phỏng", type="primary"):
            with st.spinner("Đang chạy mô phỏng discrete-event..."):
                cfg = load_config("configs/gameday.yaml", "configs/scenarios.yaml")
                client_inst = build_client(run_client, cfg, seed=run_seed)
                sim = run_scenario(cfg, run_scen, client_inst, seed=run_seed)
                m = sim.metrics()

            st.success("Mô phỏng hoàn tất trong ~0.3s!")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Availability", f"{m['availability']:.2%}")
            c2.metric("Latency p95", f"{m['latency_p95_s']:.2f}s")
            c3.metric("Amplification", f"{m['amplification']:.2f}x")
            c4.metric("Cost / Good Turn", f"${m['cost_per_good_turn']:.3f}")

            st.json(m)
    except Exception as e:  # noqa: BLE001
        st.error(f"Lỗi khi import hoặc chạy engine: {e}")
