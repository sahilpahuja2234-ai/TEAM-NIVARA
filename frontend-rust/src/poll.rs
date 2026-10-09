use crate::api::{get_json, ApiError};
use crate::models::RunStatus;
use gloo_timers::future::TimeoutFuture;
use std::{cell::Cell, rc::Rc};

const INTERVAL_MS: u32 = 1500;

/// Poll GET /api/lab/status/:run_id every 1.5s until completed.
/// Stops (with Err) when `alive` is cleared (page left), the run fails, or 3 requests fail in a row.
/// `delay_first`: wait one interval before the first poll (used for replay so the
/// server can switch the run back to "running" first).
pub async fn poll_run(
    run_id: &str,
    alive: &Rc<Cell<bool>>,
    on_update: impl Fn(&RunStatus),
    delay_first: bool,
) -> Result<RunStatus, ApiError> {
    let mut errors = 0u8;
    if delay_first {
        TimeoutFuture::new(INTERVAL_MS).await;
    }
    loop {
        if !alive.get() {
            return Err(ApiError::Network("cancelled".into()));
        }
        match get_json::<RunStatus>(&format!("/api/lab/status/{run_id}")).await {
            Ok(st) => {
                errors = 0;
                on_update(&st);
                if st.is_completed() {
                    return Ok(st);
                }
                if st.is_failed() {
                    return Err(ApiError::Failed(
                        st.message.clone().unwrap_or_else(|| "Run failed".into()),
                    ));
                }
            }
            Err(e) => {
                errors += 1;
                if errors >= 3 {
                    return Err(e);
                }
            }
        }
        TimeoutFuture::new(INTERVAL_MS).await;
    }
}
