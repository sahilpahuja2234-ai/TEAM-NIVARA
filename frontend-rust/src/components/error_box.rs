use crate::api::ApiError;
use leptos::*;
use leptos_router::A;

#[component]
pub fn ErrorBox(#[prop(into)] message: String) -> impl IntoView {
    view! { <div class="error-box">{message}</div> }
}

/// Error box for API failures; offers a login link on 401.
#[component]
pub fn ApiErrorBox(error: ApiError) -> impl IntoView {
    let unauthorized = error.is_unauthorized();
    let msg = error.message();
    view! {
        <div class="error-box">
            {msg}
            {unauthorized.then(|| view! { " " <A href="/login">"Log in again"</A> })}
        </div>
    }
}
