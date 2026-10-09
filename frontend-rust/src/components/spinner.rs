use leptos::*;

#[component]
pub fn Spinner() -> impl IntoView {
    view! { <div class="spinner" role="status" aria-label="Loading"></div> }
}
