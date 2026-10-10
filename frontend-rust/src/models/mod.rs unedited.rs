use serde::{Deserialize, Serialize};
use serde_json::Value;

// ---------- Bookstore ----------

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Author {
    pub id: i64,
    pub name: String,
    #[serde(default)]
    pub bio: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(from = "CategoryRepr")]
pub struct Category {
    pub id: i64,
    pub name: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Book {
    pub id: i64,
    pub title: String,
    #[serde(default)]
    pub author: Option<String>,
    #[serde(default)]
    pub category: Option<String>,
    pub price: f64,
    #[serde(default)]
    pub stock: i32,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub cover_url: Option<String>,
    #[serde(default)]
    pub rating: Option<f64>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CartItem {
    /// cart item id (used for PUT/DELETE /api/store/cart/:item_id)
    #[serde(default, alias = "item_id")]
    pub id: i64,
    #[serde(default)]
    pub book_id: i64,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub price: f64,
    #[serde(default = "one")]
    pub quantity: i32,
    /// Server-provided line total, if any (never computed client-side).
    #[serde(default, alias = "item_total")]
    pub line_total: Option<f64>,
}

fn one() -> i32 {
    1
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OrderItem {
    #[serde(default)]
    pub book_id: i64,
    #[serde(default)]
    pub title: String,
    pub quantity: i32,
    #[serde(default)]
    pub price: f64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Order {
    #[serde(deserialize_with = "de_id_string")]
    pub id: String,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub total: Option<f64>,
    #[serde(default)]
    pub final_total: Option<f64>,
    #[serde(default)]
    pub created_at: Option<String>,
    #[serde(default, alias = "order_items")]
    pub items: Vec<OrderItem>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Review {
    #[serde(default)]
    pub id: i64,
    #[serde(default)]
    pub book_id: i64,
    #[serde(default, alias = "reviewer", alias = "reviewer_name", alias = "username")]
    pub user: Option<String>,
    pub rating: i32,
    #[serde(default, alias = "body")]
    pub comment: Option<String>,
    #[serde(default)]
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Coupon {
    pub code: String,
    #[serde(default)]
    pub discount_percent: f64,
    #[serde(default)]
    pub active: bool,
}

// ---------- Security Lab ----------

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ControlStatus {
    Detected,
    Missed,
    Partial,
}

/// Shared result schema (read-only; produced by the backend).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ScenarioRun {
    #[serde(default)]
    pub scenario_id: String,
    #[serde(default)]
    pub scenario_name: String,
    #[serde(default, deserialize_with = "de_id_string")]
    pub run_id: String,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub severity: String,
    #[serde(default)]
    pub affected_component: String,
    #[serde(default)]
    pub attack_path: Vec<String>,
    /// Ordered as sent by the backend: (control name, result)
    #[serde(default, deserialize_with = "de_controls")]
    pub controls: Vec<(String, ControlStatus)>,
    #[serde(default)]
    pub before_score: f64,
    #[serde(default)]
    pub after_score: f64,
    /// Optional: the attack-path node where detection occurred.
    #[serde(default, alias = "detection_point", alias = "detected_node")]
    pub detected_at: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Finding {
    #[serde(default)]
    pub id: Option<String>,
    #[serde(default)]
    pub run_id: String,
    pub title: String,
    #[serde(default)]
    pub severity: String,
    #[serde(default)]
    pub component: String,
    #[serde(default)]
    pub description: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ScoreSnapshot {
    #[serde(default)]
    pub run_id: String,
    /// "before" | "after"
    #[serde(default)]
    pub phase: String,
    pub score: i32,
    #[serde(default)]
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LabStatus {
    #[serde(default)]
    pub twin_running: bool,
    #[serde(default)]
    pub db_seeded: bool,
    #[serde(default)]
    pub last_reset: Option<String>,
    #[serde(default)]
    pub current_score: Option<f64>,
    #[serde(default)]
    pub scenario_count: Option<i64>,
    /// Percentage 0–100
    #[serde(default)]
    pub detection_rate: Option<f64>,
}

// ---------- Tolerant response wrappers ----------

/// Categories may come back as ["Fiction", ...] or [{"id":1,"name":"Fiction"}, ...].
#[derive(Deserialize)]
#[serde(untagged)]
enum CategoryRepr {
    Name(String),
    Full {
        #[serde(default)]
        id: i64,
        name: String,
    },
}

impl From<CategoryRepr> for Category {
    fn from(r: CategoryRepr) -> Self {
        match r {
            CategoryRepr::Name(name) => Category { id: 0, name },
            CategoryRepr::Full { id, name } => Category { id, name },
        }
    }
}

/// /api/store/catalog may return a bare array or a paged object.
#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum CatalogResponse {
    List(Vec<Book>),
    Paged {
        #[serde(alias = "books", alias = "results", alias = "data")]
        items: Vec<Book>,
        #[serde(default)]
        total: Option<i64>,
    },
}

impl CatalogResponse {
    pub fn total(&self) -> Option<i64> {
        match self {
            CatalogResponse::List(_) => None,
            CatalogResponse::Paged { total, .. } => *total,
        }
    }
    pub fn books(self) -> Vec<Book> {
        match self {
            CatalogResponse::List(v) => v,
            CatalogResponse::Paged { items, .. } => items,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum ReviewList {
    List(Vec<Review>),
    Wrapped {
        #[serde(alias = "items", alias = "results")]
        reviews: Vec<Review>,
    },
}

impl ReviewList {
    pub fn into_vec(self) -> Vec<Review> {
        match self {
            ReviewList::List(v) => v,
            ReviewList::Wrapped { reviews } => reviews,
        }
    }
}

fn de_id_string<'de, D: serde::Deserializer<'de>>(d: D) -> Result<String, D::Error> {
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum Id {
        S(String),
        N(i64),
    }
    Ok(match Id::deserialize(d)? {
        Id::S(s) => s,
        Id::N(n) => n.to_string(),
    })
}

/// Server-computed cart. All money fields come from the backend; the client never calculates.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Cart {
    #[serde(default, alias = "cart_items")]
    pub items: Vec<CartItem>,
    #[serde(default)]
    pub subtotal: Option<f64>,
    #[serde(default, alias = "discount_amount")]
    pub discount: Option<f64>,
    #[serde(default)]
    pub coupon_code: Option<String>,
    #[serde(default)]
    pub total: Option<f64>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum CartResponse {
    List(Vec<CartItem>),
    Full(Cart),
}

impl CartResponse {
    pub fn into_cart(self) -> Cart {
        match self {
            CartResponse::List(items) => Cart {
                items,
                ..Default::default()
            },
            CartResponse::Full(c) => c,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum OrderList {
    List(Vec<Order>),
    Wrapped {
        #[serde(alias = "items", alias = "results")]
        orders: Vec<Order>,
    },
}

impl OrderList {
    pub fn into_vec(self) -> Vec<Order> {
        match self {
            OrderList::List(v) => v,
            OrderList::Wrapped { orders } => orders,
        }
    }
}

// ---------- Auth ----------

#[derive(Debug, Clone, Default, Deserialize)]
pub struct UserInfo {
    #[serde(default)]
    pub email: Option<String>,
    #[serde(default)]
    pub role: Option<String>,
    #[serde(default)]
    pub full_name: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LoginResponse {
    pub access_token: String,
    #[serde(default)]
    pub user: Option<UserInfo>,
    #[serde(default)]
    pub email: Option<String>,
    #[serde(default)]
    pub role: Option<String>,
}

// ---------- Lab scenario library ----------

/// Item from GET /api/lab/scenarios (with last_run / last_result).
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Scenario {
    #[serde(default)]
    pub id: Option<String>,
    #[serde(default)]
    pub scenario_id: Option<String>,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub scenario_name: Option<String>,
    #[serde(default)]
    pub layer: String,
    #[serde(default)]
    pub severity: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub affected_component: Option<String>,
    #[serde(default)]
    pub last_run: Option<String>,
    /// String ("detected") or object ({"status": "..."}).
    #[serde(default)]
    pub last_result: Option<Value>,
}

impl Scenario {
    pub fn sid(&self) -> String {
        self.id
            .clone()
            .or_else(|| self.scenario_id.clone())
            .unwrap_or_default()
    }

    pub fn display_name(&self) -> String {
        if !self.name.is_empty() {
            self.name.clone()
        } else {
            self.scenario_name.clone().unwrap_or_default()
        }
    }

    pub fn last_result_label(&self) -> Option<String> {
        match self.last_result.as_ref()? {
            Value::String(s) if !s.is_empty() => Some(s.clone()),
            Value::Object(m) => ["status", "result", "outcome"]
                .iter()
                .find_map(|k| m.get(*k).and_then(|v| v.as_str()).map(String::from)),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum ScenarioList {
    List(Vec<Scenario>),
    Wrapped {
        #[serde(alias = "items", alias = "results")]
        scenarios: Vec<Scenario>,
    },
}

impl ScenarioList {
    pub fn into_vec(self) -> Vec<Scenario> {
        match self {
            ScenarioList::List(v) => v,
            ScenarioList::Wrapped { scenarios } => scenarios,
        }
    }
}

// ---------- Simulation flow ----------

fn control_from_value(v: &Value) -> ControlStatus {
    match v {
        Value::Bool(true) => ControlStatus::Detected,
        Value::Bool(false) => ControlStatus::Missed,
        Value::String(s) => {
            let l = s.to_lowercase();
            if l.contains("partial") {
                ControlStatus::Partial
            } else if l == "pass" || l == "passed" || l == "ok" || (l.contains("detect") && !l.contains("undetect")) {
                ControlStatus::Detected
            } else {
                ControlStatus::Missed
            }
        }
        _ => ControlStatus::Missed,
    }
}

/// Controls arrive as {"name": "detected", ...} (order preserved) or [{"name":..,"status":..}].
fn de_controls<'de, D: serde::Deserializer<'de>>(
    d: D,
) -> Result<Vec<(String, ControlStatus)>, D::Error> {
    Ok(match Value::deserialize(d)? {
        Value::Object(m) => m
            .into_iter()
            .map(|(k, v)| (k, control_from_value(&v)))
            .collect(),
        Value::Array(a) => a
            .iter()
            .filter_map(|item| {
                let name = ["name", "control", "id"]
                    .iter()
                    .find_map(|k| item.get(*k).and_then(|v| v.as_str()))?;
                let st = ["status", "result", "state"]
                    .iter()
                    .find_map(|k| item.get(*k))
                    .map(control_from_value)
                    .unwrap_or(ControlStatus::Missed);
                Some((name.to_string(), st))
            })
            .collect(),
        _ => Vec::new(),
    })
}

#[derive(Debug, Clone, Deserialize)]
pub struct RunStarted {
    #[serde(deserialize_with = "de_id_string")]
    pub run_id: String,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct RunStatus {
    #[serde(default)]
    pub status: String,
    /// Percentage 0–100, if the backend reports it.
    #[serde(default)]
    pub progress: Option<f64>,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default, alias = "messages", alias = "logs")]
    pub steps: Vec<Value>,
    #[serde(default)]
    pub result: Option<Value>,
}

fn value_lines(items: &[Value]) -> Vec<String> {
    items
        .iter()
        .filter_map(|x| match x {
            Value::String(s) => Some(s.clone()),
            Value::Object(m) => ["message", "step", "text", "name"]
                .iter()
                .find_map(|k| m.get(*k).and_then(|v| v.as_str()).map(String::from)),
            _ => None,
        })
        .collect()
}

impl RunStatus {
    pub fn is_completed(&self) -> bool {
        matches!(
            self.status.to_lowercase().as_str(),
            "completed" | "complete" | "done" | "finished" | "success"
        )
    }
    pub fn is_failed(&self) -> bool {
        matches!(self.status.to_lowercase().as_str(), "failed" | "error")
    }
    pub fn step_lines(&self) -> Vec<String> {
        if !self.steps.is_empty() {
            return value_lines(&self.steps);
        }
        self.result
            .as_ref()
            .and_then(|r| r.get("steps").or_else(|| r.get("messages")))
            .and_then(|v| v.as_array())
            .map(|a| value_lines(a))
            .unwrap_or_default()
    }
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct FixInfo {
    #[serde(default)]
    pub recommendation: String,
    #[serde(default)]
    pub fix_description: String,
    #[serde(default)]
    pub fix_type: String,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct ScoreInfo {
    #[serde(default)]
    pub before_score: f64,
    #[serde(default)]
    pub after_score: f64,
    #[serde(default)]
    pub delta: Option<f64>,
    #[serde(default, deserialize_with = "de_controls")]
    pub before_controls: Vec<(String, ControlStatus)>,
    #[serde(default, deserialize_with = "de_controls")]
    pub after_controls: Vec<(String, ControlStatus)>,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct Report {
    #[serde(default)]
    pub report_id: Option<Value>,
    #[serde(default)]
    pub id: Option<Value>,
    #[serde(default)]
    pub scenario_name: Option<String>,
    #[serde(default)]
    pub severity: Option<String>,
    #[serde(default)]
    pub affected_component: Option<String>,
    #[serde(default)]
    pub executive_summary: Option<String>,
    #[serde(default)]
    pub summary: Option<String>,
    #[serde(default)]
    pub before_score: Option<f64>,
    #[serde(default)]
    pub after_score: Option<f64>,
    #[serde(default)]
    pub generated_at: Option<String>,
    #[serde(default)]
    pub attack_path: Vec<String>,
    #[serde(default, deserialize_with = "de_controls")]
    pub controls: Vec<(String, ControlStatus)>,
    #[serde(default)]
    pub detected_at: Option<String>,
    /// Some backends return the rendered report as an HTML string inside JSON.
    #[serde(default)]
    pub html: Option<String>,
}

impl Report {
    pub fn rid(&self) -> Option<String> {
        self.report_id
            .as_ref()
            .or(self.id.as_ref())
            .map(|v| match v {
                Value::String(s) => s.clone(),
                other => other.to_string(),
            })
    }
    pub fn summary_text(&self) -> Option<String> {
        self.executive_summary.clone().or_else(|| self.summary.clone())
    }
}
