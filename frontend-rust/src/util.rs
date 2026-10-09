/// Format a server-provided amount for display. (Formatting only — never arithmetic.)
pub fn money(v: f64) -> String {
    format!("${v:.2}")
}

/// "2026-10-08T12:34:56" -> "2026-10-08"
pub fn short_date(s: &str) -> String {
    s.chars().take(10).collect()
}

/// "2026-10-08T12:34:56Z" -> "2026-10-08 12:34"
pub fn short_datetime(s: &str) -> String {
    s.replace('T', " ").chars().take(16).collect()
}

/// Display color for a 0–100 value: red <40, yellow 40–70, green >70.
pub fn score_color(v: f64) -> &'static str {
    if v > 70.0 {
        "var(--c2)"
    } else if v >= 40.0 {
        "var(--warn)"
    } else {
        "var(--danger)"
    }
}

/// "pricing_logic" -> "Pricing logic"
pub fn pretty_name(s: &str) -> String {
    let t = s.replace(['_', '-'], " ");
    let mut c = t.chars();
    match c.next() {
        Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
        None => String::new(),
    }
}

/// Trigger a browser download of `content` as `filename`.
pub fn save_text_file(filename: &str, content: &str) -> Result<(), wasm_bindgen::JsValue> {
    use wasm_bindgen::{JsCast, JsValue};
    let parts = js_sys::Array::of1(&JsValue::from_str(content));
    let blob = web_sys::Blob::new_with_str_sequence(&parts)?;
    let url = web_sys::Url::create_object_url_with_blob(&blob)?;
    let doc = web_sys::window()
        .and_then(|w| w.document())
        .ok_or(JsValue::NULL)?;
    let a = doc
        .create_element("a")?
        .dyn_into::<web_sys::HtmlAnchorElement>()
        .map_err(|_| JsValue::NULL)?;
    a.set_href(&url);
    a.set_download(filename);
    a.click();
    web_sys::Url::revoke_object_url(&url)?;
    Ok(())
}
