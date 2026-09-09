# API contract

openapi.json 由 `uv run --locked python infra/export_openapi.py` 生成，schema.d.ts 由 `npm run api:types` 生成；不要手改。当前只有 health/ready；业务客户端留待业务 API 定义后生成。
