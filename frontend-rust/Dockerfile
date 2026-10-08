# ---------- Stage 1: build the Leptos CSR app to WASM ----------
FROM rust:1-slim AS builder

WORKDIR /app

RUN rustup target add wasm32-unknown-unknown \
    && cargo install --locked trunk

COPY . .
RUN trunk build --release

# ---------- Stage 2: serve with nginx ----------
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
