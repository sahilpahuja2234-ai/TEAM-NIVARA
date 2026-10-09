use crate::api::{self, storage};
use crate::models::LoginResponse;
use leptos::*;
use leptos_router::use_navigate;
use serde_json::Value;

pub const USER_KEY: &str = "nivara_user";

#[derive(Clone, Debug, Default, PartialEq)]
pub struct AuthState {
    pub token: Option<String>,
    pub user_email: Option<String>,
    pub role: Option<String>,
}

impl AuthState {
    pub fn is_logged_in(&self) -> bool {
        self.token.is_some()
    }
    pub fn is_admin(&self) -> bool {
        self.role
            .as_deref()
            .map(|r| r.eq_ignore_ascii_case("admin"))
            .unwrap_or(false)
    }
}

// ---- JWT helpers (display/UX only — the server is the authority) ----

fn jwt_claims(token: &str) -> Option<Value> {
    let payload = token.split('.').nth(1)?;
    let mut b64 = payload.replace('-', "+").replace('_', "/");
    while b64.len() % 4 != 0 {
        b64.push('=');
    }
    let json = web_sys::window()?.atob(&b64).ok()?;
    serde_json::from_str(&json).ok()
}

fn claim_str(v: &Value, key: &str) -> Option<String> {
    v.get(key).and_then(|x| x.as_str()).map(String::from)
}

fn is_expired(claims: &Value) -> bool {
    claims
        .get("exp")
        .and_then(|e| e.as_f64())
        .map(|exp| exp < js_sys::Date::now() / 1000.0)
        .unwrap_or(false)
}

fn clear_storage() {
    api::clear_token();
    if let Some(s) = storage() {
        let _ = s.remove_item(USER_KEY);
    }
}

/// Read localStorage and build the initial state (runs once at App mount).
fn load_auth() -> AuthState {
    let Some(token) = api::get_token() else {
        return AuthState::default();
    };
    let claims = jwt_claims(&token);
    if claims.as_ref().map(is_expired).unwrap_or(false) {
        clear_storage();
        return AuthState::default();
    }
    let stored: Option<Value> = storage()
        .and_then(|s| s.get_item(USER_KEY).ok().flatten())
        .and_then(|j| serde_json::from_str(&j).ok());

    let email = stored
        .as_ref()
        .and_then(|v| claim_str(v, "email"))
        .or_else(|| claims.as_ref().and_then(|c| claim_str(c, "email")))
        .or_else(|| {
            claims
                .as_ref()
                .and_then(|c| claim_str(c, "sub"))
                .filter(|s| s.contains('@'))
        });
    let role = stored
        .as_ref()
        .and_then(|v| claim_str(v, "role"))
        .or_else(|| claims.as_ref().and_then(|c| claim_str(c, "role")));

    AuthState {
        token: Some(token),
        user_email: email,
        role,
    }
}

// ---- Context ----

/// Call once from the App root.
pub fn provide_auth() -> RwSignal<AuthState> {
    let state = create_rw_signal(load_auth());
    provide_context(state);
    state
}

pub fn use_auth() -> RwSignal<AuthState> {
    expect_context::<RwSignal<AuthState>>()
}

/// Current token from the auth context (reactive when called inside a tracking scope).
pub fn auth_token() -> Option<String> {
    use_auth().with(|a| a.token.clone())
}

/// Persist the token + user info and update the context.
pub fn login(auth: RwSignal<AuthState>, resp: &LoginResponse, form_email: &str) {
    let claims = jwt_claims(&resp.access_token);
    let email = resp
        .user
        .as_ref()
        .and_then(|u| u.email.clone())
        .or_else(|| resp.email.clone())
        .or_else(|| claims.as_ref().and_then(|c| claim_str(c, "email")))
        .or_else(|| Some(form_email.to_string()));
    let role = resp
        .user
        .as_ref()
        .and_then(|u| u.role.clone())
        .or_else(|| resp.role.clone())
        .or_else(|| claims.as_ref().and_then(|c| claim_str(c, "role")));

    api::set_token(&resp.access_token);
    if let Some(s) = storage() {
        let user = serde_json::json!({ "email": email, "role": role });
        let _ = s.set_item(USER_KEY, &user.to_string());
    }
    auth.set(AuthState {
        token: Some(resp.access_token.clone()),
        user_email: email,
        role,
    });
}

/// Clear localStorage and the context.
pub fn logout(auth: RwSignal<AuthState>) {
    clear_storage();
    auth.set(AuthState::default());
}

/// Call in a component body: redirects to /login whenever there is no token.
pub fn require_auth() {
    let auth = use_auth();
    let navigate = use_navigate();
    create_effect(move |_| {
        if !auth.with(|a| a.is_logged_in()) {
            navigate("/login", Default::default());
        }
    });
}
