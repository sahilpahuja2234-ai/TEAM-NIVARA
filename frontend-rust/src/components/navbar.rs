use crate::auth::{logout, use_auth};
use leptos::*;
use leptos_router::{use_navigate, A};

#[component]
pub fn Navbar() -> impl IntoView {
    let auth = use_auth();
    let navigate = use_navigate();
    let logged_in = move || auth.with(|a| a.is_logged_in());
    let is_admin = move || auth.with(|a| a.is_admin());
    let email = move || auth.with(|a| a.user_email.clone().unwrap_or_default());

    view! {
        <nav class="navbar">
            <A href="/" class="brand">"NIVARA"</A>
            <div class="nav-group">
                <span class="nav-label">"Store"</span>
                <A href="/catalog">"Catalog"</A>
                <A href="/cart">"Cart"</A>
                <A href="/orders">"Orders"</A>
            </div>
            <div class="nav-group">
                <span class="nav-label">"Lab"</span>
                <A href="/lab" exact=true>"Dashboard"</A>
                <A href="/lab/scenarios">"Scenarios"</A>
            </div>
            <div class="nav-spacer"></div>
            {move || is_admin().then(|| view! { <A href="/admin">"Admin"</A> })}
            {move || {
                if logged_in() {
                    let navigate = navigate.clone();
                    view! {
                        <span class="nav-user">{email()}</span>
                        <button
                            class="link-btn nav-logout"
                            on:click=move |_| {
                                logout(auth);
                                navigate("/", Default::default());
                            }
                        >
                            "Logout"
                        </button>
                    }
                        .into_view()
                } else {
                    view! {
                        <A href="/login">"Login"</A>
                        <A href="/register">"Register"</A>
                    }
                        .into_view()
                }
            }}
        </nav>
    }
}
