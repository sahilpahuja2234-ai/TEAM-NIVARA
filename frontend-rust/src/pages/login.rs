use crate::api::{post_public, ApiError};
use crate::auth::{login, use_auth};
use crate::components::{error_box::ErrorBox, field::Field};
use crate::models::LoginResponse;
use leptos::*;
use leptos_router::{use_navigate, use_query_map, A};

#[component]
pub fn Login() -> impl IntoView {
    let auth = use_auth();
    let navigate = use_navigate();
    let query = use_query_map();
    let registered = move || {
        query.with(|q| q.get("registered").map(|v| v.as_str() == "1").unwrap_or(false))
    };

    let email = create_rw_signal(String::new());
    let password = create_rw_signal(String::new());
    let error_msg = create_rw_signal(String::new());

    let login_action = create_action(move |_: &()| {
        let e = email.get_untracked().trim().to_string();
        let p = password.get_untracked();
        async move {
            let r: Result<LoginResponse, ApiError> = post_public(
                "/api/store/auth/login",
                &serde_json::json!({ "email": e, "password": p }),
            )
            .await;
            r.map(|resp| (e, resp))
        }
    });

    create_effect(move |_| match login_action.value().get() {
        Some(Ok((form_email, resp))) => {
            login(auth, &resp, &form_email);
            navigate("/", Default::default());
        }
        Some(Err(e)) => error_msg.set(e.message()),
        None => {}
    });

    let can_submit = move || {
        !login_action.pending().get()
            && !email.get().trim().is_empty()
            && !password.get().is_empty()
    };
    let fill = move |e: &'static str, p: &'static str| {
        email.set(e.to_string());
        password.set(p.to_string());
    };

    view! {
        <div class="auth-card">
            <h1>"Log in"</h1>
            {move || {
                registered()
                    .then(|| view! { <div class="success-banner">"Account created, please log in."</div> })
            }}
            <form
                class="checkout-form"
                on:submit=move |ev| {
                    ev.prevent_default();
                    error_msg.set(String::new());
                    login_action.dispatch(());
                }
            >
                <Field label="Email" value=email input_type="email"/>
                <Field label="Password" value=password input_type="password"/>
                <button class="btn" type="submit" disabled=move || !can_submit()>
                    {move || if login_action.pending().get() { "Signing in…" } else { "Log in" }}
                </button>
                {move || {
                    let m = error_msg.get();
                    (!m.is_empty()).then(|| view! { <ErrorBox message=m/> })
                }}
            </form>

            <div class="demo-creds muted small">
                <p>"Demo credentials (click to fill):"</p>
                <p>
                    "Customer: demo@nivara.dev / Demo@1234 "
                    <button
                        type="button"
                        class="link-btn"
                        on:click=move |_| fill("demo@nivara.dev", "Demo@1234")
                    >
                        "fill"
                    </button>
                </p>
                <p>
                    "Admin: demoadmin@nivara.dev / DemoAdmin@1234 "
                    <button
                        type="button"
                        class="link-btn"
                        on:click=move |_| fill("demoadmin@nivara.dev", "DemoAdmin@1234")
                    >
                        "fill"
                    </button>
                </p>
            </div>

            <p class="muted">"No account? " <A href="/register">"Register"</A></p>
        </div>
    }
}
