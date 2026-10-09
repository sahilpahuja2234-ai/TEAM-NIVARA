use leptos::*;

/// Animated progress bar (determinate if the server reports `progress`) + step messages.
#[component]
pub fn ProgressPanel(
    progress: RwSignal<Option<f64>>,
    current: RwSignal<String>,
    steps: RwSignal<Vec<String>>,
) -> impl IntoView {
    view! {
        <div class="panel run-panel">
            {move || match progress.get() {
                Some(p) => {
                    view! {
                        <div class="progress">
                            <div class="progress-fill" style=format!("width:{:.0}%", p.clamp(0.0, 100.0))></div>
                        </div>
                    }
                        .into_view()
                }
                None => {
                    view! {
                        <div class="progress">
                            <div class="progress-fill indeterminate"></div>
                        </div>
                    }
                        .into_view()
                }
            }}
            <p class="muted">{move || current.get()}</p>
            <ul class="step-list">
                {move || {
                    steps.get().into_iter().map(|l| view! { <li>"▸ " {l}</li> }).collect_view()
                }}
            </ul>
        </div>
    }
}
