use crate::auth::provide_auth;
use crate::components::navbar::Navbar;
use crate::components::require_auth::RequireAuth;
use crate::pages::{
    book_detail::BookDetail, cart::Cart, catalog::Catalog, checkout::Checkout, home::Home,
    lab_dashboard::LabDashboard, lab_fix::LabFix, lab_observe::LabObserve, lab_replay::LabReplay,
    lab_report::LabReport, lab_run::LabRun, lab_scenarios::LabScenarios, login::Login, orders::Orders,
    register::Register,
};
use leptos::*;
use leptos_router::*;

#[component]
fn Placeholder(title: &'static str) -> impl IntoView {
    view! {
        <section class="page">
            <h1>{title}</h1>
            <p class="muted">"Placeholder — to be built."</p>
        </section>
    }
}

#[component]
pub fn App() -> impl IntoView {
    provide_auth();
    view! {
        <Router>
            <Navbar/>
            <main class="container">
                <Routes>
                    // Bookstore
                    <Route path="/" view=Home/>
                    <Route path="/catalog" view=Catalog/>
                    <Route path="/book/:id" view=BookDetail/>
                    <Route path="/cart" view=|| view! { <RequireAuth><Cart/></RequireAuth> }/>
                    <Route path="/checkout" view=|| view! { <RequireAuth><Checkout/></RequireAuth> }/>
                    <Route path="/orders" view=|| view! { <RequireAuth><Orders/></RequireAuth> }/>
                    <Route path="/login" view=Login/>
                    <Route path="/register" view=Register/>
                    <Route path="/admin" view=|| view! { <Placeholder title="Admin Panel"/> }/>
                    // Security Lab
                    <Route path="/lab" view=LabDashboard/>
                    <Route path="/lab/scenarios" view=LabScenarios/>
                    <Route path="/lab/run/:id" view=LabRun/>
                    <Route path="/lab/observe/:run_id" view=LabObserve/>
                    <Route path="/lab/fix/:run_id" view=LabFix/>
                    <Route path="/lab/replay/:run_id" view=LabReplay/>
                    <Route path="/lab/report/:run_id" view=LabReport/>
                    <Route path="/*any" view=|| view! { <Placeholder title="404 — Not Found"/> }/>
                </Routes>
            </main>
        </Router>
    }
}
