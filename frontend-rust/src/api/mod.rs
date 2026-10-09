use gloo_net::http::Request;
use serde::de::DeserializeOwned;
use serde::Serialize;
use std::fmt;

pub const TOKEN_KEY: &str = "nivara_token";

#[derive(Debug, Clone)]
pub enum ApiError {
    Network(String),
    Http(u16, String),
    Parse(String),
    Failed(String),
}

impl fmt::Display for ApiError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ApiError::Network(e) => write!(f, "Network error: {e}"),
            ApiError::Http(code, body) => write!(f, "HTTP {code}: {body}"),
            ApiError::Parse(e) => write!(f, "Bad response: {e}"),
            ApiError::Failed(m) => write!(f, "{m}"),
        }
    }
}

pub fn storage() -> Option<web_sys::Storage> {
    web_sys::window()?.local_storage().ok().flatten()
}

pub fn get_token() -> Option<String> {
    storage()?.get_item(TOKEN_KEY).ok().flatten()
}

pub fn set_token(token: &str) {
    if let Some(s) = storage() {
        let _ = s.set_item(TOKEN_KEY, token);
    }
}

pub fn clear_token() {
    if let Some(s) = storage() {
        let _ = s.remove_item(TOKEN_KEY);
    }
}

/// GET `path` (e.g. "/api/store/books") and deserialize the JSON body.
pub async fn fetch_json<T: DeserializeOwned>(
    path: &str,
    token: Option<&str>,
) -> Result<T, ApiError> {
    let mut req = Request::get(path);
    if let Some(t) = token {
        req = req.header("Authorization", &format!("Bearer {t}"));
    }
    let resp = req
        .send()
        .await
        .map_err(|e| ApiError::Network(e.to_string()))?;
    if !resp.ok() {
        let body = resp.text().await.unwrap_or_default();
        return Err(ApiError::Http(resp.status(), body));
    }
    resp.json::<T>()
        .await
        .map_err(|e| ApiError::Parse(e.to_string()))
}

/// GET using the stored `nivara_token` (if any).
pub async fn get_json<T: DeserializeOwned>(path: &str) -> Result<T, ApiError> {
    let token = get_token();
    fetch_json(path, token.as_deref()).await
}

/// POST a JSON body using the stored token. Response body is ignored; only success/failure matters.
pub async fn post_json<B: Serialize>(path: &str, body: &B) -> Result<(), ApiError> {
    let mut req = Request::post(path);
    if let Some(t) = get_token() {
        req = req.header("Authorization", &format!("Bearer {t}"));
    }
    let req = req
        .json(body)
        .map_err(|e| ApiError::Parse(e.to_string()))?;
    let resp = req
        .send()
        .await
        .map_err(|e| ApiError::Network(e.to_string()))?;
    if !resp.ok() {
        let body = resp.text().await.unwrap_or_default();
        return Err(ApiError::Http(resp.status(), body));
    }
    Ok(())
}

/// Percent-encode a query-string value.
pub fn encode(s: &str) -> String {
    String::from(js_sys::encode_uri_component(s))
}

impl ApiError {
    pub fn is_unauthorized(&self) -> bool {
        matches!(self, ApiError::Http(401, _))
    }

    /// Human-friendly message: uses FastAPI's {"detail": "..."} when present.
    pub fn message(&self) -> String {
        if let ApiError::Http(_, body) = self {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(body) {
                if let Some(s) = v
                    .get("detail")
                    .or_else(|| v.get("message"))
                    .and_then(|d| d.as_str())
                {
                    return s.to_string();
                }
            }
        }
        self.to_string()
    }
}

fn with_auth(mut req: gloo_net::http::RequestBuilder) -> gloo_net::http::RequestBuilder {
    if let Some(t) = get_token() {
        req = req.header("Authorization", &format!("Bearer {t}"));
    }
    req
}

async fn check(resp: gloo_net::http::Response) -> Result<(), ApiError> {
    if !resp.ok() {
        let body = resp.text().await.unwrap_or_default();
        return Err(ApiError::Http(resp.status(), body));
    }
    Ok(())
}

/// PUT a JSON body using the stored token.
pub async fn put_json<B: Serialize>(path: &str, body: &B) -> Result<(), ApiError> {
    let req = with_auth(Request::put(path))
        .json(body)
        .map_err(|e| ApiError::Parse(e.to_string()))?;
    let resp = req
        .send()
        .await
        .map_err(|e| ApiError::Network(e.to_string()))?;
    check(resp).await
}

/// DELETE using the stored token.
pub async fn delete_req(path: &str) -> Result<(), ApiError> {
    let resp = with_auth(Request::delete(path))
        .send()
        .await
        .map_err(|e| ApiError::Network(e.to_string()))?;
    check(resp).await
}

/// POST without the Authorization header (login / register); returns the checked response.
async fn public_post<B: Serialize>(
    path: &str,
    body: &B,
) -> Result<gloo_net::http::Response, ApiError> {
    let req = Request::post(path)
        .json(body)
        .map_err(|e| ApiError::Parse(e.to_string()))?;
    let resp = req
        .send()
        .await
        .map_err(|e| ApiError::Network(e.to_string()))?;
    if !resp.ok() {
        let body = resp.text().await.unwrap_or_default();
        return Err(ApiError::Http(resp.status(), body));
    }
    Ok(resp)
}

/// Unauthenticated POST that returns the JSON body.
pub async fn post_public<B: Serialize, T: DeserializeOwned>(
    path: &str,
    body: &B,
) -> Result<T, ApiError> {
    public_post(path, body)
        .await?
        .json::<T>()
        .await
        .map_err(|e| ApiError::Parse(e.to_string()))
}

/// Unauthenticated POST; the response body is ignored.
pub async fn post_public_ok<B: Serialize>(path: &str, body: &B) -> Result<(), ApiError> {
    public_post(path, body).await.map(|_| ())
}

/// POST a JSON body using the stored token and parse the JSON response.
pub async fn post_json_as<B: Serialize, T: DeserializeOwned>(
    path: &str,
    body: &B,
) -> Result<T, ApiError> {
    let req = with_auth(Request::post(path))
        .json(body)
        .map_err(|e| ApiError::Parse(e.to_string()))?;
    let resp = req
        .send()
        .await
        .map_err(|e| ApiError::Network(e.to_string()))?;
    if !resp.ok() {
        let body = resp.text().await.unwrap_or_default();
        return Err(ApiError::Http(resp.status(), body));
    }
    resp.json::<T>()
        .await
        .map_err(|e| ApiError::Parse(e.to_string()))
}

/// GET returning the raw body text (HTML reports, etc.), using the stored token.
pub async fn get_text(path: &str) -> Result<String, ApiError> {
    let resp = with_auth(Request::get(path))
        .send()
        .await
        .map_err(|e| ApiError::Network(e.to_string()))?;
    if !resp.ok() {
        let body = resp.text().await.unwrap_or_default();
        return Err(ApiError::Http(resp.status(), body));
    }
    resp.text()
        .await
        .map_err(|e| ApiError::Parse(e.to_string()))
}
