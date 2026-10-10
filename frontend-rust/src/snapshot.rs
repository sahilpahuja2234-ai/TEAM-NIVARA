//! Remembers the controls as first observed for a run (before the fix), so the
//! Replay page can show the BEFORE card even if the scores API doesn't return them.
use crate::api::storage;
use crate::models::ControlStatus;

fn key(run_id: &str) -> String {
    format!("nivara_before_{run_id}")
}

pub fn save_before(run_id: &str, controls: &[(String, ControlStatus)]) {
    if controls.is_empty() {
        return;
    }
    if let Some(s) = storage() {
        let k = key(run_id);
        if s.get_item(&k).ok().flatten().is_none() {
            if let Ok(json) = serde_json::to_string(controls) {
                let _ = s.set_item(&k, &json);
            }
        }
    }
}

pub fn load_before(run_id: &str) -> Option<Vec<(String, ControlStatus)>> {
    let raw = storage()?.get_item(&key(run_id)).ok().flatten()?;
    serde_json::from_str(&raw).ok()
}
