use crate::auth::{require_auth, use_auth};
use leptos::*;

/// Renders children only while logged in; redirects to /login otherwise (also after logout).
#[component]
pub fn RequireAuth(children: ChildrenFn) -> impl IntoView {
    let auth = use_auth();
    require_auth();
    let authed = create_memo(move |_| auth.with(|a| a.is_logged_in()));
    move || authed.get().then(|| children())
}
