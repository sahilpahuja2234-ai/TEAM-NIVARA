use crate::api::{get_text, ApiError};
use crate::components::{
    attack_path::AttackPath, badge::Badge, controls_matrix::ControlMatrix,
    error_box::ApiErrorBox, score_ring::ScoreRing, spinner::Spinner,
};
use crate::models::Report;
use crate::util::save_text_file;
use leptos::*;
use leptos_router::{use_params_map, A};

#[derive(Clone)]
enum ReportView {
    Json(Report),
    Html(String),
}

#[component]
pub fn LabReport() -> impl IntoView {
    let params = use_params_map();
    let run_id = move || params.with(|p| p.get("run_id").cloned().unwrap_or_default());

    // GET /api/reports/generate/:run_id — JSON preferred; raw HTML is shown in a frame.
    let report = create_local_resource(run_id, |rid| async move {
        let text = get_text(&format!("/api/reports/generate/{rid}")).await?;
        Ok::<ReportView, ApiError>(match serde_json::from_str::<Report>(&text) {
            Ok(r) => ReportView::Json(r),
            Err(_) => ReportView::Html(text),
        })
    });

    let download = create_action(move |report_id: &String| {
        let report_id = report_id.clone();
        let rid = run_id();
        async move {
            let html = get_text(&format!("/api/reports/download/{report_id}")).await?;
            save_text_file(&format!("nivara-report-{rid}.html"), &html)
                .map_err(|_| ApiError::Failed("Could not save the file".into()))
        }
    });

    let download_button = move |report_id: String| {
        view! {
            <button
                class="btn"
                disabled=move || download.pending().get()
                on:click=move |_| download.dispatch(report_id.clone())
            >
                "⬇ Download HTML Report"
            </button>
            {move || {
                download
                    .value()
                    .get()
                    .and_then(|r| r.err())
                    .map(|e| view! { <ApiErrorBox error=e/> })
            }}
        }
    };

    view! {
        <h1>"Security Report"</h1>
        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                report
                    .get()
                    .map(|res| match res {
                        Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                        Ok(ReportView::Html(html)) => {
                            view! {
                                <iframe class="report-frame" sandbox="" srcdoc=html></iframe>
                                <div class="actions">{download_button(run_id())}</div>
                            }
                                .into_view()
                        }
                        Ok(ReportView::Json(r)) => {
                            if let Some(html) = r.html.clone() {
                                return view! {
                                    <iframe class="report-frame" sandbox="" srcdoc=html></iframe>
                                    <div class="actions">{download_button(r.rid().unwrap_or_else(run_id))}</div>
                                }
                                    .into_view();
                            }
                            let rid = r.rid().unwrap_or_else(run_id);
                            let summary = r.summary_text();
                            let before = r.before_score.map(|s| s.round() as i32);
                            let after = r.after_score.map(|s| s.round() as i32);
                            view! {
                                <div class="obs-meta">
                                    <h2>{r.scenario_name.clone().unwrap_or_default()}</h2>
                                    {r.severity.clone().map(|s| view! { <Badge severity=s/> })}
                                    {r
                                        .affected_component
                                        .clone()
                                        .map(|c| view! { <span class="tag">{c}</span> })}
                                    {r
                                        .generated_at
                                        .clone()
                                        .map(|g| view! { <span class="muted small">{format!("Generated {g}")}</span> })}
                                </div>

                                <section class="panel">
                                    <h2>"Executive Summary"</h2>
                                    <p>{summary.unwrap_or_else(|| "No summary provided.".to_string())}</p>
                                </section>

                                <section class="panel">
                                    <h2>"Security Score"</h2>
                                    <div class="score-pair">
                                        {before.map(|b| view! { <ScoreRing score=b label="before"/> })}
                                        {after.map(|a| view! { <ScoreRing score=a label="after"/> })}
                                    </div>
                                </section>

                                <div class="obs-grid">
                                    <section class="panel">
                                        <h2>"Attack Path"</h2>
                                        <AttackPath nodes=r.attack_path.clone() detected_at=r.detected_at.clone()/>
                                    </section>
                                    <section class="panel">
                                        <h2>"Controls Matrix"</h2>
                                        <ControlMatrix controls=r.controls.clone()/>
                                    </section>
                                </div>
                                <div class="actions">{download_button(rid)}</div>
                            }
                                .into_view()
                        }
                    })
            }}
        </Suspense>
        <div class="actions">
            <A href="/lab" class="btn btn-ghost">"← Back to Lab"</A>
        </div>
    }
}
