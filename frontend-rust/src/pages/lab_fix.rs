use crate::api::{get_json, post_json};
use crate::components::{error_box::ApiErrorBox, spinner::Spinner};
use crate::models::FixInfo;
use crate::util::pretty_name;
use leptos::*;
use leptos_router::{use_params_map, A};

#[component]
pub fn LabFix() -> impl IntoView {
    let params = use_params_map();
    let run_id = move || params.with(|p| p.get("run_id").cloned().unwrap_or_default());

    let fix = create_local_resource(run_id, |rid| async move {
        get_json::<FixInfo>(&format!("/api/lab/fix/{rid}")).await
    });

    let apply = create_action(move |_: &()| {
        let rid = run_id();
        async move {
            post_json(
                &format!("/api/lab/fix/{rid}/apply"),
                &serde_json::json!({}),
            )
            .await
        }
    });
    let applied = move || matches!(apply.value().get(), Some(Ok(_)));

    view! {
        <h1>"Apply Fix"</h1>
        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                fix.get()
                    .map(|res| match res {
                        Ok(f) => {
                            let fix_type = (!f.fix_type.is_empty()).then(|| pretty_name(&f.fix_type));
                            view! {
                                <section class="panel reco-box">
                                    <div class="reco-head">
                                        <h2>"Recommendation"</h2>
                                        {fix_type.map(|t| view! { <span class="tag">{t}</span> })}
                                    </div>
                                    <p>{f.recommendation}</p>
                                    <h3>"What the fix does"</h3>
                                    <p class="muted">{f.fix_description}</p>
                                </section>
                            }
                                .into_view()
                        }
                        Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                    })
            }}
        </Suspense>

        {move || {
            if applied() {
                view! {
                    <div class="success-banner">"Fix applied successfully."</div>
                    <A href=format!("/lab/replay/{}", run_id()) class="btn">"▶ Replay Now"</A>
                }
                    .into_view()
            } else {
                view! {
                    <button
                        class="btn"
                        disabled=move || apply.pending().get()
                        on:click=move |_| apply.dispatch(())
                    >
                        {move || if apply.pending().get() { "Applying…" } else { "Apply Fix" }}
                    </button>
                    {move || {
                        apply
                            .value()
                            .get()
                            .and_then(|r| r.err())
                            .map(|e| view! { <ApiErrorBox error=e/> })
                    }}
                }
                    .into_view()
            }
        }}
        <div class="actions">
            <A href=move || format!("/lab/observe/{}", run_id()) class="btn btn-ghost">"← Back to results"</A>
        </div>
    }
}
